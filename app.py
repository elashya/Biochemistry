import streamlit as st
from openai import OpenAI
import time
import random

# === Config ===
BIOCHEM_ASSISTANT_ID = "asst_uZSql3UUgVbDRKD4jaMXUkU5"
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
APP_PIN = st.secrets["APP_PIN"]

client = OpenAI(api_key=OPENAI_API_KEY)

# === Page Setup ===
st.set_page_config(page_title="AI BioChem Tutor", layout="centered")
st.title("🧪 AI Biology & Chemistry Tutor")

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

# === Session State Initialization ===
def init_session():
    for key in [
        "selected_course", "selected_units", "quiz_started", "question_index",
        "quiz_thread_id", "current_question", "question_history", "score_summary",
        "ready_for_next_question", "total_questions"
    ]:
        if key not in st.session_state:
            if key == "question_index":
                st.session_state[key] = 0
            elif key == "ready_for_next_question":
                st.session_state[key] = False
            elif key == "total_questions":
                st.session_state[key] = 10
            else:
                st.session_state[key] = None

init_session()

# === Course and Unit Selection ===
courses = {
    "Biology": [
        "Biochemistry", "Metabolic Processes", "Molecular Genetics",
        "Homeostasis", "Population Dynamics"
    ],
    "Chemistry": [
        "Matter & Bonding", "Chemical Reactions", "Quantities & Solutions",
        "Chemical Systems & Equilibrium", "Atomic & Molecular Structure"
    ]
}

if not st.session_state.quiz_started:
    st.markdown("""
        ### 👋 Assalamu Alaikum, Sohail!
        
        Welcome back to your personal revision coach. I know you're aiming for an **A+** — and with focus, effort, and Allah's help, you can absolutely get there!

        🌟 Let's get started — which course are we revising today?
    """)

    st.subheader("1️⃣ Choose Your Course")
    selected_course = st.selectbox("Select a course:", list(courses.keys()))
    st.session_state.selected_course = selected_course

    st.subheader("2️⃣ Choose Units to Revise")
    selected_units = st.multiselect("Select one or more units:", courses[selected_course])
    st.session_state.selected_units = selected_units

    st.subheader("3️⃣ How many questions do you want to practice?")
    total_qs = st.selectbox("Select total number of questions:", [5, 10, 15, 20], index=1)
    st.session_state.total_questions = total_qs

    if selected_units:
        if st.button("🚀 Start Quiz"):
            thread = client.beta.threads.create()
            st.session_state.quiz_thread_id = thread.id
            st.session_state.quiz_started = True
            st.session_state.question_history = []
            st.session_state.question_index = 0
            st.session_state.score_summary = ""
            st.session_state.ready_for_next_question = False
            st.rerun()

# === Quiz Loop ===
elif st.session_state.quiz_started:
    idx = st.session_state.question_index
    thread_id = st.session_state.quiz_thread_id
    total = st.session_state.total_questions

    # === Ask New Question ===
    if idx < total and not st.session_state.current_question and not st.session_state.ready_for_next_question:
        prompt = f"""
You are a kind and smart high school tutor helping a student prepare for a real exam.

Course: {st.session_state.selected_course}
Selected Units: {', '.join(st.session_state.selected_units)}

Please generate question {idx+1} out of {total} based on the selected units.
Structure the question as:
1. The question clearly numbered (e.g., Q1)
2. Ensure it mimics real exam difficulty
3. Avoid overly complex phrasing
4. Do not give the answer yet
"""

        with st.spinner("🧠 Tutor is preparing a question..."):
            client.beta.threads.messages.create(
                thread_id=thread_id,
                role="user",
                content=prompt
            )

            run = client.beta.threads.runs.create(
                thread_id=thread_id,
                assistant_id=BIOCHEM_ASSISTANT_ID
            )

            while run.status != "completed":
                time.sleep(1)
                run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)

            messages = client.beta.threads.messages.list(thread_id=thread_id)
            q_text = messages.data[0].content[0].text.value
            st.session_state.current_question = q_text

    if st.session_state.current_question:
        st.subheader(f"❓ Question {idx+1} of {total}")
        st.markdown(st.session_state.current_question)

        user_answer = st.text_area("Your Answer:", key=f"answer_{idx}")
        if st.button("📤 Submit Answer"):
            with st.spinner("📚 Evaluating your answer..."):
                client.beta.threads.messages.create(
                    thread_id=thread_id,
                    role="user",
                    content=f"The student's answer to Question {idx+1} is: {user_answer}\n\nPlease evaluate it by:\n- Saying if it's correct or not\n- Giving a clear explanation\n- One encouragement note"
                )

                run = client.beta.threads.runs.create(
                    thread_id=thread_id,
                    assistant_id=BIOCHEM_ASSISTANT_ID
                )

                while run.status != "completed":
                    time.sleep(1)
                    run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)

                messages = client.beta.threads.messages.list(thread_id=thread_id)
                feedback = messages.data[0].content[0].text.value
                st.markdown("---")
                st.success("🧠 Feedback from Tutor:")
                st.markdown(feedback)

                # Store feedback and wait for next button
                st.session_state.question_history.append({
                    "question": st.session_state.current_question,
                    "answer": user_answer,
                    "feedback": feedback
                })
                st.session_state.ready_for_next_question = True

    if st.session_state.ready_for_next_question:
        if st.button("➡️ Next Question"):
            st.session_state.current_question = None
            st.session_state.ready_for_next_question = False
            st.session_state.question_index += 1
            st.rerun()

    # === Final Report ===
    elif idx >= total:
        if not st.session_state.score_summary:
            with st.spinner("🧠 Generating final summary..."):
                client.beta.threads.messages.create(
                    thread_id=thread_id,
                    role="user",
                    content=f"Please summarize the student's performance over {total} questions. Highlight:\n- Strengths\n- Areas to improve\n- Final mark out of {total}"
                )

                run = client.beta.threads.runs.create(
                    thread_id=thread_id,
                    assistant_id=BIOCHEM_ASSISTANT_ID
                )

                while run.status != "completed":
                    time.sleep(1)
                    run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)

                messages = client.beta.threads.messages.list(thread_id=thread_id)
                summary = messages.data[0].content[0].text.value
                st.session_state.score_summary = summary

        st.subheader("📊 Final Tutor Report")
        st.markdown(st.session_state.score_summary)

        if st.button("🔁 Start Over"):
            for key in [
                "selected_course", "selected_units", "quiz_started", "question_index",
                "quiz_thread_id", "current_question", "question_history", "score_summary",
                "ready_for_next_question", "total_questions"
            ]:
                if key == "question_index":
                    st.session_state[key] = 0
                elif key == "ready_for_next_question":
                    st.session_state[key] = False
                elif key == "total_questions":
                    st.session_state[key] = 10
                else:
                    st.session_state[key] = None
            st.rerun()
