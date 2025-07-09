import streamlit as st
from openai import OpenAI
import time
import pandas as pd
from datetime import datetime

# === Config ===
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
APP_PIN = st.secrets["APP_PIN"]

ASSISTANT_IDS = {
    "Essay": "asst_XQQG6ntdnYNoNW8m222fAbag",
    "Interviewer": "asst_GgZ2Y3WrUrHMDyO1nsGC9N1D"
}

client = OpenAI(api_key=OPENAI_API_KEY)

st.set_page_config(page_title="AI Essay and Interview Practice", layout="centered")
st.title("🎓 AI Entrance Exam Practice")

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
        "reset_app": False
    }
    for key, default in keys_defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default

init_session()

# === Safe Reset Logic ===
if st.session_state.reset_app:
    for key in [
        "essay_thread_id", "essay_prompt", "user_essay", "essay_feedback", "essay_submitted",
        "interview_thread_id", "interview_prompt", "interview_feedback", "interview_response", "interview_submitted"
    ]:
        st.session_state[key] = "" if isinstance(st.session_state[key], str) else None
    st.session_state.reset_app = False
    st.experimental_rerun()

# === Mode Selection ===
mode = st.radio("Select Practice Mode:", ["Practice Essay", "Practice Interview"])

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

# === Start Over Button ===
if st.session_state.essay_submitted or st.session_state.interview_submitted:
    if st.button("🔄 Start Over"):
        st.session_state.reset_app = True
        st.experimental_rerun()
