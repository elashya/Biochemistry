import streamlit as st
import json, time, os, re
from collections import defaultdict

APP_TITLE = "IGCSE Physics (0625) — Adaptive Practice (Dynamic Assistant)"

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

# ---------------- Secrets / PIN ----------------
def _get_secret(name, default=None):
    try:
        return st.secrets.get(name, default)
    except Exception:
        return os.getenv(name, default)

def require_pin():
    APP_PIN = _get_secret("APP_PIN", None)
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
    api_key = _get_secret("OPENAI_API_KEY", None)
    if not api_key:
        return None
    try:
        from openai import OpenAI
        return OpenAI(api_key=api_key)
    except Exception:
        return None

def parse_json_from_content(content):
    """Parse JSON robustly, handle fences, objects, arrays, or errors."""
    # Fence: ```json ... ```
    fence = re.search(r"```json(.*?)```", content, re.DOTALL)
    if fence:
        raw_json = fence.group(1).strip()
    else:
        # Match object or array
        match = re.search(r'(\{.*\}|\[.*\])', content, re.DOTALL)
        raw_json = match.group(0) if match else None

    if not raw_json:
        st.error("⚠️ Assistant did not return JSON. Raw output below:")
        st.code(content)
        return None

    try:
        data = json.loads(raw_json)
        # If it's a list, take the first element
        if isinstance(data, list):
            if len(data) == 0:
                st.error("⚠️ Assistant returned an empty list.")
                return None
            return data[0]
        return data
    except Exception as e:
        st.error(f"⚠️ JSON parse error: {e}")
        st.code(raw_json)
        return None

def generate_single_question(selected_pairs, progress, usage_counter):
    """Generate ONE adaptive question from Assistant."""
    client = _get_openai_client()
    assistant_id = _get_secret("ASSISTANT_ID", None)
    if client is None or not assistant_id:
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

Generate ONE exam-style question in JSON.
Rules:
- Question must be from the selected sub-units only.
- Balance coverage (use sub-units less covered).
- Adapt difficulty: easier if struggling, harder if doing well.
- Strictly Cambridge IGCSE Physics style.

Output ONLY JSON. No prose, no intro, no explanation.
"""

    try:
        thread = client.beta.threads.create()
        client.beta.threads.messages.create(thread_id=thread.id, role="user", content=prompt)
        client.beta.threads.runs.create_and_poll(thread_id=thread.id, assistant_id=assistant_id)
        msgs = client.beta.threads.messages.list(thread_id=thread.id, order="desc", limit=1)
        if not msgs.data:
            return None
        content = "".join(
            [p.text.value for p in msgs.data[0].content if getattr(p, "type", "") == "text"]
        )
        return parse_json_from_content(content)
    except Exception as e:
        st.error(f"Error generating question: {e}")
        return None

def assistant_grade(question, user_answer, max_marks):
    """Grade via Assistant."""
    client = _get_openai_client()
    assistant_id = _get_secret("ASSISTANT_ID", None)
    if client is None or not assistant_id:
        return None

    prompt = f"""
Evaluate this IGCSE Physics (0625) answer.

Question: {question['prompt']}
Correct answer (for reference): {question.get('answer','')}
Student answer: {user_answer}

Return ONLY JSON:
{{
  "awarded": 0..{max_marks},
  "max_marks": {max_marks},
  "correct": true/false,
  "feedback": ["tip1","tip2"],
  "expected": "optional",
  "correct_option": "optional"
}}
"""

    try:
        thread = client.beta.threads.create()
        client.beta.threads.messages.create(thread_id=thread.id, role="user", content=prompt)
        client.beta.threads.runs.create_and_poll(thread_id=thread.id, assistant_id=assistant_id)
        msgs = client.beta.threads.messages.list(thread_id=thread.id, order="desc", limit=1)
        if not msgs.data:
            return None
        content = "".join(
            [p.text.value for p in msgs.data[0].content if getattr(p, "type", "") == "text"]
        )
        return parse_json_from_content(content)
    except Exception:
        return None

# ---------------- Helpers ----------------
def reset_state():
    for k in ["quiz_started","q_index","score","marks_total","responses",
              "error_log","usage_counter","n_questions","selected_pairs"]:
        st.session_state.pop(k, None)

def render_header():
    st.title(APP_TITLE)
    st.caption("Adaptive mode: generates one question at a time, adjusting to performance.")

def main():
    st.set_page_config(page_title=APP_TITLE, page_icon="📘")
    require_pin()
    render_header()

    with st.sidebar:
        has_ai = bool(_get_secret("OPENAI_API_KEY") and _get_secret("ASSISTANT_ID"))
        if has_ai:
            st.success("Assistant grading: ON")
        else:
            st.warning("Assistant grading: OFF")
        if "status_message" in st.session_state:
            st.info(st.session_state.status_message)

    # Config form
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
                st.rerun()
        return

    # Active quiz
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

    if st.button("✅ Submit Answer"):
        result = assistant_grade(q, user_answer, q.get("marks",1))
        if result:
            awarded = result.get("awarded",0)
            correct = result.get("correct",False)
            feedback = result.get("feedback",[])
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
            st.success("Feedback")
            for f in feedback: st.markdown("- " + f)
            if not correct:
                st.session_state.error_log.append(f"{q['subunit']} | Q{q_index+1} | Ans: {user_answer}")
            if st.button("➡️ Next"):
                st.session_state.q_index += 1
                st.rerun()
        else:
            st.error("Grading failed.")

if __name__ == "__main__":
    main()
