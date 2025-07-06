import streamlit as st
from openai import OpenAI
import time
import re
import pandas as pd
from datetime import datetime, timedelta

# === Config ===
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
APP_PIN = st.secrets["APP_PIN"]

# Map each course to its corresponding assistant ID
ASSISTANT_IDS = {
    "Biology - SBI3U": "asst_QxWwAb8wjBkzUxHehzpmlp8Z", 
    "Biology - SBI4U": "asst_t9vrqxAau5LWqOSR9bmm1egb",  
    "Biology - Uni Exam": "asst_6X4Btqc3rNXYyH0iwMZAHiau",
    "Chemistry - SCH3U": "asst_4RzhLQqUFGni8leY61N7Nw14"  
}

client = OpenAI(api_key=OPENAI_API_KEY)

st.set_page_config(page_title="AI BioChem Tutor", layout="centered")
st.title("\U0001F9EA AI Biology & Chemistry Tutor")

# === PIN Authentication ===
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    pin = st.text_input("Enter your secure access PIN:", type="password")
    if pin == APP_PIN:
        st.session_state.authenticated = True
        st.success("✅ Access granted.")
        time.sleep(1)
        st.rerun()
    else:
        st.stop()

# === Session Initialization ===
def init_session():
    keys_defaults = {
        "selected_course": None,
        "selected_units": None,
        "quiz_started": False,
        "question_index": 0,
        "quiz_thread_id": None,
        "current_question": None,
        "question_body": "",
        "question_history": [],
        "score_summary": "",
        "ready_for_next_question": False,
        "total_questions": 10,
        "current_options": [],
        "is_mcq": False,
        "start_time": None,
        "timestamps": [],
        "question_type": "Short Answer"
    }
    for key, default in keys_defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default

init_session()

# === Study Plan Progress Tracker ===
@st.cache_data
def load_study_data():
    return pd.read_excel("study_plan.xlsx")

def compute_progress(course_df, slides_completed):
    total_slides = course_df["# of slides"].sum()
    cumulative = 0
    for _, row in course_df.iterrows():
        if cumulative + row["# of slides"] > slides_completed:
            slide_within = slides_completed - cumulative + 1
            percent = round((slides_completed / total_slides) * 100, 1)
            return {
                "unit_number": row["Unit#"],
                "unit_title": row["Unit Title"],
                "slide_number": slide_within,
                "percent_complete": percent
            }
        cumulative += row["# of slides"]
    last = course_df.iloc[-1]
    return {
        "unit_number": last["Unit#"],
        "unit_title": last["Unit Title"],
        "slide_number": last["# of slides"],
        "percent_complete": 100.0
    }

# === Course and Units Definition ===
courses = {
    "Biology - SBI3U": ["Diversity of Living Things", "Evolution", "Genetic Processes", "Animals: Structure and Function", "Plants: Anatomy, Growth and Function"],
    "Biology - SBI4U": ["Biochemistry", "Metabolic Processes", "Molecular Genetics", "Homeostasis", "Population Dynamics"],
    "Biology - Uni Exam": ["All topics"],
    "Chemistry - SCH3U": ["Matter & Bonding", "Chemical Reactions", "Quantities & Solutions", "Equilibrium", "Atomic Structure"]
}

# === Main Interface ===
if not st.session_state.quiz_started:
    df = load_study_data()
    df["Course"] = df["Course"].str.lower().replace({"intro": "biology", "bilology": "biology"})
    bio_df = df[df["Course"] == "biology"]
    chem_df = df[df["Course"] == "chemistry"]

    if bio_df.empty or chem_df.empty:
        st.error("\u274C Could not load Biology or Chemistry content from the sheet. Please check formatting.")
        st.stop()

    st.markdown("### 🌟 What are we revising today to get that A+ ?")
    st.subheader("1️⃣ Choose Your Course")
    selected_course = st.selectbox("Select a course:", list(courses.keys()))
    st.session_state.selected_course = selected_course

    st.subheader("2️⃣ Choose Units to Revise")
    selected_units = st.multiselect("Select one or more units:", courses[selected_course])
    st.session_state.selected_units = selected_units

    st.subheader("3️⃣ Number of Questions")
    total_qs = st.selectbox("Select total number of questions:", [3, 10, 15, 20, 25, 30], index=1)
    st.session_state.total_questions = total_qs

    if selected_units:
        if st.button("🚀 Start Quiz"):
            thread = client.beta.threads.create()
            st.session_state.quiz_thread_id = thread.id
            st.session_state.quiz_started = True
            st.session_state.question_index = 0
            st.session_state.question_history = []
            st.session_state.start_time = datetime.now()
            st.session_state.timestamps = []
            st.rerun()

# === Quiz Loop ===
elif st.session_state.quiz_started:
    idx = st.session_state.question_index
    thread_id = st.session_state.quiz_thread_id
    total = st.session_state.total_questions
    assistant_id = ASSISTANT_IDS.get(st.session_state.selected_course)

    if idx < total and not st.session_state.current_question and not st.session_state.ready_for_next_question:
        prompt = f"""
You are a kind and smart high school tutor helping a student prepare for real exams.
Course: {st.session_state.selected_course}
Units: {', '.join(st.session_state.selected_units)}
Question {idx+1} of {total}
Generate a mix of question types, including:
- Multiple Choice [MCQ]
- Short Answer [Short Answer]
- Fill-in-the-blank [Fill-in-the-Blank]
Clearly label the type in brackets.
For MCQ, use format:
A. Option 1
B. Option 2
C. Option 3
D. Option 4
Do NOT include answers or hints.
Only one question per response.
"""
        with st.spinner("\U0001F9E0 Tutor is preparing a question..."):
            client.beta.threads.messages.create(thread_id=thread_id, role="user", content=prompt)
            run = client.beta.threads.runs.create(thread_id=thread_id, assistant_id=assistant_id)
            while run.status != "completed":
                time.sleep(1)
                run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
            messages = client.beta.threads.messages.list(thread_id=thread_id)
            full_text = messages.data[0].content[0].text.value
            st.session_state.current_question = full_text
            st.session_state.timestamps.append(datetime.now())

            lines = full_text.strip().splitlines()
            body_lines, options = [], []
            for line in lines:
                if re.match(r"^[A-Da-d][).]?\s", line):
                    options.append(line.strip())
                else:
                    body_lines.append(line.strip())
            st.session_state.question_body = "\n".join(body_lines).strip()
            st.session_state.current_options = options
            st.session_state.is_mcq = len(options) >= 2
            st.session_state.question_type = "MCQ" if st.session_state.is_mcq else "Short Answer"

    if st.session_state.current_question:
        st.subheader(f"❓ Question {idx+1} of {total}")
        st.markdown(st.session_state.question_body)

        if st.session_state.is_mcq:
            user_answer = st.radio("Choose your answer:", st.session_state.current_options, key=f"mcq_{idx}")
        else:
            user_answer = st.text_area("Your Answer:", key=f"answer_{idx}")

        if st.button("📤 Submit Answer"):
            with st.spinner("📚 Evaluating..."):
                client.beta.threads.messages.create(
                    thread_id=thread_id,
                    role="user",
                    content=f"The student's answer to Question {idx+1} is: {user_answer}\n\nPlease evaluate it clearly:\n- Say if it's correct or not\n- Give a brief explanation."
                )
                run = client.beta.threads.runs.create(thread_id=thread_id, assistant_id=assistant_id)
                while run.status != "completed":
                    time.sleep(1)
                    run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
                messages = client.beta.threads.messages.list(thread_id=thread_id)
                feedback = messages.data[0].content[0].text.value
                st.success("\U0001F9E0 Feedback from Tutor")
                st.markdown(feedback)
                st.session_state.question_history.append({
                    "question": st.session_state.current_question,
                    "answer": user_answer,
                    "feedback": feedback
                })
                st.session_state.ready_for_next_question = True

    if st.session_state.ready_for_next_question:
        next_label = "✅ Finish My Quiz" if idx + 1 == total else "➡️ Next Question"
        if st.button(next_label):
            st.session_state.current_question = None
            st.session_state.question_body = ""
            st.session_state.current_options = []
            st.session_state.ready_for_next_question = False
            st.session_state.question_index += 1
            st.rerun()

    elif idx >= total:
        if not st.session_state.score_summary:
            duration = datetime.now() - st.session_state.start_time
            seconds = int(duration.total_seconds())
            avg_time = seconds / total
            formatted = str(duration).split('.')[0]
            client.beta.threads.messages.create(
                thread_id=thread_id,
                role="user",
                content=f"""Please summarize the student's performance for {total} questions:
- Strengths
- Areas to improve
- Final mark out of {total}
Add timing info:
- Total Time: {formatted}
- Avg Time per Question: {avg_time:.1f} sec
"""
            )
            run = client.beta.threads.runs.create(thread_id=thread_id, assistant_id=assistant_id)
            while run.status != "completed":
                time.sleep(1)
                run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
            messages = client.beta.threads.messages.list(thread_id=thread_id)
            st.session_state.score_summary = messages.data[0].content[0].text.value
        st.subheader("📊 Final Tutor Report")
        st.markdown(st.session_state.score_summary)
        if st.button("🔁 Start Over"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
