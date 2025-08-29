
import streamlit as st
import json, random, time, os, re
from collections import defaultdict

# ----------------------
# App Config & Constants
# ----------------------
APP_TITLE = "IGCSE Physics (0625) — Timed Exam Practice (Assistant-Enforced)"
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
# Secrets / PIN helpers
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
        return True  # allow in dev
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
    """Create OpenAI client using the official SDK (v1.x)."""
    api_key = _get_secret("OPENAI_API_KEY", None)
    if not api_key:
        return None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        return client
    except Exception:
        return None

def assistant_grade(question, user_answer, max_marks):
    """
    Ask your configured Assistant (whose system instructions enforce syllabus/technique/common mistakes)
    to evaluate the answer and return a compact JSON.

    The assistant should return JSON like:
    {
      "awarded": 2,
      "max_marks": 3,
      "correct": true,
      "feedback": ["point 1", "point 2"],
      "expected": "7.0 N·m",
      "correct_option": "B"
    }
    """
    client = _get_openai_client()
    assistant_id = _get_secret("ASSISTANT_ID", None)
    if client is None or not assistant_id:
        return None  # No assistant available; caller can fallback to local grading

    # Build a strict instruction for a JSON-only response
    json_schema_hint = f"""
Return ONLY a JSON object with keys:
- "awarded" (integer 0..{max_marks})
- "max_marks" ({max_marks})
- "correct" (boolean)
- "feedback" (array of 1-5 short strings)
- "expected" (string, optional)
- "correct_option" (string, optional)

No prose outside JSON.
"""

    payload = f"""
Question (IGCSE Physics 0625 exam style):
{question['prompt']}

Metadata:
- Unit: {question['unit']}
- Sub-unit: {question['subunit']}
- Marks for this question: {max_marks}
- Type: {question['type']}
- Marking scheme (if provided): {question.get('marking_scheme', '(none)')}
- Technique cues: {', '.join(question.get('technique', []))}
- Common mistakes to warn about: {', '.join(question.get('common_mistakes', []))}
- Correct numeric answer/MCQ option (for reference when awarding marks): {question.get('answer', '(n/a)')} {question.get('units','')}
- Keywords for short answer (if any): {question.get('keywords', [])}
- Options (for MCQ, if any): {question.get('options', [])}

Student's answer:
{str(user_answer)}

Scoring rule:
- Use Cambridge-style marking: method marks + accuracy/units where applicable.
- Award an integer from 0 to {max_marks}.
- Always include 1-3 actionable improvement tips in "feedback".
- If the student's answer is numerical, include expected value + units in "expected".
- If MCQ, include the correct option in "correct_option".

{json_schema_hint}
"""

    try:
        # Create a new ephemeral thread per request
        thread = client.beta.threads.create()
        client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=payload
        )
        # Run with the fixed assistant (system instructions live there)
        run = client.beta.threads.runs.create_and_poll(
            thread_id=thread.id,
            assistant_id=assistant_id,
            temperature=0.2,
            top_p=0.9
        )
        # Fetch messages
        msgs = client.beta.threads.messages.list(thread_id=thread.id, order="desc", limit=1)
        if not msgs.data:
            return None
        content = ""
        parts = msgs.data[0].content
        for p in parts:
            if getattr(p, "type", "") == "text":
                content += p.text.value
        # Extract JSON (some assistants may wrap it in fencing)
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if not match:
            return None
        import json as _json
        data = _json.loads(match.group(0))
        return data
    except Exception as e:
        # For robustness, fail silently to allow local fallback
        return None

# ----------------------
# Local helpers & data
# ----------------------
def load_questions(path="questions.json"):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def numerical_correct(user_value, correct_value, tol_abs=None, tol_rel=None):
    try:
        x = float(str(user_value).strip())
    except Exception:
        return False
    if tol_abs is not None and abs(x - correct_value) <= tol_abs:
        return True
    if tol_rel is not None:
        if correct_value == 0:
            return abs(x - correct_value) <= (tol_abs if tol_abs is not None else 0.0)
        return abs(x - correct_value) / abs(correct_value) <= tol_rel
    return abs(x - correct_value) < 1e-9

def short_text_correct(user_text, keywords):
    if not isinstance(keywords, list) or len(keywords) == 0:
        return False
    text = (user_text or "").lower().strip()
    return all(kw.lower() in text for kw in keywords)

def reset_state():
    for k in [
        "quiz_started","selected_qs","q_index","score","marks_total","responses",
        "error_log","start_ts","end_ts","duration_min"
    ]:
        st.session_state.pop(k, None)

def start_quiz(questions, selected_pairs, n_questions, duration_min):
    filtered = [q for q in questions if (q["unit"], q["subunit"]) in selected_pairs]
    if len(filtered) == 0:
        st.warning("No questions match the selected units/sub-units. Please adjust your selection.")
        return
    random.shuffle(filtered)
    selected = filtered[:n_questions]
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
    st.caption("Assistant-enforced: official Cambridge IGCSE Physics (0625) syllabus & grade descriptions (2023–2025).")
    st.markdown(
        "- **Syllabus (2023–2025)**: https://www.cambridgeinternational.org/Images/595430-2023-2025-syllabus.pdf\n"
        "- **Grade Descriptions (2023–2025)**: https://www.cambridgeinternational.org/Images/730281-2023-2025-grade-descriptions.pdf"
    )

def time_remaining_text():
    if not st.session_state.get("quiz_started"):
        return ""
    remaining = max(0, int(st.session_state.end_ts - time.time()))
    m, s = divmod(remaining, 60)
    return f"⏳ Time remaining: **{m:02d}:{s:02d}**"

# ----------------------
# Grading path (Assistant first, fallback local)
# ----------------------
def grade_with_assistant_or_local(q, user_answer):
    # 1) Try assistant grading
    max_marks = q.get("marks", 1)
    data = assistant_grade(q, user_answer, max_marks)
    if data:
        # Trust awarded value, cap within 0..max
        awarded = int(max(0, min(max_marks, data.get("awarded", 0))))
        correct = bool(data.get("correct", awarded == max_marks))
        feedback_points = []
        if isinstance(data.get("feedback"), list):
            feedback_points.extend([str(x) for x in data["feedback"][:5]])
        expected = data.get("expected")
        correct_option = data.get("correct_option")
        if expected:
            feedback_points.append(f"**Expected**: {expected}")
        if correct_option and q["type"] == "mcq":
            feedback_points.append(f"**Correct option**: {correct_option}")
        return correct, awarded, feedback_points

    # 2) Fallback to deterministic local grading
    q_type = q["type"]
    correct = False
    awarded = 0
    feedback_points = []
    if q_type == "mcq":
        correct = (user_answer == q["answer"])
        awarded = q.get("marks",1) if correct else 0
    elif q_type == "numerical":
        tol_abs = q.get("tolerance_abs")
        tol_rel = q.get("tolerance_rel")
        try:
            correct = numerical_correct(user_answer, float(q["answer"]), tol_abs, tol_rel)
        except Exception:
            correct = False
        awarded = q.get("marks",1) if correct else 0
    elif q_type == "short_text":
        keywords = q.get("keywords", [])
        correct = short_text_correct(user_answer, keywords)
        awarded = q.get("marks",1) if correct else 0
    else:
        st.error("Unknown question type.")
        return False, 0, []

    # Feedback payload
    if correct:
        feedback_points.append("✅ Correct. Good application of technique.")
    else:
        feedback_points.append("❌ Not correct.")

    if q.get("marking_scheme"):
        feedback_points.append(f"**Marking scheme**: {q['marking_scheme']}")
    if q.get("technique"):
        feedback_points.append("**Technique**: " + "; ".join(q["technique"]))
    if q.get("common_mistakes"):
        feedback_points.append("**Common mistakes**: " + "; ".join(q["common_mistakes"]))
    if q_type == "numerical":
        feedback_points.append(f"**Expected**: {q['answer']} {q.get('units','')}")
    if q_type == "mcq":
        feedback_points.append(f"**Correct option**: {q['answer']}")

    return correct, awarded, feedback_points

def end_quiz_summary():
    st.subheader("📊 Summary & Score")
    score = st.session_state.score
    total = st.session_state.marks_total
    pct = 100.0 * score / total if total else 0.0
    st.metric("Final Score", f"{score} / {total}", f"{pct:.1f}%")

    rows = []
    per_topic = defaultdict(lambda: {"marks":0, "scored":0, "count":0})
    for r in st.session_state.responses:
        key = (r["unit"], r["subunit"])
        per_topic[key]["marks"] += r["marks"]
        per_topic[key]["scored"] += r["awarded"]
        per_topic[key]["count"] += 1
        rows.append({
            "Q#": r["index"]+1,
            "Unit": r["unit"],
            "Sub-unit": r["subunit"],
            "Result": "✓" if r["correct"] else "✗",
            "Marks": r["marks"],
            "Awarded": r["awarded"],
            "Your answer": r["user_answer"],
            "Correct/Expected": r.get("correct_display",""),
            "Source": r.get("source","")
        })
    if rows:
        st.dataframe(rows, use_container_width=True)

    st.subheader("🧭 Topic Focus Suggestions")
    weak = sorted(per_topic.items(), key=lambda kv: (kv[1]["scored"]/(kv[1]["marks"] or 1e-9)))
    for i, ((unit, sub), stats) in enumerate(weak[:5], start=1):
        rate = 100.0*stats["scored"]/(stats["marks"] or 1e-9)
        st.write(f"{i}. **{unit} → {sub}**: {rate:.0f}% — revisit formulas, units, and worked examples.")

    if st.session_state.error_log:
        st.download_button(
            "Download error log (CSV)",
            data="\n".join(st.session_state.error_log).encode("utf-8"),
            file_name="error_log.csv",
            mime="text/csv"
        )

    if st.button("🔁 Start another quiz"):
        reset_state()
        st.rerun()

# ----------------------
# UI
# ----------------------
def main():
    st.set_page_config(page_title=APP_TITLE, page_icon="📘", layout="centered")
    require_pin()
    render_header()

    # Secrets check for Assistant ID
    with st.sidebar:
        st.header("Settings")
        has_ai = bool(_get_secret("OPENAI_API_KEY", None) and _get_secret("ASSISTANT_ID", None))
        if has_ai:
            st.success("Assistant grading: ON (system instructions enforced).")
        else:
            st.warning("Assistant grading: OFF (fallback to local rules). Add OPENAI_API_KEY and ASSISTANT_ID in Secrets.")

    questions = load_questions()

    # Config form
    if not st.session_state.get("quiz_started"):
        with st.form("config"):
            units_selected = st.multiselect("Select units", list(SYLLABUS_UNITS.keys()))
            selected_pairs = []
            for u in units_selected:
                subs = st.multiselect(f"Sub-units from **{u}**", SYLLABUS_UNITS[u], key=f"subs_{u}")
                selected_pairs.extend((u, s) for s in subs)
            n_questions = st.number_input("Number of questions", min_value=3, max_value=40, value=10, step=1)
            duration_min = st.number_input("Exam time (minutes)", min_value=10, max_value=180, value=30, step=5)
            start = st.form_submit_button("▶️ Start Quiz")
        if start:
            if len(selected_pairs) == 0:
                st.error("Please select at least one sub-unit.")
            else:
                start_quiz(questions, selected_pairs, n_questions, duration_min)
                st.rerun()
        st.info("💡 Tip: Choose a mix of sub-units and keep time strict to simulate real exam conditions.")
        return

    # Active quiz
    st.info(time_remaining_text())
    if time.time() >= st.session_state.end_ts:
        st.warning("⏰ Time is up! Submitting your quiz...")
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
    st.markdown("—" * 20)
    st.write(q["prompt"])
    if q.get("source"):
        st.caption(f"Source: {q['source']}")

    # Input widget
    if q["type"] == "mcq":
        user_answer = st.radio("Choose an option:", q["options"], index=0)
    elif q["type"] == "numerical":
        user_answer = st.text_input(f"Your answer ({q.get('units','')})", value="")
    elif q["type"] == "short_text":
        user_answer = st.text_area("Your short answer", height=120)
    else:
        st.error("Unknown question type.")
        return

    if st.button("✅ Submit Answer"):
        correct, awarded, feedback_points = grade_with_assistant_or_local(q, user_answer)
        st.session_state.score += awarded

        # Save response
        resp = {
            "index": q_index,
            "unit": q["unit"],
            "subunit": q["subunit"],
            "marks": q.get("marks",1),
            "awarded": awarded,
            "correct": correct,
            "user_answer": user_answer,
            "source": q.get("source","")
        }
        if q["type"] == "numerical":
            resp["correct_display"] = f"{q['answer']} {q.get('units','')}"
        elif q["type"] == "mcq":
            resp["correct_display"] = q["answer"]
        else:
            resp["correct_display"] = ""
        st.session_state.responses.append(resp)

        # Feedback
        st.success("Feedback")
        for p in feedback_points:
            st.markdown("- " + str(p))

        # Error log line
        if not correct:
            st.session_state.error_log.append(
                f"{q['unit']} | {q['subunit']} | Q{q_index+1} | Your: {user_answer} | Expected: {resp['correct_display']}"
            )

        if st.button("➡️ Next question"):
            st.session_state.q_index += 1
            st.rerun()

    st.markdown("---")
    if st.button("🛑 End quiz now"):
        end_quiz_summary()

if __name__ == "__main__":
    main()

