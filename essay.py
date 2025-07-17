import streamlit as st
from openai import OpenAI
import time
import pandas as pd
from datetime import datetime
import re
import requests


RECIPIENT_EMAIL = "ahmed03@hotmail.com"  

def send_brevo_email(subject, message_text):
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "api-key": st.secrets["BREVO_API_KEY"]
    }
    data = {
        "sender": {
            "name": "AI Tutor",
            "email": st.secrets["SENDER_EMAIL"]
        },
        "to": [{"email": RECIPIENT_EMAIL}],
        "subject": subject,
        "textContent": message_text
    }

    response = requests.post(url, headers=headers, json=data)

    if response.status_code == 201:
        st.success("📧 Result sent to your inbox.")
    else:
        st.error(f"❌ Failed to send email: {response.status_code} — {response.text}")





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

                        subject = "Essay Practice Result - AI Entrance"
                        message = f"""Essay Prompt:
                        {st.session_state.essay_prompt}
                        
                        User Essay:
                        {st.session_state.user_essay}
                        
                        Evaluation:
                        {feedback}
                        """
                        send_brevo_email(subject, message)


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

                        subject = "Interview Practice Result - AI Entrance"
                        message = f"""Interview Question:
                        {st.session_state.interview_prompt}
                        
                        User Response:
                        {st.session_state.interview_response}
                        
                        Evaluation:
                        {feedback}
                        """
                        send_brevo_email(subject, message)


                except Exception as e:
                    st.error(f"❌ Error during evaluation: {e}")

elif mode == "Practice Quiz":

    # === 1. Show Summary ===
    if st.session_state.get("quiz_completed"):
        st.markdown("## 🎉 Quiz Completed!")

        end_time = datetime.now()
        duration = end_time - st.session_state.start_time
        total_seconds = int(duration.total_seconds())
        formatted_time = str(duration).split('.')[0]
        avg_time = total_seconds / st.session_state.total_questions if st.session_state.total_questions else 0

        st.markdown(f"- ⏱️ **Total Time:** {formatted_time}")
        st.markdown(f"- 🕒 **Avg Time per Question:** {avg_time:.1f} seconds")


        st.markdown("### 📊 Performance Summary")
        summary_data = []
        correct_count = 0
        
        for i, entry in enumerate(st.session_state.question_history, 1):
            feedback = entry["feedback"]
            import re
            is_correct = feedback.strip().startswith("✅")

        
            if is_correct:
                correct_count += 1
            summary_data.append({
                "Q#": i,
                "Answer": entry["answer"],
                "Tutor Feedback": feedback[:100] + "..." if len(feedback) > 100 else feedback
            })
        
        df = pd.DataFrame(summary_data)
        st.dataframe(df.set_index("Q#"), use_container_width=True)
        
        # ✅ total AFTER the loop
        total = st.session_state.total_questions
        st.markdown(f"### 🧮 Final Score: **{correct_count} / {total}**")
        score_percent = (correct_count / total) * 100 if total else 0
        st.markdown(f"**Score Percentage:** `{score_percent:.1f}%`")



        if correct_count == total:
            st.success("🏆 Amazing! You nailed it.")
        elif correct_count == 0:
            st.info("Keep going—each effort is progress, and I'm here to support you! 🍀")
        else:
            st.info("You're getting there! Use the feedback above to grow stronger. 💪")

        with st.spinner("🧠 Analyzing your overall performance..."):
            insights_prompt = f"""
Please give a detailed performance report for this quiz of {total} questions:

- Strengths  
- Areas to improve  
- Study tips  
- Final score  
Time taken: {formatted_time}, Avg time: {avg_time:.1f} sec

Data:
{"".join([f"Q{i+1}: {entry['question']}\nAnswer: {entry['answer']}\nFeedback: {entry['feedback']}\n\n" for i, entry in enumerate(st.session_state.question_history)])}
"""
            client.beta.threads.messages.create(
                thread_id=st.session_state.quiz_thread_id,
                role="user",
                content=insights_prompt
            )
            run = client.beta.threads.runs.create(
                thread_id=st.session_state.quiz_thread_id,
                assistant_id=ASSISTANT_IDS[st.session_state.selected_course]
            )
            while run.status != "completed":
                time.sleep(1)
                run = client.beta.threads.runs.retrieve(thread_id=st.session_state.quiz_thread_id, run_id=run.id)
            messages = client.beta.threads.messages.list(thread_id=st.session_state.quiz_thread_id)
            summary_text = messages.data[0].content[0].text.value

            st.markdown("### 🧾 Detailed Feedback Summary")
            st.markdown(summary_text)

            score_percent = (correct_count / total) * 100 if total else 0
            subject = f"Quiz Result - {st.session_state.selected_course} ({score_percent:.1f}%)"
            message = f"""Quiz Summary Report
            
            Course: {st.session_state.selected_course}
            Final Score: {correct_count} / {total} ({score_percent:.1f}%)
            Time Taken: {formatted_time}
            Avg Time/Question: {avg_time:.1f} seconds
            
            
            {summary_text}
            """
            send_brevo_email(subject, message)



        st.markdown("---")
        if st.button("🔁 Start Over"):
            for key in [
                "quiz_completed", "quiz_started", "question_history", "question_index",
                "current_question", "question_body", "current_options", "quiz_thread_id",
                "selected_course", "selected_units", "total_questions"
            ]:
                st.session_state[key] = None if key != "quiz_completed" else False
            st.rerun()

        st.stop()

    # === 2. Show Course Selection ===
    courses = {
        "Biology - SBI3U": ["Diversity of Living Things", "Evolution", "Genetic Processes", "Animals: Structure and Function", "Plants: Anatomy, Growth and Function"],
        "Biology - SBI4U": ["Biochemistry", "Metabolic Processes", "Molecular Genetics", "Homeostasis", "Population Dynamics"],
        "Biology - Uni Exam": ["All topics"],
        "Chemistry - SCH3U": ["Matter & Bonding", "Chemical Reactions", "Quantities & Solutions", "Equilibrium", "Atomic Structure"]
    }

    if not st.session_state.get("quiz_started", False):
        selected_course = st.selectbox("Select a course:", list(courses.keys()))
        selected_units = st.multiselect("Select units:", courses[selected_course])
        total_questions = st.selectbox("How many questions?", [10, 20, 30, 40, 50, 60], index=0)

        if selected_units and st.button("🚀 Start Quiz"):
            thread = client.beta.threads.create()
            st.session_state.quiz_thread_id = thread.id
            st.session_state.quiz_started = True
            st.session_state.quiz_completed = False
            st.session_state.selected_course = selected_course
            st.session_state.selected_units = selected_units
            st.session_state.total_questions = total_questions
            st.session_state.question_index = 0
            st.session_state.question_history = []
            st.session_state.start_time = datetime.now()
            st.session_state.ready_for_next_question = False
            st.session_state.current_question = None
            st.rerun()

        st.stop()

    # === 3. Render Active Quiz ===
    if st.session_state.quiz_started and not st.session_state.quiz_completed:
        idx = st.session_state.question_index
        total = st.session_state.total_questions
        course = st.session_state.selected_course
        assistant_id = ASSISTANT_IDS.get(course)
        thread_id = st.session_state.quiz_thread_id

        if not st.session_state.current_question and not st.session_state.ready_for_next_question:
            with st.spinner("🧠 Generating quiz question..."):
                prompt = f"""
Course: {course}
Units: {', '.join(st.session_state.selected_units)}
Question {idx+1} of {total}
Generate a quiz question (MCQ, Short Answer, or Fill-in-the-Blank), include type and options if MCQ.
Do NOT include the answer or hint.
"""
                client.beta.threads.messages.create(thread_id=thread_id, role="user", content=prompt)
                run = client.beta.threads.runs.create(thread_id=thread_id, assistant_id=assistant_id)
                while run.status != "completed":
                    time.sleep(1)
                    run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
                messages = client.beta.threads.messages.list(thread_id=thread_id)
                text = messages.data[0].content[0].text.value

                st.session_state.current_question = text
                lines = text.strip().splitlines()
                body_lines, options = [], []
                for line in lines:
                    if re.match(r"^[A-D][).]?\s", line):
                        options.append(line.strip())
                    else:
                        body_lines.append(line.strip())
                st.session_state.question_body = "\n".join(body_lines)
                st.session_state.current_options = options

        st.subheader(f"❓ Question {idx+1} of {total}")
        st.markdown(st.session_state.question_body)

        if st.session_state.current_options:
            user_answer = st.radio("Choose an answer:", st.session_state.current_options, key=f"mcq_{idx}")
        else:
            user_answer = st.text_area("Your Answer:", key=f"answer_{idx}")

        if st.button("📤 Submit Answer"):
            with st.spinner("💬 Evaluating your answer..."):
                client.beta.threads.messages.create(
                    thread_id=thread_id,
                    role="user",
                    content=f"The student's answer to Question {idx+1} is: {user_answer}. Please say if it's correct, give the correct answer, and explain why."
                )
                run = client.beta.threads.runs.create(thread_id=thread_id, assistant_id=assistant_id)
                while run.status != "completed":
                    time.sleep(1)
                    run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
                messages = client.beta.threads.messages.list(thread_id=thread_id)
                feedback = messages.data[0].content[0].text.value.strip()

                st.success("✅ Feedback:")
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
                if idx + 1 < total:
                    st.session_state.question_index += 1
                    st.session_state.current_question = None
                    st.session_state.ready_for_next_question = False
                    st.rerun()
                else:
                    st.session_state.quiz_started = False
                    st.session_state.quiz_completed = True
                    st.session_state.ready_for_next_question = False
                    st.session_state.current_question = None
                    st.rerun()
