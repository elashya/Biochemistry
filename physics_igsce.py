import streamlit as st
import json, re
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
        "Pressure"
    ],
    "Thermal Physics": [
        "Kinetic model; States of Matter; Brownian motion",
        "Gas pressure; Melting/Boiling",
        "Thermal Capacity; Latent Heat",
        "Heat Transfer (conduction, convection, radiation)"
    ],
    "Waves (Light & Sound)": [
        "General wave properties; Reflection",
        "Refraction; Diffraction",
        "Interference; EM Spectrum",
        "Light (Lenses, TIR, critical angle)",
        "Optical Instruments; Sound"
    ],
    "Electricity & Magnetism": [
        "Magnetism; Electrostatics",
        "Current, Voltage, Resistance; Ohm’s Law",
        "Power/Energy in Circuits",
        "Safety; Logic Gates",
        "Electromagnetism; Induction"
    ],
    "Atomic Physics": [
        "Nuclear model; Isotopes",
        "Types of radiation; Detection",
        "Half-life; Dangers",
        "Nuclear Energy & Uses"
    ],
    "Space Physics": [
        "Earth, Moon, Sun; Solar System",
        "Orbits & Satellites",
        "Life Cycle of Stars",
        "Cosmology (Big Bang, Redshift, CMB)"
    ]
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

# ---------------- Question Generation ----------------
def generate_single_question(selected_pairs, progress, usage_counter, paper_type="P2"):
    client = _get_openai_client()
    if client is None:
        return None

    subunits_info = "\n".join([f"- {u} → {s}" for (u, s) in selected_pairs])

    if paper_type == "P1":
        paper_rules = """
Generate ONE multiple-choice exam-style question for Cambridge IGCSE Physics (0625) Paper 1 (MCQ).
- Provide 4 options (A–D).
- Ensure 3 distractors reflect common misconceptions.
- Only 1 correct option.
- Question worth 1 mark.
"""
    elif paper_type == "P6":
        paper_rules = """
Generate ONE practical/data-handling style exam question for Cambridge IGCSE Physics (0625) Paper 6.
- Use experiment-based or data analysis tasks.
- Include tables, graphs, apparatus, sources of error.
- Allocate realistic marks (1–6 per part).
"""
    else:
        paper_rules = """
Generate ONE structured exam-style question for Cambridge IGCSE Physics (0625) Paper 2/4.
- Use command words (state, explain, calculate, describe).
- Multi-part if suitable.
- Allocate realistic marks.
"""

    prompt = f"""
You are a Cambridge IGCSE Physics (0625) examiner.

Student selected ONLY these sub-units:
{subunits_info}

{paper_rules}

Return ONLY valid JSON with fields: id, unit, subunit, type, prompt, options (if mcq), answer, tolerance_abs (if numerical), units, marks, technique, common_mistakes, marking_scheme, difficulty, command_words, source.
"""
    try:
        thread = client.beta.threads.create()
        client.beta.threads.messages.create(thread_id=thread.id, role="user", content=prompt)
        client.beta.threads.runs.create_and_poll(thread_id=thread.id, assistant_id=ASSISTANT_ID, temperature=0.7)
        msgs = client.beta.threads.messages.list(thread_id=thread.id, order="desc", limit=1)

        if not msgs.data:
            return None
        content = extract_message_content(msgs.data[0])
        raw_q = parse_json_from_content(content)
        return raw_q
    except Exception:
        return None

# ---------------- Main ----------------
def main():
    st.set_page_config(page_title=APP_TITLE, page_icon="📘")
    require_pin()
    st.title(APP_TITLE)
    st.caption("Adaptive mode: generates one question at a time, adjusting to performance.")

    if not st.session_state.get("quiz_started"):
        with st.form("config"):
            all_subunits = [(u, s) for u, subs in SYLLABUS_UNITS.items() for s in subs]
            subunit_names = [f"{u} – {s}" for (u, s) in all_subunits]
            selected_names = st.multiselect("Select sub-units", subunit_names)
            selected_pairs = [pair for pair, label in zip(all_subunits, subunit_names) if label in selected_names]

            paper_type = st.selectbox("Select Paper Type", ["P1", "P2/4", "P6"], index=1)
            n_questions = st.number_input("Number of questions", 3, 20, 5, 1)
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
                st.session_state.selected_pairs = selected_pairs
                st.session_state.paper_type = paper_type
                st.session_state.n_questions = n_questions
                q = generate_single_question(selected_pairs, {}, defaultdict(int), paper_type)
                if q: st.session_state.current_q = q
                st.rerun()
        return

    q_index = st.session_state.q_index
    n_questions = st.session_state.n_questions
    paper_type = st.session_state.get("paper_type", "P2/4")

    q = st.session_state.get("current_q", None)
    if not q:
        q = generate_single_question(st.session_state.selected_pairs, {}, defaultdict(int), paper_type)
        if q: st.session_state.current_q = q
        else:
            st.error("Failed to generate question.")
            return

    st.subheader(f"Question {q_index+1} of {n_questions}")
    st.write(q["prompt"])

    user_input_key = f"ans_{q_index}"
    if not st.session_state.get("submitted", False):
        if paper_type == "P1" and q.get("type") == "mcq" and "options" in q:
            user_answer = st.radio("Choose one option:", q["options"], key=user_input_key)
        elif paper_type == "P6":
            user_answer = st.text_area("Your structured response:", key=user_input_key)
        else:
            user_answer = st.text_input("Your answer", key=user_input_key)

        if st.button("✅ Submit Answer"):
            if not str(user_answer).strip():
                st.warning("⚠️ Please enter an answer before submitting.")
            else:
                st.session_state.submitted = True
                st.session_state.last_user_answer = user_answer
                st.rerun()
    else:
        st.success("Feedback")
        st.write("(Grading logic here)")
        if st.button("➡️ Next"):
            st.session_state.q_index += 1
            st.session_state.submitted = False
            new_q = generate_single_question(st.session_state.selected_pairs, {}, defaultdict(int), paper_type)
            if new_q: st.session_state.current_q = new_q
            st.rerun()

if __name__ == "__main__":
    main()
