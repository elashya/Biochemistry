import streamlit as st
import json, os, re
from collections import defaultdict

APP_TITLE = "IGCSE Physics (0625) — Adaptive Practice (Dynamic Assistant)"

# Hardcode Assistant ID
ASSISTANT_ID = "asst_6V33q7Edl4vlh4fiER6OG09d"

SYLLABUS_UNITS = {
    "General Physics": [
        "Length & time", "Mass & weight", "Density",
        "Speed, velocity & acceleration", "Forces & Newton’s laws",
        "Turning effects of forces", "Momentum",
        "Energy, work & power", "Pressure"
    ],
    "Thermal Physics": [
        "Kinetic model of matter", "Thermal properties & temperature",
        "Transfer of thermal energy"
    ],
    "Properties of Waves (Light & Sound)": [
        "General wave properties", "Light (reflection, refraction, lenses, critical angle)",
        "Sound"
    ],
    "Electricity & Magnetism": [
        "Simple phenomena of magnetism", "Electrical quantities",
        "Electric circuits", "Digital electronics (logic gates)",
        "Dangers of electricity", "Electromagnetic effects"
    ],
    "Atomic Physics": [
        "The nuclear model of the atom", "Radioactivity", "Safety & uses of radiation"
    ],
}

# ---------------- PIN ----------------
def require_pin():
    APP_PIN = st.secrets.get("APP_PIN", None)
    if not APP_PIN:
        return True
    if st.session_state.get("authed"):
        return True
    with st.form("pin_form"):
        pin = st.text_input("Enter access PIN", type="password")
        ok = st.form_submit_button("Unlock")
    if ok:
        if pin == str(APP_PIN):
            st.session_state.authed = True
            st.success("Unlocked.")
            st.rerun()
        else:
            st.error("Incorrect PIN.")
    st.stop()

# ---------------- OpenAI ----------------
def _get_openai_client():
    try:
        from openai import OpenAI
        api_key = st.secrets["OPENAI_API_KEY"]
        return OpenAI(api_key=api_key)
    except Exception as e:
        st.error(f"⚠️ OpenAI client init failed: {e}")
        return None

def extract_message_content(msg):
    out = []
    for part in msg.content:
        if part.type == "text":
            out.append(part.text.value)
        elif hasattr(part, "text"):
            out.append(str(part.text))
        elif hasattr(part, "json"):
            out.append(json.dumps(part.json, indent=2))
        else:
            out.append(str(part))
    return "\n".join(out)

def parse_json_from_content(content):
    fence_match = re.search(r"```json(.*?)```", content, re.DOTALL)
    if fence_match:
        raw_json = fence_match.group(1).strip()
    else:
        match = re.search(r'(\[.*\]|\{.*\})', content, re.DOTALL)
        raw_json = match.group(0) if match else None

    if not raw_json:
        return None

    try:
        data = json.loads(raw_json)
        if isinstance(data, list):
            return data[0] if data else None
        return data
    except Exception:
        return None

def generate_single_question(selected_pairs, progress, usage_counter):
    client = _get_openai_client()
    if client is None:
        return None

    subunits_info = "\n".join([f"- {u} → {s}" for (u, s) in selected_pairs])
    coverage = "\n".join([f"{sub}: {count}" for (_, sub), count in usage_counter.items()])
    history_summary = f"So far performance: {progress}" if progress else "No answers yet."

    prompt = f"""
You are a Cambridge IGCSE Physics (0625) tutor.
Student selected ONLY these sub-units:
{subunits_info}

Coverage so far:
{coverage}

Performance so far:
{history_summary}

Generate ONE exam-style question in JSON only.
"""

    try:
        thread = client.beta.threads.create()
        client.beta.threads.messages.create(thread_id=thread.id, role="user", content=prompt)
        client.beta.threads.runs.create_and_poll(thread_id=thread.id, assistant_id=ASSISTANT_ID)
        msgs = client.beta.threads.messages.list(thread_id=thread.id, order="desc", limit=1)

        if not msgs.data:
            return None

        content = extract_message_content(msgs.data[0])
        return parse_json_from_content(content)
    except Exception:
        return None

def assistant_grade(question, user_answer, max_marks):
    client = _get_openai_client()
    if client is None:
        return None

    prompt = f"""
Evaluate this IGCSE Physics (0625) answer.

Question: {question['prompt']}
Correct answer (for reference): {question.get('answer','')}
Student answer: {user_answer}

Return ONLY JSON with awarded marks and feedback.
"""

    try:
        thread = client.beta.threads.create()
        client.beta.threads.messages.create(thread_id=thread.id, role="user", content=prompt)
        client.beta.threads.runs.create_and_poll(thread_id=thread.id, assistant_id=ASSISTANT_ID)
        msgs = client.beta.threads.messages.list(thread_id=thread.id, order="desc", limit=1)

        if not msgs.data:
            return None

        content = extract_message_content(msgs.data[0])
        return parse_json_from_content(content)
    except Exception:
        return None

# ---------------- Helpers ----------------
def reset_state():
    for k in ["quiz_started","q_index","score","marks_total","responses",
              "error_log","usage_counter","n_questions","selected_pairs",
              "submitted","last_result"]:
        st.session_state.pop(k, None)

def render_header():
    st.title(APP_TITLE)
    st.caption("Adaptive mode: generates one question at a time, adjusting to performance.")

def main():
    st.set_page_config(page_title=APP_TITLE, page_icon="📘")
    require_pin()
    render_header()

    with st.sidebar:
        if "OPENAI_API_KEY" in st.secrets:
            st.success("Assistant grading: ON")
        else:
            st.warning("Assistant grading: OFF")
        if "status_message" in st.session_state:
            st.info(st.session_state.status_message)

    if not st.session_state.get("quiz_started"):
        with st.form("config"):
            all_subunits = [(u, s) for u, subs in SYLLABUS_UNITS.items() for s in subs]
            subunit_names = [s for (_, s) in all_subunits]
            selected_names = st.multiselect("Select sub-units", subunit_names)
            selected_pairs = [(u, s) for (u, s) in all_subunits if s in selected_names]

            n_questions = st.number_input("Number of questions", 3, 40, 5, 1)
            start = st.form_submit_button("▶️ Start Adaptive Quiz")

        if start:
            if not selected_pairs:
                st.error("Select at least one sub-unit.")
            else:
                st.session_state.quiz_started = True
                st.session_state.q_index = 0
                st.session_state.score = 0
                st.session_state.marks_total = 0
                st.session_state.responses = []
                st.session_state.error_log = []
                st.session_state.usage_counter = defaultdict(int)
                st.session_state.n_questions = n_questions
                st.session_state.selected_pairs = selected_pairs
                st.session_state.status_message = "🟡 Ready to generate first question"
                st.session_state.submitted = False
                st.rerun()
        return

    q_index = st.session_state.q_index
    n_questions = st.session_state.n_questions

    if q_index >= n_questions:
        st.subheader("📊 Quiz Complete")
        st.metric("Final Score", f"{st.session_state.score}/{st.session_state.marks_total}")
        if st.button("🔁 Start again"):
            reset_state()
            st.rerun()
        return

    if q_index >= len(st.session_state.responses):
        st.session_state.status_message = "🟡 Generating next question..."
        progress = {"responses": st.session_state.responses}
        new_q = generate_single_question(st.session_state.selected_pairs, progress, st.session_state.usage_counter)
        if new_q:
            st.session_state.current_q = new_q
            st.session_state.usage_counter[(new_q["unit"], new_q["subunit"])] += 1
            st.session_state.status_message = f"✅ Generated question {q_index+1}"
        else:
            st.error("Failed to generate question.")
            return

    q = st.session_state.current_q
    st.subheader(f"Question {q_index+1} of {n_questions}")
    st.write(f"**Sub-unit:** {q['subunit']} | **Marks:** {q.get('marks',1)}")
    st.write(q["prompt"])

    if q["type"] == "mcq":
        user_answer = st.radio("Choose:", q.get("options", []))
    elif q["type"] == "numerical":
        user_answer = st.text_input(f"Your answer ({q.get('units','')})")
    else:
        user_answer = st.text_area("Your answer")

    # Ensure state exists
    if "submitted" not in st.session_state:
        st.session_state.submitted = False

    if not st.session_state.submitted:
        if st.button("✅ Submit Answer"):
            if not user_answer.strip():
                st.warning("⚠️ Please enter an answer before submitting.")
            else:
                result = assistant_grade(q, user_answer, q.get("marks",1))
                if result:
                    st.session_state.submitted = True
                    st.session_state.last_result = result
                    st.session_state.last_user_answer = user_answer
                    st.rerun()
    else:
        result = st.session_state.last_result
        user_answer = st.session_state.last_user_answer
        awarded = result.get("awarded",0)
        correct = result.get("correct",False)
        feedback = result.get("feedback",[])

        st.success("Feedback")
        for f in feedback:
            st.markdown("- " + f)

        st.session_state.score += awarded
        st.session_state.marks_total += q.get("marks",1)
        st.session_state.responses.append({
            "index": q_index,
            "unit": q["unit"],
            "subunit": q["subunit"],
            "marks": q.get("marks",1),
            "awarded": awarded,
            "correct": correct,
            "user_answer": user_answer
        })
        if not correct:
            st.session_state.error_log.append(f"{q['subunit']} | Q{q_index+1} | Ans: {user_answer}")

        if st.button("➡️ Next"):
            st.session_state.q_index += 1
            st.session_state.submitted = False
            st.rerun()

if __name__ == "__main__":
    main()
