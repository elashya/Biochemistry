import streamlit as st
import json, time, os, re
from collections import defaultdict

# ----------------------
# Config
# ----------------------
APP_TITLE = "IGCSE Physics (0625) — Timed Exam Practice (Dynamic Assistant)"

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

# ----------------------
# Secrets / PIN
# ----------------------
def _get_secret(name, default=None):
    try:
        return st.secrets.get(name, default)
    except Exception:
        return os.getenv(name, default)

def require_pin():
    """Gate the app behind a PIN stored in Streamlit Secrets as APP_PIN."""
    APP_PIN = _get_secret("APP_PIN", None)
    if not APP_PIN:
        st.sidebar.warning("Admin: Set APP_PIN in Streamlit Secrets to enable the PIN gate.")
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

# ----------------------
# OpenAI Assistants API
# ----------------------
def _get_openai_client():
    api_key = _get_secret("OPENAI_API_KEY", None)
    if not api_key:
        return None
    try:
        from openai import OpenAI
        return OpenAI(api_key=api_key)
    except Exception:
        return None

def generate_questions_from_assistant(selected_pairs, n_questions):
    """Ask the Assistant to generate questions dynamically in JSON."""
    client = _get_openai_client()
    assistant_id = _get_secret("ASSISTANT_ID", None)
    if client is None or not assistant_id:
        st.error("Assistant not available. Please set OPENAI_API_KEY and ASSISTANT_ID in Secrets.")
        return []

    units_info = "\n".join([f"- {u} → {s}" for (u, s) in selected_pairs])
    payload = f"""
You are a Cambridge IGCSE Physics (0625) exam question generator.
Generate {n_questions} questions in JSON format.

Target units/sub-units:
{units_info}

Each question must include:
- id
- unit
- subunit
- type (numerical | mcq | short_text)
- prompt
- options (mcq only)
- answer
- tolerance_abs (if numerical)
- units (if numerical)
- marks
- technique
- common_mistakes
- marking_scheme
- source

Rules:
- Output ONLY a valid JSON array, no extra text.
- Questions must match Cambridge IGCSE Physics (0625) style and difficulty.
- Include realistic marking scheme, technique, and common mistakes.
"""
    try:
        thread = client.beta.threads.create()
        client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=payload
        )
        client.beta.threads.runs.create_and_poll(
            thread_id=thread.id,
            assistant_id=assistant_id,
            temperature=0.3,
            top_p=0.9
        )
        msgs = client.beta.threads.messages.list(thread_id=thread.id, order="desc", limit=1)
        if not msgs.data:
            return []
        content = "".join([p.text.value for p in msgs.data[0].content if getattr(p, "type", "") == "text"])
        match = re.search(r'\[.*\]', content, re.DOTALL)
        return json.loads(match.group(0)) if match else []
    except Exception as e:
        st.error(f"Error generating questions: {e}")
        return []

def assistant_grade(question, user_answer, max_marks):
    """Ask the Assistant to grade a single answer and return JSON feedback."""
    client = _get_openai_client()
    assistant_id = _get_secret("ASSISTANT_ID", None)
    if client is None or not assistant_id:
        return None

    payload = f"""
Evaluate the student's answer for the following Physics question:

Question: {question['prompt']}
Unit: {question['unit']} | Sub-unit: {question['subunit']}
Type: {question['type']}
Correct answer (for reference): {question.get('answer','')}
Student answer: {user_answer}

Return JSON with:
- awarded (0..{max_marks})
- max_marks
- correct (true/false)
- feedback (list of 1-3 tips)
- expected (string, optional)
- correct_option (string, optional)
Only output JSON, nothing else.
"""
    try:
        thread = client.beta.threads.create()
        client.beta.threads.messages.create(thread_id=thread.id, role="user", content=payload)
        client.beta.threads.runs.create_and_poll(thread_id=thread.id, assistant_id=assistant_id)
        msgs = client.beta.threads.messages.list(thread_id=thread.id, order="desc", limit=1)
        if not msgs.data:
            return None
        content = "".join([p.text.value for p in msgs.data[0].content if getattr(p, "type", "") == "text"])
        match = re.search(r'\{.*\}', content, re.DOTALL)
        return json.loads(match.group(0)) if match else None
    except Exception:
        return None

# ----------------------
# Quiz Helpers
# ----------------------
def reset_state():
    for k in ["quiz_started","selected_qs","q_index","score","marks_total",
              "responses","error_log","start_ts","end_ts","duration_min"]:
        st.session_state.pop(k, None)

def start_quiz(selected_pairs, n_questions, duration_min):
    with st.spinner("Generating questions... please wait (up to 30s)"):
        selected = generate_questions_from_assistant(selected_pairs, n_questions)

    if len(selected) == 0:
        st.warning("No questions generated. Try different units/sub-units.")
        return

    st.session_state.quiz_started = True
    st.session_state.selected_qs = selected
    st.session_state.q_index = 0
    st.session_state.score = 0
    st.session_state.marks_total = sum(q.get("marks",1) for q in selected)
    st.session_state.responses = []
    st.session_state.error_log = []
    st.session_state.duration_min = duration_min
    st.session_state.start_ts = time.time()
    st.session_state.end_ts = st.session_state.start_ts + duration_min*60

def render_header():
    st.title(APP_TITLE)
    st.caption("Powered by Assistant ID (dynamic question generation + grading).")
    st.markdown(
        "- **Syllabus**: [0625 Physics 2023–2025](https://www.cambridgeinternational.org/Images/595430-2023-2025-syllabus.pdf)\n"
        "- **Grade Descriptions**: [2023–2025](https://www.cambridgeinternational.org/Images/730281-2023-2025-grade-descriptions.pdf)"
    )

def time_remaining_text():
    if not st.session_state.get("quiz_started"):
        return ""
    remaining = max(0, int(st.session_state.end_ts - time.time()))
    m, s = divmod(remaining, 60)
    return f"⏳ Time remaining: **{m:02d}:{s:02d}**"

def grade_with_assistant_or_local(q, user_answer):
    max_marks = q.get("marks", 1)
    data = assistant_grade(q, user_answer, max_marks)
    if data:
        awarded = int(max(0, min(max_marks, data.get("awarded", 0))))
        correct = bool(data.get("correct", awarded == max_marks))
        feedback_points = [str(x) for x in data.get("feedback", [])]
        if "expected" in data:
            feedback_points.append(f"**Expected**: {data['expected']}")
        if "correct_option" in data and q["type"] == "mcq":
            feedback_points.append(f"**Correct option**: {data['correct_option']}")
        return correct, awarded, feedback_points
    return False, 0, ["❌ Unable to grade (Assistant unavailable)."]

def end_quiz_summary():
    st.subheader("📊 Summary & Score")
    score = st.session_state.score
    total = st.session_state.marks_total
    pct = 100.0 * score / total if total else 0.0
    st.metric("Final Score", f"{score} / {total}", f"{pct:.1f}%")
    rows = []
    per_topic = defaultdict(lambda: {"marks":0, "scored":0})
    for r in st.session_state.responses:
        key = (r["unit"], r["subunit"])
        per_topic[key]["marks"] += r["marks"]
        per_topic[key]["scored"] += r["awarded"]
        rows.append({
            "Q#": r["index"]+1,
            "Unit": r["unit"], "Sub-unit": r["subunit"],
            "Result": "✓" if r["correct"] else "✗",
            "Marks": r["marks"], "Awarded": r["awarded"],
            "Your answer": r["user_answer"],
            "Correct/Expected": r.get("correct_display",""),
            "Source": r.get("source","Generated")
        })
    if rows:
        st.dataframe(rows, use_container_width=True)
    st.subheader("🧭 Focus Suggestions")
    weak = sorted(per_topic.items(), key=lambda kv: (kv[1]["scored"]/(kv[1]["marks"] or 1e-9)))
    for i, ((unit, sub), stats) in enumerate(weak[:5], start=1):
        rate = 100.0*stats["scored"]/(stats["marks"] or 1e-9)
        st.write(f"{i}. **{unit} → {sub}**: {rate:.0f}% — revise with marking schemes.")
    if st.session_state.error_log:
        st.download_button("Download error log", "\n".join(st.session_state.error_log), "error_log.csv")

    if st.button("🔁 Start another quiz"):
        reset_state()
        st.rerun()

# ----------------------
# Main UI
# ----------------------
def main():
    st.set_page_config(page_title=APP_TITLE, page_icon="📘")
    require_pin()
    render_header()

    with st.sidebar:
        has_ai = bool(_get_secret("OPENAI_API_KEY") and _get_secret("ASSISTANT_ID"))
        if has_ai:
            st.success("Assistant grading: ON")
        else:
            st.warning("Assistant grading: OFF (no secrets set)")

    # Config form
    if not st.session_state.get("quiz_started"):
        with st.form("config"):
            # Flatten all subunits
            all_subunits = []
            for u, subs in SYLLABUS_UNITS.items():
                for s in subs:
                    all_subunits.append((u, s))
        
            # Show just subunit names in the UI
            subunit_names = [s for (_, s) in all_subunits]
            selected_names = st.multiselect("Select sub-units", subunit_names)
        
            # Map back to (unit, subunit) pairs
            selected_pairs = [(u, s) for (u, s) in all_subunits if s in selected_names]
        
            n_questions = st.number_input("Number of questions", min_value=3, max_value=40, value=5, step=1)
            duration_min = st.number_input("Exam time (minutes)", min_value=10, max_value=180, value=30, step=5)
            start = st.form_submit_button("▶️ Start Quiz")

        if start:
            if not selected_pairs:
                st.error("Select at least one sub-unit.")
            else:
                start_quiz(selected_pairs, n_questions, duration_min)
                st.rerun()
        return

    # Active Quiz
    st.info(time_remaining_text())
    if time.time() >= st.session_state.end_ts:
        st.warning("⏰ Time is up! Submitting...")
        end_quiz_summary()
        return

    q_index = st.session_state.q_index
    selected = st.session_state.selected_qs
    if q_index >= len(selected):
        end_quiz_summary()
        return

    q = selected[q_index]
    st.subheader(f"Question {q_index+1} of {len(selected)}")
    st.markdown(f"**Unit:** {q['unit']}  \n**Sub-unit:** {q['subunit']}  \n**Marks:** {q.get('marks',1)}")
    st.write(q["prompt"])

    if q["type"] == "mcq":
        user_answer = st.radio("Choose an option:", q["options"], index=0)
    elif q["type"] == "numerical":
        user_answer = st.text_input(f"Your answer ({q.get('units','')})")
    elif q["type"] == "short_text":
        user_answer = st.text_area("Your short answer", height=120)
    else:
        st.error("Unknown question type.")
        return

    if st.button("✅ Submit Answer"):
        correct, awarded, feedback = grade_with_assistant_or_local(q, user_answer)
        st.session_state.score += awarded
        st.session_state.responses.append({
            "index": q_index, "unit": q["unit"], "subunit": q["subunit"],
            "marks": q.get("marks",1), "awarded": awarded, "correct": correct,
            "user_answer": user_answer, "source": "Generated"
        })
        st.success("Feedback")
        for f in feedback:
            st.markdown("- " + f)
        if not correct:
            st.session_state.error_log.append(f"{q['unit']} | {q['subunit']} | Q{q_index+1} | Your: {user_answer}")
        if st.button("➡️ Next question"):
            st.session_state.q_index += 1
            st.rerun()

    if st.button("🛑 End quiz now"):
        end_quiz_summary()

if __name__ == "__main__":
    main()
