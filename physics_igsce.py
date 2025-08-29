import streamlit as st
import json, re
from collections import defaultdict

APP_TITLE = "IGCSE Physics (0625) — Adaptive Practice (Dynamic Assistant)"
ASSISTANT_ID = "asst_6V33q7Edl4vlh4fiER6OG09d"

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

# ---------------- Question Generation ----------------
def generate_single_question(selected_pairs, progress, usage_counter):
    client = _get_openai_client()
    if client is None:
        return None

    subunits_info = "\n".join([f"- {u} → {s}" for (u, s) in selected_pairs])
    prompt = f"""
You are a Cambridge IGCSE Physics (0625) tutor.
Student selected ONLY these sub-units:
{subunits_info}

Generate ONE exam-style question in JSON only.
Always include fields: id, unit, subunit, type, prompt, marks, units (if any).
Provide a plausible correct answer in 'answer', but note: it may later be revalidated.
"""

    try:
        thread = client.beta.threads.create()
        client.beta.threads.messages.create(thread_id=thread.id, role="user", content=prompt)
        client.beta.threads.runs.create_and_poll(
            thread_id=thread.id, assistant_id=ASSISTANT_ID, temperature=0.7
        )
        msgs = client.beta.threads.messages.list(thread_id=thread.id, order="desc", limit=1)

        if not msgs.data:
            return None
        content = extract_message_content(msgs.data[0])
        return parse_json_from_content(content)
    except Exception:
        return None

# ---------------- Grading (FIXED) ----------------
def assistant_grade(question, user_answer, max_marks):
    client = _get_openai_client()
    if client is None:
        return None

    prompt = f"""
You are grading IGCSE Physics (0625).

Question: {question['prompt']}
Student answer: {user_answer}

Important:
- IGNORE any "answer" field provided with the question JSON.
- Recalculate the correct solution yourself step by step.
- Then grade the student’s answer compared to your recalculated solution.

Return ONLY JSON with:
- awarded (int marks)
- correct (true/false)
- feedback: list of 4 bullet points covering:
   1. Accuracy check
   2. Technique check
   3. Common mistake (if any)
   4. Improvement tip
"""

    try:
        thread = client.beta.threads.create()
        client.beta.threads.messages.create(thread_id=thread.id, role="user", content=prompt)
        client.beta.threads.runs.create_and_poll(
            thread_id=thread.id, assistant_id=ASSISTANT_ID, temperature=0.3
        )
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
              "submitted","last_result","last_user_answer","current_q"]:
        st.session_state.pop(k, None)

def render_header():
    st.title(APP_TITLE)
    st.caption("Adaptive mode: generates one question at a time, adjusting to performance.")

# ---------------- Main ----------------
def main():
    st.set_page_config(page_title=APP_TITLE, page_icon="📘")
    require_pin()
    render_header()

    if not st.session_state.get("quiz_started"):
        with st.form("config"):
            subunit_names = ["Length & time", "Mass & weight", "Density",
                             "Speed, velocity & acceleration"]
            selected_names = st.multiselect("Select sub-units", subunit_names)
            selected_pairs = [("General Physics", s) for s in selected_names]

            n_questions = st.number_input("Number of questions", 3, 20, 5, 1)
            start = st.form_submit_button("▶️ Start Adaptive Quiz")

        if start:
            if not selected_pairs:
                st.error("Select at least one sub-unit.")
            else:
                reset_state()
                st.session_state.quiz_started = True
                st.session_state.q_index = 0
                st.session_state.score = 0
                st.session_state.marks_total = 0
                st.session_state.responses = []
                st.session_state.n_questions = n_questions
                st.session_state.selected_pairs = selected_pairs
                q = generate_single_question(selected_pairs, {}, defaultdict(int))
                if q:
                    st.session_state.current_q = q
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

    q = st.session_state.get("current_q", None)
    if not q:
        q = generate_single_question(st.session_state.selected_pairs, {}, defaultdict(int))
        if q:
            st.session_state.current_q = q
        else:
            st.error("Failed to generate question.")
            return

    st.subheader(f"Question {q_index+1} of {n_questions}")
    st.write(q["prompt"])

    user_answer = st.text_input("Your answer", key=f"ans_{q_index}")

    if not st.session_state.get("submitted", False):
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
        st.success("Feedback")
        for f in result.get("feedback", []):
            st.markdown("- " + f)

        if len(st.session_state.responses) <= q_index:
            st.session_state.score += result.get("awarded",0)
            st.session_state.marks_total += q.get("marks",1)
            st.session_state.responses.append({
                "index": q_index,
                "prompt": q["prompt"],
                "user_answer": st.session_state.last_user_answer,
                "awarded": result.get("awarded",0),
                "marks": q.get("marks",1),
                "correct": result.get("correct",False)
            })

        if st.button("➡️ Next"):
            st.session_state.q_index += 1
            st.session_state.submitted = False
            new_q = generate_single_question(st.session_state.selected_pairs, {}, defaultdict(int))
            if new_q:
                st.session_state.current_q = new_q
            st.rerun()

if __name__ == "__main__":
    main()
