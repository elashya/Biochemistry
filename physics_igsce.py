import streamlit as st
import json, re, time
from collections import defaultdict

APP_TITLE = "IGCSE Physics (0625) — Adaptive Practice"
ASSISTANT_ID = "asst_6V33q7Edl4vlh4fiER6OG09d"

# ---------------- IGCSE Physics Syllabus ----------------
SYLLABUS_UNITS = {
    "General Physics": [
        "Physical quantities & measurement; Motion",
        "Mass & Weight; Density",
        "Forces & Newton’s Laws",
        "Turning effects; Scalars & Vectors",
        "Centre of Mass; Momentum",
        "Energy transfers; Work & Power",
        "Pressure",
    ],
    "Thermal Physics": [
        "Kinetic model; States of Matter; Brownian motion",
        "Gas pressure; Melting/Boiling",
        "Thermal Capacity; Latent Heat",
        "Heat Transfer (conduction, convection, radiation)",
    ],
    "Waves (Light & Sound)": [
        "General wave properties; Reflection",
        "Refraction; Diffraction",
        "Interference; EM Spectrum",
        "Light (Lenses, TIR, critical angle)",
        "Optical Instruments; Sound",
    ],
    "Electricity & Magnetism": [
        "Magnetism; Electrostatics",
        "Current, Voltage, Resistance; Ohm’s Law",
        "Power/Energy in Circuits",
        "Safety; Logic Gates",
        "Electromagnetism; Induction",
    ],
    "Atomic Physics": [
        "Nuclear model; Isotopes",
        "Types of radiation; Detection",
        "Half-life; Dangers",
        "Nuclear Energy & Uses",
    ],
    "Space Physics": [
        "Earth, Moon, Sun; Solar System",
        "Orbits & Satellites",
        "Life Cycle of Stars",
        "Cosmology (Big Bang, Redshift, CMB)",
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
        if getattr(part, "type", None) == "text":
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
        match = re.search(r'(\{.*\}|\[.*\])', content, re.DOTALL)
        raw_json = match.group(1).strip() if match else None
    if not raw_json:
        return None
    try:
        data = json.loads(raw_json)
        if isinstance(data, list):
            return data[0] if data else None
        return data
    except Exception:
        return None

# ---------------- Utility ----------------
def idx_to_letter(i):
    return ["A", "B", "C", "D", "E", "F"][i]

def letter_to_idx(letter):
    m = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4, "F": 5}
    return m.get(letter.upper(), None)

def normalize_mcq_options(options):
    """Strip any leading letters/numbers (A), A., A- etc) so we can label cleanly."""
    norm = []
    for opt in options:
        if not isinstance(opt, str):
            norm.append(str(opt))
            continue
        # remove leading like "A) ", "A. ", "1) ", "1. " etc
        cleaned = re.sub(r"^\s*([A-Da-d0-9])\s*[\.\)]\s*", "", opt).strip()
        norm.append(cleaned)
    return norm

# ---------------- Solution Validation ----------------
def validate_solution(question_json):
    client = _get_openai_client()
    if client is None:
        return question_json

    prompt = f"""
You are an IGCSE Physics (0625) examiner.
Recalculate the correct solution for this question, ensuring the answer and units are correct.

Question JSON:
{json.dumps(question_json, indent=2)}

Return ONLY the corrected JSON with same fields (id, unit, subunit, type, prompt, options, answer, tolerance_abs, units, marks, technique, common_mistakes, marking_scheme, difficulty, command_words, source).
"""
    try:
        thread = client.beta.threads.create()
        client.beta.threads.messages.create(thread_id=thread.id, role="user", content=prompt)
        client.beta.threads.runs.create_and_poll(thread_id=thread.id, assistant_id=ASSISTANT_ID, temperature=0)
        msgs = client.beta.threads.messages.list(thread_id=thread.id, order="desc", limit=1)
        if not msgs.data:
            return question_json
        content = extract_message_content(msgs.data[0])
        corrected = parse_json_from_content(content)
        return corrected if corrected else question_json
    except Exception:
        return question_json

# ---------------- Question Generation ----------------
def generate_single_question(selected_pairs, progress, usage_counter, paper_type="P2/4"):
    client = _get_openai_client()
    if client is None:
        return None

    subunits_info = "\n".join([f"- {u} → {s}" for (u, s) in selected_pairs])
    novelty = f"nonce:{time.time():.0f}"

    if paper_type == "P1":
        paper_rules = """
Generate ONE multiple-choice exam-style question for Cambridge IGCSE Physics (0625) Paper 1 (MCQ).

Requirements:
- Based ONLY on the selected sub-units.
- Provide 4 options (A–D).
- Ensure 3 distractors reflect common misconceptions reported by Cambridge examiners.
- Only 1 correct option. Set "type": "mcq".
- Question worth 1 mark (set "marks": 1).
"""
    elif paper_type == "P6":
        paper_rules = """
Generate ONE practical/data-handling style exam question for Cambridge IGCSE Physics (0625) Paper 6 (Alternative to Practical).

Requirements:
- Focus ONLY on experiment-based or data analysis tasks.
- Use realistic practical scenarios (tables, graphs, measurements, apparatus, sources of error).
- May include: plotting a graph, completing a table, describing apparatus, identifying errors, suggesting improvements.
- Allocate realistic marks (1–6 per part). "type" can be "short_text" or "numerical".
"""
    else:
        paper_rules = """
Generate ONE structured exam-style question for Cambridge IGCSE Physics (0625) Paper 2/4 (Theory).

Requirements:
- Based ONLY on the selected sub-units.
- Use Cambridge command words (state, explain, calculate, determine, describe, suggest).
- Structure as multi-part (a), (b), (c) where suitable.
- Allocate realistic marks (1–6 per part).
- Ensure difficulty matches real Cambridge past paper questions.
"""

    prompt = f"""
You are a Cambridge IGCSE Physics (0625) examiner.

Student selected ONLY these sub-units:
{subunits_info}

{paper_rules}

Return ONLY valid JSON with these fields:
- id, unit, subunit, type, prompt, options (if mcq), answer, tolerance_abs (if numerical), units, marks,
- technique, common_mistakes, marking_scheme, difficulty, command_words, source.

Make sure the JSON is valid and contains a single object. {novelty}
"""

    try:
        with st.spinner("Generating question... please wait"):
            thread = client.beta.threads.create()
            client.beta.threads.messages.create(thread_id=thread.id, role="user", content=prompt)
            client.beta.threads.runs.create_and_poll(thread_id=thread.id, assistant_id=ASSISTANT_ID, temperature=0.7)
            msgs = client.beta.threads.messages.list(thread_id=thread.id, order="desc", limit=1)

        if not msgs.data:
            return None

        content = extract_message_content(msgs.data[0])
        raw_q = parse_json_from_content(content)
        if raw_q:
            raw_q.setdefault("marks", 1 if paper_type == "P1" else 2)
            raw_q.setdefault("type", "mcq" if paper_type == "P1" else "short_text")
            return validate_solution(raw_q)
        return None

    except Exception:
        return None

# ---------------- Grading ----------------
def assistant_grade(question, user_answer, max_marks):
    client = _get_openai_client()
    if client is None:
        return None
    prompt = f"""
You are grading IGCSE Physics (0625).

Question: {question['prompt']}
Full question JSON:
{json.dumps(question, indent=2)}

Student answer: {user_answer}

Important:
- IGNORE any 'answer' field provided with the question JSON.
- Recalculate the correct solution yourself step by step.
- Then grade the student’s answer compared to your recalculated solution.

Return ONLY JSON with:
- awarded (int marks)
- correct (true/false)
- feedback: list of 4 bullet points
- expected: correct solution with units (or correct option text for MCQ)
- correct_option: for MCQ only (e.g. "B")
- related_techniques: list of 2–3 formulas or exam tips
"""
    try:
        thread = client.beta.threads.create()
        client.beta.threads.messages.create(thread_id=thread.id, role="user", content=prompt)
        client.beta.threads.runs.create_and_poll(thread_id=thread.id, assistant_id=ASSISTANT_ID, temperature=0.3)
        msgs = client.beta.threads.messages.list(thread_id=thread.id, order="desc", limit=1)
        if not msgs.data:
            return None
        content = extract_message_content(msgs.data[0])
        return parse_json_from_content(content)
    except Exception:
        return None

# ---------------- Final Summary ----------------
def generate_final_summary(responses):
    client = _get_openai_client()
    if client is None:
        return None
    prompt = f"""
You are an IGCSE Physics (0625) examiner.
Here are the student’s responses and grading details:
{json.dumps(responses, indent=2)}

Provide ONLY JSON with:
- score: "X/Y and percentage"
- strengths: list of 3 bullet points
- weaknesses: list of 3 bullet points
- study_hints: list of 3 bullet points
- related_techniques: list of 3 exam tips or formulas
"""
    try:
        thread = client.beta.threads.create()
        client.beta.threads.messages.create(thread_id=thread.id, role="user", content=prompt)
        client.beta.threads.runs.create_and_poll(thread_id=thread.id, assistant_id=ASSISTANT_ID, temperature=0.3)
        msgs = client.beta.threads.messages.list(thread_id=thread.id, order="desc", limit=1)
        if not msgs.data:
            return None
        content = extract_message_content(msgs.data[0])
        return parse_json_from_content(content)
    except Exception:
        return None

# ---------------- Helpers ----------------
def reset_state():
    for k in [
        "quiz_started","q_index","score","marks_total","responses",
        "error_log","related_techniques_log","usage_counter","n_questions",
        "selected_pairs","submitted","last_result","last_user_answer",
        "current_q","paper_type","mcq_choice_idx"
    ]:
        st.session_state.pop(k, None)

def render_header():
    st.title(APP_TITLE)
    st.caption("Adaptive mode: generates one question at a time, adjusting to performance.")

# ---------------- Main ----------------
def main():
    st.set_page_config(page_title=APP_TITLE, page_icon="📘")
    require_pin()
    render_header()

    # Sidebar progress
    with st.sidebar:
        st.write("### 📊 Progress")
        st.write(f"Score: {st.session_state.get('score',0)}/{st.session_state.get('marks_total',0)}")
        if st.session_state.get("error_log"):
            st.write("### ❌ Error Log")
            for e in st.session_state["error_log"]:
                st.markdown("- " + e)
        if st.session_state.get("related_techniques_log"):
            st.write("### 📘 Related Techniques")
            for t in st.session_state["related_techniques_log"]:
                st.markdown("- " + t)

    # Config screen
    if not st.session_state.get("quiz_started"):
        with st.form("config"):
            # Flatten all sub-units
            all_subunits = [(u, s) for u, subs in SYLLABUS_UNITS.items() for s in subs]
            subunit_labels = [f"{u} – {s}" for (u, s) in all_subunits]
            selected_labels = st.multiselect("Select sub-units (multi-select)", subunit_labels)
            selected_pairs = [pair for pair, label in zip(all_subunits, subunit_labels) if label in selected_labels]

            paper_choice = st.selectbox("Select Paper Type", ["P1 (MCQ)", "P2/4 (Theory)", "P6 (Practical)"])
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
                st.session_state.error_log = []
                st.session_state.related_techniques_log = []
                st.session_state.n_questions = n_questions
                st.session_state.selected_pairs = selected_pairs
                st.session_state.paper_type = "P1" if paper_choice.startswith("P1") \
                                              else "P6" if paper_choice.startswith("P6") else "P2/4"
                st.session_state.usage_counter = {}
                with st.spinner("Getting first question..."):
                    q = generate_single_question(
                        selected_pairs, {}, st.session_state.usage_counter, st.session_state.paper_type
                    )
                if q:
                    st.session_state.current_q = q
                st.rerun()
        return

    # Quiz screen
    q_index = st.session_state.q_index
    n_questions = st.session_state.n_questions
    paper_type = st.session_state.paper_type

    # End of quiz
    if q_index >= n_questions:
        st.subheader("📊 Quiz Complete")
        st.metric("Final Score", f"{st.session_state.score}/{st.session_state.marks_total}")
        summary = generate_final_summary(st.session_state.responses)
        if summary:
            st.write("### 🌟 Performance Summary")
            st.write(f"**Score:** {summary.get('score','')}")
            st.write("**Strengths:**")
            for s in summary.get("strengths", []): st.markdown("- " + s)
            st.write("**Weaknesses:**")
            for w in summary.get("weaknesses", []): st.markdown("- " + w)
            st.write("**Study Hints:**")
            for h in summary.get("study_hints", []): st.markdown("- " + h)
            st.write("**Related Techniques:**")
            for t in summary.get("related_techniques", []): st.markdown("- " + t)
        if st.button("🔁 Start again"):
            reset_state(); st.rerun()
        return

    # Fetch or generate current question
    q = st.session_state.get("current_q", None)
    if not q:
        with st.spinner("Generating question..."):
            q = generate_single_question(
                st.session_state.selected_pairs, {}, st.session_state.usage_counter, paper_type
            )
        if q:
            st.session_state.current_q = q
        else:
            st.error("Failed to generate question.")
            return

    # Display question
    st.subheader(f"Question {q_index+1} of {n_questions}")
    st.write(q["prompt"])

    # Input controls based on paper type & question type
    user_answer = None
    if not st.session_state.get("submitted", False):
        if paper_type == "P1" and q.get("type") == "mcq" and "options" in q:
            # Normalize and render labeled options
            raw_opts = q.get("options", [])
            clean_opts = normalize_mcq_options(raw_opts)
            labels = [f"{idx_to_letter(i)}) {opt}" for i, opt in enumerate(clean_opts)]
            choice = st.radio("Choose one option:", labels, key=f"mcq_{q_index}")
            chosen_idx = labels.index(choice) if choice in labels else None
            st.session_state.mcq_choice_idx = chosen_idx
            user_answer = idx_to_letter(chosen_idx) if chosen_idx is not None else ""
        elif paper_type == "P6":
            user_answer = st.text_area("Your structured response:", key=f"ans_{q_index}")
        else:
            user_answer = st.text_input("Your answer", key=f"ans_{q_index}")

        # Submit
        if st.button("✅ Submit Answer"):
            if not str(user_answer).strip():
                st.warning("⚠️ Please enter an answer before submitting.")
            else:
                result = assistant_grade(q, user_answer, q.get("marks", 1))
                if result:
                    st.session_state.submitted = True
                    st.session_state.last_result = result
                    st.session_state.last_user_answer = user_answer
                    st.rerun()
    else:
        # Show feedback
        result = st.session_state.last_result or {}
        correct = bool(result.get("correct", False))
        awarded = int(result.get("awarded", 0))
        expected = result.get("expected", "")
        correct_option = result.get("correct_option", None)

        if correct:
            st.success("✅ Correct.")
        else:
            if paper_type == "P1" and correct_option:
                st.error(f"❌ Incorrect. Correct answer: **{correct_option}** ({expected})")
            else:
                st.error(f"❌ Incorrect. Correct answer: **{expected}**")

        st.write("### Feedback")
        for f in result.get("feedback", []):
            st.markdown("- " + f)

        # Log once
        if len(st.session_state.responses) <= q_index:
            st.session_state.score += awarded
            st.session_state.marks_total += int(q.get("marks", 1))
            st.session_state.responses.append({
                "index": q_index,
                "prompt": q["prompt"],
                "user_answer": st.session_state.last_user_answer,
                "awarded": awarded,
                "marks": int(q.get("marks", 1)),
                "correct": correct,
            })
            if not correct:
                st.session_state.error_log.append(f"Q{q_index+1}: {st.session_state.last_user_answer}")
            for t in result.get("related_techniques", []):
                st.session_state.related_techniques_log.append(f"Q{q_index+1}: {t}")

        # Next
        if st.button("➡️ Next"):
            st.session_state.q_index += 1
            st.session_state.submitted = False
            with st.spinner("Generating next question..."):
                new_q = generate_single_question(
                    st.session_state.selected_pairs, {}, st.session_state.usage_counter, paper_type
                )
            if new_q:
                st.session_state.current_q = new_q
            st.rerun()

if __name__ == "__main__":
    main()
