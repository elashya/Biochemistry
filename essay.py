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

st.set_page_config(page_title="AI Essay Practice", layout="centered")
st.title("📝 AI Essay Practice Assistant")

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
        "essay_submitted": False
    }
    for key, default in keys_defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default

init_session()

# === Main Interface ===
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

# === Essay Section ===
if st.session_state.essay_prompt:
    st.subheader("🧾 Essay Prompt")
    st.markdown(st.session_state.essay_prompt)

    st.subheader("✍️ Write Your Essay")
    st.session_state.user_essay = st.text_area("Paste or type your response here:", height=300)

    if st.button("📤 Submit Essay"):
        with st.spinner("📚 Evaluating your essay..."):
            try:
                # Step 1: Send essay to thread
                client.beta.threads.messages.create(
                    thread_id=st.session_state.essay_thread_id,
                    role="user",
                    content=f"Here is the student's essay:\n\n{st.session_state.user_essay}\n\nPlease evaluate it using university entrance standards and give feedback and a mark out of 100."
                )

                # Step 2: Start assistant run
                run = client.beta.threads.runs.create(
                    thread_id=st.session_state.essay_thread_id,
                    assistant_id=ASSISTANT_IDS["Essay"]
                )

                # Step 3: Wait until run completes or timeout
                max_wait = 60  # increased from 30
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
                    # Step 4: Get response
                    messages = client.beta.threads.messages.list(thread_id=st.session_state.essay_thread_id)

                    if messages.data and messages.data[0].content:
                        feedback = messages.data[0].content[0].text.value.strip()
                        st.session_state.essay_feedback = feedback
                        st.session_state.essay_submitted = True
                        st.success("✅ Essay evaluated successfully!")
                        st.markdown("### 📋 Feedback")
                        st.markdown(feedback)
                    else:
                        st.error("⚠️ No feedback was returned. Please try again.")

            except Exception as e:
                st.error(f"❌ Error during evaluation: {e}")

            try:
                # Step 1: Send essay to thread
                client.beta.threads.messages.create(
                    thread_id=st.session_state.essay_thread_id,
                    role="user",
                    content=f"Here is the student's essay:\n\n{st.session_state.user_essay}\n\nPlease evaluate it using university entrance standards and give feedback and a mark out of 100."
                )

                # Step 2: Start assistant run
                run = client.beta.threads.runs.create(
                    thread_id=st.session_state.essay_thread_id,
                    assistant_id=ASSISTANT_IDS["Essay"]
                )

                # Step 3: Wait until run completes or timeout
                max_wait = 30  # seconds
                start_time = time.time()
                while run.status not in ["completed", "failed", "cancelled"]:
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
                    # Step 4: Get response
                    messages = client.beta.threads.messages.list(thread_id=st.session_state.essay_thread_id)
                    feedback = messages.data[0].content[0].text.value.strip()
                    st.session_state.essay_feedback = feedback
                    st.session_state.essay_submitted = True

            except Exception as e:
                st.error(f"❌ Error during evaluation: {e}")

