import streamlit as st
from openai import OpenAI
import time
import pandas as pd
from datetime import datetime
import re
import requests

# ============================
# Utility: Markdown + LaTeX
# ============================

def render_markdown_with_latex_blocks(text):
    """
    Renders clean LaTeX blocks in the text using \( ... \) or $$ ... $$.
    Avoids rendering square-bracketed expressions like [ ... ].
    """
    import re

    pattern = r"\\\((.*?)\\\)|\$\$(.*?)\$\$"
    matches = list(re.finditer(pattern, text, re.DOTALL))
    last_end = 0

    for match in matches:
        start, end = match.start(), match.end()
        if last_end < start:
            part = text[last_end:start].strip()
            if part:
                st.markdown(part)
        latex_expr = match.group(1) or match.group(2)
        if latex_expr:
            st.latex(latex_expr.strip())
        last_end = end

    if last_end < len(text):
        part = text[last_end:].strip()
        if part:
            st.markdown(part)

# ============================
# Email via Brevo
# ============================

RECIPIENT_EMAIL = "ahmed03@hotmail.com"

def send_brevo_email(subject, message_text):
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "api-key": st.secrets["BREVO_API_KEY"],
    }
    data = {
        "sender": {"name": "AI Tutor", "email": st.secrets["SENDER_EMAIL"]},
        "to": [{"email": RECIPIENT_EMAIL}],
        "subject": subject,
        "textContent": message_text,
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 201:
        st.success("📧 Result sent to your inbox.")
    else:
        st.error(f"❌ Failed to send email: {response.status_code} — {response.text}")

# ============================
# Config & Client
# ============================

OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
APP_PIN = st.secrets["APP_PIN"]

ASSISTANT_IDS = {
    "Biology - SBI3U": "asst_QxWwAb8wjBkzUxHehzpmlp8Z",
    "Biology - SBI4U": "asst_t9vrqxAau5LWqOSR9bmm1egb",
    "Semmelwise  - Bio": "asst_6X4Btqc3rNXYyH0iwMZAHiau",
    "Chemistry - SCH3U": "asst_4RzhLQqUFGni8leY61N7Nw14",
    "Debrecen - Chem": "asst_q04IFQBRID5LJxYPXBBfhFlx",
    "Debrecen - Bio": "asst_Pp6HpUWNIXHLOhRmX89EddAx",
    "Essay": "asst_XQQG6ntdnYNoNW8m222fAbag",
    # 🔧 Add your real Interview assistant id here or inject via secrets
    "Interviewer": st.secrets.get("INTERVIEW_ASSISTANT_ID", "asst_REPLACE_ME_INTERVIEWER"),
}

client = OpenAI(api_key=OPENAI_API_KEY)

st.set_page_config(page_title="AI Essay and Interview Practice", layout="centered")
st.title("\U0001F393 AI Entrance Exam Practice")

# ============================
# Helpers: Threads & Content
# ============================

def ensure_thread_id(key: str) -> str:
    """Ensure we have a live thread id stored at st.session_state[key]."""
    tid = st.session_state.get(key)
    if not tid:
        tid = client.beta.threads.create().id
        st.session_state[key] = tid
    return tid


def safe_content(s: str):
    s = (s or "").strip()
    if not s:
        raise ValueError("Empty content for assistant message.")
    return [{"type": "text", "text": s}]


def get_latest_assistant_text(thread_id: str) -> str:
    """Return the newest assistant message text or raise a clear error."""
    msgs = client.beta.threads.messages.list(thread_id=thread_id).data
    for m in msgs:
        if m.role == "assistant" and m.content and len(m.content) > 0:
            block = m.content[0]
            if getattr(block, "type", "") == "text":
                return block.text.value
    raise RuntimeError("No assistant message found yet. Try again.")


def wait_for_run(thread_id: str, run_id: str, max_wait: int = 60):
    start = time.time()
    while True:
        run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run_id)
        if run.status in ("completed", "failed", "cancelled"):
            return run
        if time.time() - start > max_wait:
            raise TimeoutError("⚠️ Assistant evaluation took too long.")
        time.sleep(1)

# ============================
# PIN Authentication
# ============================

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

# ============================
# Session Initialization
# ============================

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
        "timestamps": [],
        # Quiz
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
        "question_body": "",
    }
    for key, default in keys_defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default

init_session()

# ============================
# Reset Logic
# ============================

if st.session_state.get("reset_app", False):
    for key in [
        "essay_thread_id", "essay_prompt", "user_essay", "essay_feedback", "essay_submitted",
        "interview_thread_id", "interview_prompt", "interview_feedback", "interview_response", "interview_submitted",
    ]:
        st.session_state[key] = "" if isinstance(st.session_state[key], str) else None
    st.session_state.reset_app = False
    st.rerun()

# ============================
# Mode Selection
# ============================

if not st.session_state.quiz_started and not st.session_state.quiz_completed:
    mode = st.radio("Select Practice Mode:", ["Practice Essay", "Practice Interview", "Practice Quiz"])
    st.session_state.mode = mode
else:
    mode = st.session_state.get("mode", "Practice Quiz")

# ============================
# Practice Essay
# ============================

if mode == "Practice Essay":
    st.markdown("### ✨ Practice Essay Writing")

    if not st.session_state.essay_prompt:
        if st.button("✍️ Get Essay Prompt"):
            try:
                tid = ensure_thread_id("essay_thread_id")
                client.beta.threads.messages.create(
                    thread_id=tid,
                    role="user",
                    content=safe_content(
                        "Give me one structured essay prompt related to physiotherapy, suitable for university entrance motivation letter practice."
                    ),
                )
                run = client.beta.threads.runs.create(thread_id=tid, assistant_id=ASSISTANT_IDS["Essay"])
                run = wait_for_run(tid, run.id)
                if run.status != "completed":
                    st.error(f"❌ Assistant run failed with status: {run.status}")
                else:
                    prompt_text = get_latest_assistant_text(tid)
                    st.session_state.essay_prompt = prompt_text
                    st.session_state.essay_submitted = False
                    st.session_state.user_essay = ""
                    st.session_state.essay_feedback = ""
            except Exception as e:
                msg = getattr(e, "message", str(e))
                st.error(f"❌ Error generating essay prompt: {msg}")

    if st.session_state.essay_prompt:
        st.subheader("🧾 Essay Prompt")
        st.markdown(st.session_state.essay_prompt)

        st.subheader("✍️ Write Your Essay")
        st.session_state.user_essay = st.text_area("Paste or type your response here:", height=300)

        if st.button("📤 Submit Essay"):
            if not st.session_state.user_essay.strip():
                st.warning("Please write your essay before submitting.")
                st.stop()
            try:
                tid = ensure_thread_id("essay_thread_id")
                client.beta.threads.messages.create(
                    thread_id=tid,
                    role="user",
                    content=safe_content(
                        f"Here is the student's essay:\n\n{st.session_state.user_essay}\n\nPlease evaluate it using university entrance standards and give feedback and a mark out of 100."
                    ),
                )
                run = client.beta.threads.runs.create(thread_id=tid, assistant_id=ASSISTANT_IDS["Essay"])
                run = wait_for_run(tid, run.id)
                if run.status != "completed":
                    st.error(f"❌ Assistant run failed with status: {run.status}")
                else:
                    feedback = get_latest_assistant_text(tid).strip()
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
                msg = getattr(e, "message", str(e))
                st.error(f"❌ Error during evaluation: {msg}")

# ============================
# Practice Interview
# ============================

elif mode == "Practice Interview":
    st.markdown("### 🎤 Practice Interview Questions")

    if not st.session_state.interview_prompt:
        if st.button("🎯 Get Interview Question"):
            try:
                tid = ensure_thread_id("interview_thread_id")
                client.beta.threads.messages.create(
                    thread_id=tid,
                    role="user",
                    content=safe_content("Ask me one physiotherapy university admission interview question."),
                )
                run = client.beta.threads.runs.create(thread_id=tid, assistant_id=ASSISTANT_IDS["Interviewer"])
                run = wait_for_run(tid, run.id)
                if run.status != "completed":
                    st.error(f"❌ Assistant run failed with status: {run.status}")
                else:
                    question_text = get_latest_assistant_text(tid)
                    st.session_state.interview_prompt = question_text
                    st.session_state.interview_response = ""
                    st.session_state.interview_feedback = ""
                    st.session_state.interview_submitted = False
            except Exception as e:
                msg = getattr(e, "message", str(e))
                st.error(f"❌ Error generating interview question: {msg}")

    if st.session_state.interview_prompt:
        st.subheader("🎙️ Interview Question")
        st.markdown(st.session_state.interview_prompt)

        st.subheader("🧑‍🎓 Your Response")
        st.session_state.interview_response = st.text_area("Type your answer here:", height=200)

        if st.button("📤 Submit Interview Response"):
            if not st.session_state.interview_response.strip():
                st.warning("Please type your response before submitting.")
                st.stop()
            try:
                tid = ensure_thread_id("interview_thread_id")
                client.beta.threads.messages.create(
                    thread_id=tid,
                    role="user",
                    content=safe_content(
                        f"Here is my interview response:\n\n{st.session_state.interview_response}\n\nPlease give me feedback as if you're an admission officer."
                    ),
                )
                run = client.beta.threads.runs.create(thread_id=tid, assistant_id=ASSISTANT_IDS["Interviewer"])
                run = wait_for_run(tid, run.id)
                if run.status != "completed":
                    st.error(f"❌ Assistant run failed with status: {run.status}")
                else:
                    feedback = get_latest_assistant_text(tid).strip()
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
                msg = getattr(e, "message", str(e))
                st.error(f"❌ Error during evaluation: {msg}")

# ============================
# Practice Quiz
# ============================

elif mode == "Practice Quiz":
    # 1) Completed summary
    if st.session_state.get("quiz_completed"):
        st.markdown("## 🎉 Quiz Completed!")
        end_time = datetime.now()
        duration = end_time - st.session_state.start_time
        total_seconds = int(duration.total_seconds())
        formatted_time = str(duration).split(".")[0]
        avg_time = (
            total_seconds / st.session_state.total_questions if st.session_state.total_questions else 0
        )

        total = st.session_state.total_questions
        correct_count = sum(
            1 for q in st.session_state.question_history if re.search(r"\b(✅|correct)\b", q["feedback"].lower())
        )
        score_percent = (correct_count / total) * 100 if total else 0

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
            try:
                tid = ensure_thread_id("quiz_thread_id")
                client.beta.threads.messages.create(
                    thread_id=tid, role="user", content=safe_content(insights_prompt)
                )
                run = client.beta.threads.runs.create(
                    thread_id=tid, assistant_id=ASSISTANT_IDS[st.session_state.selected_course]
                )
                run = wait_for_run(tid, run.id)
                summary_text = get_latest_assistant_text(tid)

                total = st.session_state.total_questions
                score_percent = (correct_count / total) * 100 if total else 0
                formatted_time = str(duration).split(".")[0]
                avg_time = total_seconds / total if total else 0

                st.markdown("### 🧾 Detailed Feedback Summary")
                st.markdown(summary_text)

                subject = f"Quiz Result - {st.session_state.selected_course} ({score_percent:.1f}%)"
                message = f"""📊 Quiz Summary Report

Course: {st.session_state.selected_course}
Final Score: {correct_count} / {total} ({score_percent:.1f}%)
Score Percentage: {score_percent:.1f}%
Time Taken: {formatted_time}
Avg Time/Question: {avg_time:.1f} seconds

Detailed Feedback:
{summary_text}
"""
                send_brevo_email(subject, message)
            except Exception as e:
                msg = getattr(e, "message", str(e))
                st.error(f"❌ Error generating summary: {msg}")

        st.markdown("---")
        if st.button("🔁 Start Over"):
            for key in [
                "quiz_completed",
                "quiz_started",
                "question_history",
                "question_index",
                "current_question",
                "question_body",
                "current_options",
                "quiz_thread_id",
                "selected_course",
                "selected_units",
                "total_questions",
            ]:
                st.session_state[key] = None if key != "quiz_completed" else False
            st.rerun()

        st.stop()

    # 2) Course selection
    courses = {
        "Biology - SBI3U": [
            "Diversity of Living Things",
            "Evolution",
            "Genetic Processes",
            "Animals: Structure and Function",
            "Plants: Anatomy, Growth and Function",
        ],
        "Biology - SBI4U": [
            "Biochemistry",
            "Metabolic Processes",
            "Molecular Genetics",
            "Homeostasis",
            "Population Dynamics",
        ],
        "Chemistry - SCH3U": [
            "Matter & Bonding",
            "Chemical Reactions",
            "Quantities & Solutions",
            "Equilibrium",
            "Atomic Structure",
        ],
        "Semmelwise  - Bio": ["All topics"],
        "Debrecen - Bio": ["All topics"],
        "Debrecen - Chem": ["All topics"],
    }

    if not st.session_state.get("quiz_started", False):
        selected_course = st.selectbox("Select a course:", list(courses.keys()))
        selected_units = st.multiselect("Select units:", courses[selected_course])
        total_questions = st.selectbox("How many questions?", [3, 10, 20, 30, 40, 50, 60], index=0)

        if selected_units and st.button("🚀 Start Quiz"):
            tid = ensure_thread_id("quiz_thread_id")
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

    # 3) Active quiz
    if st.session_state.quiz_started and not st.session_state.quiz_completed:
        idx = st.session_state.question_index
        total = st.session_state.total_questions
        course = st.session_state.selected_course
        assistant_id = ASSISTANT_IDS.get(course)
        thread_id = ensure_thread_id("quiz_thread_id")

        if not st.session_state.current_question and not st.session_state.ready_for_next_question:
            with st.spinner("🧠 Generating quiz question..."):
                prompt = f"""
Course: {course}
Units: {', '.join(st.session_state.selected_units)}
Question {idx+1} of {total}
Generate a quiz question (MCQ, Short Answer, or Fill-in-the-Blank), include type and options if MCQ.
Do NOT include the answer or hint.
"""
                try:
                    client.beta.threads.messages.create(
                        thread_id=thread_id, role="user", content=safe_content(prompt)
                    )
                    run = client.beta.threads.runs.create(thread_id=thread_id, assistant_id=assistant_id)
                    run = wait_for_run(thread_id, run.id)
                    text = get_latest_assistant_text(thread_id)

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
                except Exception as e:
                    msg = getattr(e, "message", str(e))
                    st.error(f"❌ Error generating question: {msg}")
                    st.stop()

        st.subheader(f"❓ Question {idx+1} of {total}")
        st.markdown(st.session_state.question_body)

        if st.session_state.current_options:
            user_answer = st.radio("Choose an answer:", st.session_state.current_options, key=f"mcq_{idx}")
        else:
            user_answer = st.text_area("Your Answer:", key=f"answer_{idx}")

        if st.button("📤 Submit Answer"):
            with st.spinner("💬 Evaluating your answer..."):
                clean_answer = str(user_answer).strip() if user_answer else "No answer provided"
                if len(clean_answer) > 1000:
                    st.warning("⚠️ Your answer is too long. Please shorten it before submitting.")
                    st.stop()
                try:
                    client.beta.threads.messages.create(
                        thread_id=thread_id,
                        role="user",
                        content=safe_content(
                            f"The student's answer to Question {idx+1} is: {clean_answer}. Please say if it's correct, give the correct answer, and explain why."
                        ),
                    )
                    run = client.beta.threads.runs.create(thread_id=thread_id, assistant_id=assistant_id)
                    run = wait_for_run(thread_id, run.id)
                    feedback = get_latest_assistant_text(thread_id).strip()

                    st.success("✅ Feedback:")
                    st.markdown(feedback)

                    st.session_state.question_history.append(
                        {"question": st.session_state.current_question, "answer": user_answer, "feedback": feedback}
                    )
                    st.session_state.ready_for_next_question = True
                except Exception as e:
                    msg = getattr(e, "message", str(e))
                    st.error(f"❌ Error evaluating answer: {msg}")

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
