import streamlit as st
from openai import OpenAI
import time
import pandas as pd
from datetime import datetime
import re

# === Config ===
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
APP_PIN = st.secrets["APP_PIN"]

ASSISTANT_IDS = {
    "Essay": "asst_XQQG6ntdnYNoNW8m222fAbag",
    "Interviewer": "asst_GgZ2Y3WrUrHMDyO1nsGC9N1D",
    "Biology - SBI3U": "asst_QxWwAb8wjBkzUxHehzpmlp8Z",
    "Biology - SBI4U": "asst_t9vrqxAau5LWqOSR9bmm1egb",
    "Biology - Uni Exam": "asst_6X4Btqc3rNXYyH0iwMZAHiau",
    "Chemistry - SCH3U": "asst_4RzhLQqUFGni8leY61N7Nw14"
}

client = OpenAI(api_key=OPENAI_API_KEY)

st.set_page_config(page_title="AI Essay and Interview Practice", layout="centered")
st.title("\U0001F393 AI Entrance Exam Practice")

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
        "essay_thread_id": None,
        "essay_prompt": "",
        "user_essay": "",
        "essay_feedback": "",
        "essay_submitted": False,
        "interview_thread_id": None,
        "interview_prompt": "",
        "interview_feedback": "",
        "interview_response": "",
        "interview_submitted": False,
        "reset_app": False,
        "mode": None,
        "timestamps": [],  # ✅ required for st.session_state.timestamps.append()
        # For quiz mode
        "quiz_completed": False,
        "quiz_started": False,
        "selected_course": None,
        "selected_units": [],
        "total_questions": 0,
        "question_index": 0,
        "quiz_thread_id": None,
        "question_history": [],
        "start_time": None,
        "ready_for_next_question": False,
        "current_question": None,
        "current_options": [],
    }
    for key, default in keys_defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default

init_session()

# === Reset Logic ===
if st.session_state.get("reset_app", False):
    for key in [
        "essay_thread_id", "essay_prompt", "user_essay", "essay_feedback", "essay_submitted",
        "interview_thread_id", "interview_prompt", "interview_feedback", "interview_response", "interview_submitted"
    ]:
        st.session_state[key] = "" if isinstance(st.session_state[key], str) else None
    st.session_state.reset_app = False
    st.rerun()

# === Mode Selection ===
if not st.session_state.quiz_started and not st.session_state.quiz_completed:
    mode = st.radio("Select Practice Mode:", ["Practice Essay", "Practice Interview", "Practice Quiz"])
    st.session_state.mode = mode
else:
    mode = st.session_state.get("mode", "Practice Quiz")


# === Practice Essay ===
if mode == "Practice Essay":
    st.markdown("### ✨ Practice Essay Writing")

    if not st.session_state.essay_prompt:
        if st.button("✍️ Get Essay Prompt"):
            with st.spinner("🧠 Generating an essay topic..."):
                thread = client.beta.threads.create()
                st.session_state.essay_thread_id = thread.id

                client.beta.threads.messages.create(
                    thread_id=thread.id,
                    role="user",
                    content="Give me one structured essay prompt related to physiotherapy, suitable for university entrance motivation letter practice."
                )
                run = client.beta.threads.runs.create(
                    thread_id=thread.id,
                    assistant_id=ASSISTANT_IDS["Essay"]
                )
                while run.status != "completed":
                    time.sleep(1)
                    run = client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
                messages = client.beta.threads.messages.list(thread_id=thread.id)
                prompt_text = messages.data[0].content[0].text.value

                st.session_state.essay_prompt = prompt_text
                st.session_state.essay_submitted = False
                st.session_state.user_essay = ""
                st.session_state.essay_feedback = ""

    if st.session_state.essay_prompt:
        st.subheader("🧾 Essay Prompt")
        st.markdown(st.session_state.essay_prompt)

        st.subheader("✍️ Write Your Essay")
        st.session_state.user_essay = st.text_area("Paste or type your response here:", height=300)

        if st.button("📤 Submit Essay"):
            with st.spinner("📚 Evaluating your essay..."):
                try:
                    client.beta.threads.messages.create(
                        thread_id=st.session_state.essay_thread_id,
                        role="user",
                        content=f"Here is the student's essay:\n\n{st.session_state.user_essay}\n\nPlease evaluate it using university entrance standards and give feedback and a mark out of 100."
                    )
                    run = client.beta.threads.runs.create(
                        thread_id=st.session_state.essay_thread_id,
                        assistant_id=ASSISTANT_IDS["Essay"]
                    )
                    max_wait = 60
                    start_time = time.time()
                    while run.status not in ["completed", "failed", "cancelled"]:
                        st.write(f"⏳ Current run status: `{run.status}`")
                        if time.time() - start_time > max_wait:
                            raise TimeoutError("⚠️ Assistant evaluation took too long.")
                        time.sleep(1)
                        run = client.beta.threads.runs.retrieve(
                            thread_id=st.session_state.essay_thread_id,
                            run_id=run.id
                        )

                    if run.status != "completed":
                        st.error(f"❌ Assistant run failed with status: {run.status}")
                    else:
                        messages = client.beta.threads.messages.list(thread_id=st.session_state.essay_thread_id)
                        feedback = messages.data[0].content[0].text.value.strip()
                        st.session_state.essay_feedback = feedback
                        st.session_state.essay_submitted = True
                        st.success("✅ Essay evaluated successfully!")
                        st.markdown("### 📋 Feedback")
                        st.markdown(feedback)

                except Exception as e:
                    st.error(f"❌ Error during evaluation: {e}")

# === Practice Interview ===
elif mode == "Practice Interview":
    st.markdown("### 🎤 Practice Interview Questions")

    if not st.session_state.interview_prompt:
        if st.button("🎯 Get Interview Question"):
            with st.spinner("🧠 Generating interview question..."):
                thread = client.beta.threads.create()
                st.session_state.interview_thread_id = thread.id

                client.beta.threads.messages.create(
                    thread_id=thread.id,
                    role="user",
                    content="Ask me one physiotherapy university admission interview question."
                )
                run = client.beta.threads.runs.create(
                    thread_id=thread.id,
                    assistant_id=ASSISTANT_IDS["Interviewer"]
                )
                while run.status != "completed":
                    time.sleep(1)
                    run = client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
                messages = client.beta.threads.messages.list(thread_id=thread.id)
                question_text = messages.data[0].content[0].text.value

                st.session_state.interview_prompt = question_text
                st.session_state.interview_response = ""
                st.session_state.interview_feedback = ""
                st.session_state.interview_submitted = False

    if st.session_state.interview_prompt:
        st.subheader("🎙️ Interview Question")
        st.markdown(st.session_state.interview_prompt)

        st.subheader("🧑‍🎓 Your Response")
        st.session_state.interview_response = st.text_area("Type your answer here:", height=200)

        if st.button("📤 Submit Interview Response"):
            with st.spinner("🧠 Evaluating your response..."):
                try:
                    client.beta.threads.messages.create(
                        thread_id=st.session_state.interview_thread_id,
                        role="user",
                        content=f"Here is my interview response:\n\n{st.session_state.interview_response}\n\nPlease give me feedback as if you're an admission officer."
                    )
                    run = client.beta.threads.runs.create(
                        thread_id=st.session_state.interview_thread_id,
                        assistant_id=ASSISTANT_IDS["Interviewer"]
                    )
                    max_wait = 60
                    start_time = time.time()
                    while run.status not in ["completed", "failed", "cancelled"]:
                        st.write(f"⏳ Current run status: `{run.status}`")
                        if time.time() - start_time > max_wait:
                            raise TimeoutError("⚠️ Interview evaluation took too long.")
                        time.sleep(1)
                        run = client.beta.threads.runs.retrieve(
                            thread_id=st.session_state.interview_thread_id,
                            run_id=run.id
                        )

                    if run.status != "completed":
                        st.error(f"❌ Assistant run failed with status: {run.status}")
                    else:
                        messages = client.beta.threads.messages.list(thread_id=st.session_state.interview_thread_id)
                        feedback = messages.data[0].content[0].text.value.strip()
                        st.session_state.interview_feedback = feedback
                        st.session_state.interview_submitted = True
                        st.success("✅ Interview evaluated successfully!")
                        st.markdown("### 📋 Feedback")
                        st.markdown(feedback)

                except Exception as e:
                    st.error(f"❌ Error during evaluation: {e}")

# === Practice Quiz ===
elif mode == "Practice Quiz":
    st.markdown("### 🧪 Practice Quiz Mode")

    courses = {
        "Biology - SBI3U": ["Diversity of Living Things", "Evolution", "Genetic Processes", "Animals: Structure and Function", "Plants: Anatomy, Growth and Function"],
        "Biology - SBI4U": ["Biochemistry", "Metabolic Processes", "Molecular Genetics", "Homeostasis", "Population Dynamics"],
        "Biology - Uni Exam": ["All topics"],
        "Chemistry - SCH3U": ["Matter & Bonding", "Chemical Reactions", "Quantities & Solutions", "Equilibrium", "Atomic Structure"]
    }

    if not st.session_state.quiz_started and not st.session_state.get("quiz_completed", False):
        selected_course = st.selectbox("Select a course:", list(courses.keys()))
        selected_units = st.multiselect("Select units:", courses[selected_course])
        total_questions = st.selectbox("How many questions?", [3, 10, 15, 20, 30, 40, 50, 60], index=2)

        if selected_units and st.button("🚀 Start Quiz"):
            thread = client.beta.threads.create()
            st.session_state.quiz_thread_id = thread.id
            st.session_state.quiz_started = True
            st.session_state.selected_course = selected_course
            st.session_state.selected_units = selected_units
            st.session_state.total_questions = total_questions
            st.session_state.question_index = 0
            st.session_state.question_history = []
            st.session_state.start_time = datetime.now()
            st.session_state.ready_for_next_question = False
            st.session_state.current_question = None
            st.rerun()

    else:
        idx = st.session_state.question_index
        total = st.session_state.total_questions
        course = st.session_state.selected_course
        assistant_id = ASSISTANT_IDS.get(course)
        thread_id = st.session_state.quiz_thread_id

        if not st.session_state.current_question and not st.session_state.ready_for_next_question:
            with st.spinner("🧠 Generating quiz question..."):
                if course == "Biology - Uni Exam":
                    prompt = f"""
You are a kind and smart high school tutor helping a student prepare for real exams.
Course: {course}
Units: {', '.join(st.session_state.selected_units)}
Question {idx+1} of {total}
Only generate a multiple-choice question [MCQ].
Use this format:
A. Option 1
B. Option 2
C. Option 3
D. Option 4
Do NOT include answers or hints.
Only one question per response.
"""
                else:
                    prompt = f"""
You are a kind and smart high school tutor helping a student prepare for real exams.
Course: {course}
Units: {', '.join(st.session_state.selected_units)}
Question {idx+1} of {total}
Generate **one question only**, choosing randomly from:
- Multiple Choice [MCQ]
- Short Answer
- Fill-in-the-Blank
Clearly label the type.
For MCQ, use format:
A. Option 1
B. Option 2
C. Option 3
D. Option 4
Do NOT include answers or hints.
"""

                client.beta.threads.messages.create(thread_id=thread_id, role="user", content=prompt)
                run = client.beta.threads.runs.create(thread_id=thread_id, assistant_id=assistant_id)
                while run.status != "completed":
                    time.sleep(1)
                    run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
                messages = client.beta.threads.messages.list(thread_id=thread_id)
                text = messages.data[0].content[0].text.value

                st.session_state.current_question = text
                st.session_state.timestamps.append(datetime.now())

                # Determine question type
                if "[MCQ]" in text:
                    st.session_state.question_type = "MCQ"
                elif "[Short Answer]" in text:
                    st.session_state.question_type = "Short Answer"
                elif "[Fill-in-the-Blank]" in text:
                    st.session_state.question_type = "Fill-in-the-Blank"
                else:
                    st.session_state.question_type = "Unknown"

                lines = text.strip().splitlines()
                body_lines, options = [], []
                for line in lines:
                    # Split options if on same line
                    if re.search(r"A[).]\s.+B[).]\s.+C[).]\s.+D[).]\s.+", line):
                        parts = re.split(r"(?=[A-D][).]\s)", line)
                        options.extend([opt.strip() for opt in parts if opt.strip()])
                    elif re.match(r"^[A-D][).]?\s", line):
                        options.append(line.strip())
                    else:
                        body_lines.append(line.strip())

                st.session_state.question_body = "\n".join(body_lines)
                st.session_state.current_options = options

        if st.session_state.current_question:
            st.subheader(f"❓ Question {idx+1} of {total}")
            st.markdown(st.session_state.question_body)

            if st.session_state.question_type == "MCQ":
                user_answer = st.radio("Choose your answer:", st.session_state.current_options, key=f"mcq_{idx}")
            else:
                user_answer = st.text_area("Your Answer:", key=f"answer_{idx}")

            if st.button("📤 Submit Answer"):
                with st.spinner("💬 Getting feedback..."):
                    client.beta.threads.messages.create(
                        thread_id=thread_id,
                        role="user",
                        content=f"The student's answer to Question {idx+1} is: {user_answer}\n\nPlease say if it's correct, explain briefly, and mention the correct answer."
                    )
                    run = client.beta.threads.runs.create(thread_id=thread_id, assistant_id=assistant_id)
                    while run.status != "completed":
                        time.sleep(1)
                        run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
                    messages = client.beta.threads.messages.list(thread_id=thread_id)
                    feedback = messages.data[0].content[0].text.value

                    st.success("✅ Tutor Feedback")
                    st.markdown(feedback)
                    st.session_state.question_history.append({
                        "question": st.session_state.current_question,
                        "answer": user_answer,
                        "feedback": feedback
                    })
                    st.session_state.ready_for_next_question = True

        if st.session_state.ready_for_next_question:
            next_label = "✅ Finish Quiz" if idx + 1 == total else "➡️ Next Question"
            if st.button(next_label):
                st.session_state.current_question = None
                st.session_state.ready_for_next_question = False
                st.session_state.question_index += 1
                if st.session_state.question_index >= total:
                    st.session_state.quiz_started = False
                    st.session_state.quiz_completed = True 
                st.rerun()

        # === Final Summary After Quiz Completion ===
        if not st.session_state.quiz_started and st.session_state.question_history:
            st.subheader("📊 Quiz Summary")
            for i, entry in enumerate(st.session_state.question_history):
                st.markdown(f"**Q{i+1}:** {entry['question']}")
                st.markdown(f"- **Your Answer:** {entry['answer']}")
                st.markdown(f"- **Feedback:** {entry['feedback']}")
                st.markdown("---")

            if st.button("🔄 Start Over (Quiz)", key="quiz_restart_button"):
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.rerun()

# === Global Start Over (Essay/Interview) ===
if st.session_state.essay_submitted or st.session_state.interview_submitted:
    if st.button("🔄 Start Over", key="start_over_button_unique"):
        st.session_state.reset_app = True
        st.rerun()
