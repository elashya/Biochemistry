import streamlit as st
from openai import OpenAI
import time
import re
import pandas as pd
from datetime import datetime, timedelta
import hashlib
import os
import json
import matplotlib.pyplot as plt


# === Config ===
BIOCHEM_ASSISTANT_ID = "asst_uZSql3UUgVbDRKD4jaMXUkU5"
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
DATA_DIR = "user_data"

client = OpenAI(api_key=OPENAI_API_KEY)

st.set_page_config(page_title="AI BioChem Tutor", layout="centered")

# === Local Login Auth ===
USERS = {
    "mohamad": hashlib.sha256("M2013".encode()).hexdigest(),
    "sohail": hashlib.sha256("S2009".encode()).hexdigest(),
}

if "user_id" not in st.session_state:
    st.session_state.user_id = None

if st.session_state.user_id is None:
    st.subheader("🔐 Local Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        hashed = hashlib.sha256(password.encode()).hexdigest()
        if USERS.get(username) == hashed:
            st.session_state.user_id = username
            st.success(f"✅ Welcome, {username}!")
            st.rerun()
        else:
            st.error("❌ Invalid username or password")
    st.stop()
    
st.markdown("### 🗃️ View User Data File")
selected_user_file = st.selectbox("Choose user file to view:", os.listdir("user_data"))

if selected_user_file.endswith(".json"):
    filepath = os.path.join("user_data", selected_user_file)
    with open(filepath, "r") as f:
        content = json.load(f)
    st.json(content)
    
# === Load/Save User Progress ===
def load_user_progress(user_id):
    filepath = os.path.join(DATA_DIR, f"{user_id}.json")
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            return json.load(f)
    return {"quiz_history": [], "master_report": ""}

def save_user_progress(user_id, quiz_data, master_report=None):
    os.makedirs(DATA_DIR, exist_ok=True)
    filepath = os.path.join(DATA_DIR, f"{user_id}.json")
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            data = json.load(f)
    else:
        data = {"quiz_history": [], "master_report": ""}
    data["quiz_history"].append(quiz_data)
    if master_report:
        data["master_report"] = master_report
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)

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
    "Biology": ["Biochemistry", "Metabolic Processes", "Molecular Genetics", "Homeostasis", "Population Dynamics"],
    "Chemistry": ["Matter & Bonding", "Chemical Reactions", "Quantities & Solutions", "Equilibrium", "Atomic Structure"]
}

# === Main Interface (Pre-Quiz) ===
if not st.session_state.quiz_started:
    st.title("🧪 AI Biology & Chemistry Tutor")
    st.markdown(f"### 👤 Welcome, **{st.session_state.user_id}**")

    # 1. Quiz History
    user_data = load_user_progress(st.session_state.user_id)
    with st.expander("🗂️ Your Quiz History", expanded=False):
        df = pd.DataFrame(user_data.get("quiz_history", [])[::-1])
        if not df.empty:
            df = df[["quiz_date", "course", "units", "time_taken", "final_mark"]]
            df.columns = ["Date", "Course", "Units", "Time", "Mark"]
            df.index.name = "#"
            st.dataframe(df, use_container_width=True)

    # 2. Study Plan & Progress
    df = load_study_data()
    df["Course"] = df["Course"].str.lower().replace({"intro": "biology", "bilology": "biology"})
    bio_df = df[df["Course"] == "biology"]
    chem_df = df[df["Course"] == "chemistry"]

    if bio_df.empty or chem_df.empty:
        st.error("❌ Could not load Biology or Chemistry content from the sheet. Please check formatting.")
        st.stop()

    start_date = datetime(2025, 6, 14)
    today = datetime.today()
    days_elapsed = (today - start_date).days
    slides_completed = (days_elapsed // 2) * 7

    bio_progress = compute_progress(bio_df, slides_completed)
    chem_progress = compute_progress(chem_df, slides_completed)

    bio_completion_date = start_date + timedelta(days=((bio_df["# of slides"].sum() + 6) / 7) * 2)
    chem_completion_date = start_date + timedelta(days=((chem_df["# of slides"].sum() + 6) / 7) * 2)

    with st.expander("📊 This is your expected progress point:", expanded=False):
        st.markdown(f"- 🧬 **Biology:** Unit {bio_progress['unit_number']} – {bio_progress['unit_title']}, Slide {bio_progress['slide_number']}")
        bio_col1, bio_col2, bio_col3 = st.columns([1, 4, 3])
        with bio_col1:
            st.markdown(f"**{bio_progress['percent_complete']}%**")
        with bio_col2:
            st.progress(int(bio_progress['percent_complete']))
        with bio_col3:
            st.markdown(f"📅 {bio_completion_date.strftime('%A, %d %B %Y')}")

        st.markdown(f"- ⚗️ **Chemistry:** Unit {chem_progress['unit_number']} – {chem_progress['unit_title']}, Slide {chem_progress['slide_number']}")
        chem_col1, chem_col2, chem_col3 = st.columns([1, 4, 3])
        with chem_col1:
            st.markdown(f"**{chem_progress['percent_complete']}%**")
        with chem_col2:
            st.progress(int(chem_progress['percent_complete']))
        with chem_col3:
            st.markdown(f"📅 {chem_completion_date.strftime('%A, %d %B %Y')}")

    # 3. Cumulative Master Performance Report
    with st.expander("🧠 Cumulative Performance Insights", expanded=False):
        master_report = user_data.get("master_report", "")
        if master_report:
            st.markdown(master_report)
        else:
            st.info("📌 No cumulative performance insights yet. Complete a quiz to generate one.")


    # 5. Course + Units + Quiz Config
    st.markdown("### 🎯 What are we revising today to get that A+ ?")
    selected_course = st.selectbox("Select a course:", list(courses.keys()))
    st.session_state.selected_course = selected_course

    selected_units = st.multiselect("Select one or more units:", courses[selected_course])
    st.session_state.selected_units = selected_units

    total_qs = st.selectbox("Select total number of questions:", [3, 10, 15, 20, 25, 30], index=1)
    st.session_state.total_questions = total_qs

    if selected_units and st.button("🚀 Start Quiz"):
        thread = client.beta.threads.create()
        st.session_state.quiz_thread_id = thread.id
        st.session_state.quiz_started = True
        st.session_state.question_index = 0
        st.session_state.question_history = []
        st.session_state.start_time = datetime.now()
        st.session_state.timestamps = []
        st.rerun()



# === Generate Master Performance Summary ===
def generate_master_performance(user_id):
    filepath = os.path.join(DATA_DIR, f"{user_id}.json")
    if not os.path.exists(filepath):
        return None
    with open(filepath, "r") as f:
        data = json.load(f)

    summary_counts = {}
    all_units = []

    for entry in data.get("quiz_history", []):
        units = entry.get("units", [])
        mark = entry.get("final_mark", "N/A")
        if isinstance(units, list):
            for unit in units:
                summary_counts.setdefault(unit, {"attempts": 0, "total": 0})
                summary_counts[unit]["attempts"] += 1
                try:
                    score, total = map(int, re.findall(r"(\d+)", mark))
                    summary_counts[unit]["total"] += score
                except:
                    pass
                all_units.append(unit)

    if not summary_counts:
        return None

    insights = "### 📈 Cumulative Performance Summary\n"
    insights += f"- Total Quizzes Taken: {len(data.get('quiz_history', []))}\n\n"

    for unit, stats in summary_counts.items():
        avg_score = stats["total"] / stats["attempts"]
        insights += f"- **{unit}**: Attempted {stats['attempts']} times, Avg Score: {avg_score:.1f}\n"

    # Optional: Chart
    try:
        st.markdown("#### 📊 Average Score per Unit")
        df_chart = pd.DataFrame({
            "Unit": list(summary_counts.keys()),
            "Avg Score": [v["total"] / v["attempts"] for v in summary_counts.values()]
        })
        fig, ax = plt.subplots()
        ax.bar(df_chart["Unit"], df_chart["Avg Score"], color="skyblue")
        ax.set_ylabel("Avg Score")
        ax.set_title("Avg Performance by Unit")
        st.pyplot(fig)
    except:
        pass

    return insights
# === Generate Master Performance Summary ===
def generate_master_performance(user_id):
    filepath = os.path.join(DATA_DIR, f"{user_id}.json")
    if not os.path.exists(filepath):
        return "📌 No cumulative performance insights yet. Complete a quiz to generate one."

    with open(filepath, "r") as f:
        data = json.load(f)
    
    quiz_history = data.get("quiz_history", [])
    if not quiz_history:
        return "📌 No cumulative performance insights yet. Complete a quiz to generate one."

    # Collect performance data
    unit_stats = {}
    total_score = 0
    total_possible = 0

    for record in quiz_history:
        mark = record.get("final_mark", "0/0")
        try:
            score, out_of = map(int, re.findall(r"\d+", mark))
            total_score += score
            total_possible += out_of
        except:
            continue
        
        for unit in record.get("units", []):
            if unit not in unit_stats:
                unit_stats[unit] = {"score": 0, "out_of": 0}
            unit_stats[unit]["score"] += score
            unit_stats[unit]["out_of"] += out_of

    if total_possible == 0:
        return "📌 No valid marks yet to summarize performance."

    # Build markdown + chart
    markdown = "## 📈 Master Performance Report\n"
    markdown += f"**Overall Accuracy:** `{round((total_score / total_possible) * 100, 1)}%`\n\n"
    markdown += "**Unit-wise Performance:**\n"

    chart_data = []
    for unit, stats in unit_stats.items():
        percent = round((stats["score"] / stats["out_of"]) * 100, 1)
        markdown += f"- `{unit}`: {percent}% ({stats['score']}/{stats['out_of']})\n"
        chart_data.append({"Unit": unit, "Accuracy (%)": percent})

    # Plot chart
    if chart_data:
        df_chart = pd.DataFrame(chart_data)
        st.bar_chart(df_chart.set_index("Unit"))

    return markdown

# === Save Progress After Quiz ===
if st.session_state.quiz_started and st.session_state.score_summary:
    duration = datetime.now() - st.session_state.start_time
    seconds = int(duration.total_seconds())
    avg_time = seconds / st.session_state.total_questions
    formatted = str(duration).split('.')[0]

    quiz_record = {
        "quiz_date": datetime.now().isoformat(),
        "course": st.session_state.selected_course,
        "units": st.session_state.selected_units,
        "total_questions": st.session_state.total_questions,
        "time_taken": formatted,
        "avg_time_sec": round(avg_time, 1),
        "summary": st.session_state.score_summary,
    }

    match = re.search(r"(\d+)\s*(?:/|out of)\s*(\d+)", st.session_state.score_summary, re.IGNORECASE)
    if match:
        quiz_record["final_mark"] = f"{match.group(1)}/{match.group(2)}"
    else:
        quiz_record["final_mark"] = "N/A"

    save_user_progress(st.session_state.user_id, quiz_record)

    # Update master performance after saving quiz
    cumulative_summary = generate_master_performance(st.session_state.user_id)
    st.session_state.master_performance_summary = cumulative_summary


    cumulative_summary = generate_master_performance(st.session_state.user_id)
    st.session_state.master_performance_summary = cumulative_summary

    # === Update master performance summary ===
    user_data_path = f"user_data/{st.session_state.user_id}.json"
    if os.path.exists(user_data_path):
        with open(user_data_path, "r") as f:
            user_data = json.load(f)

        if "quiz_history" in user_data and len(user_data["quiz_history"]) >= 3:
            history_for_prompt = "\n\n".join([entry["summary"] for entry in user_data["quiz_history"]])
            perf_prompt = f"""Based on the following past quiz performance summaries, generate a master performance report for Sohail that includes:
- Key strengths (tagged by topic)
- Areas to improve (grouped by patterns or repetition)
- Suggested study strategy moving forward
- Motivational tone

Past Summaries:
{history_for_prompt}
"""

            perf_response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a wise and encouraging high school science tutor."},
                    {"role": "user", "content": perf_prompt}
                ]
            )

            user_data["master_performance_summary"] = perf_response.choices[0].message.content
            with open(user_data_path, "w") as f:
                json.dump(user_data, f, indent=2)

# === Quiz Loop ===
elif st.session_state.quiz_started:
    idx = st.session_state.question_index
    thread_id = st.session_state.quiz_thread_id
    total = st.session_state.total_questions

    if st.session_state.start_time:
        elapsed = datetime.now() - st.session_state.start_time
        st.info(f"⏱️ Time Elapsed: **{str(elapsed).split('.')[0]}**")

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
        with st.spinner("🧠 Tutor is preparing a question..."):
            client.beta.threads.messages.create(thread_id=thread_id, role="user", content=prompt)
            run = client.beta.threads.runs.create(thread_id=thread_id, assistant_id=BIOCHEM_ASSISTANT_ID)
            while run.status != "completed":
                time.sleep(1)
                run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
            messages = client.beta.threads.messages.list(thread_id=thread_id)
            full_text = messages.data[0].content[0].text.value
            st.session_state.current_question = full_text
            st.session_state.timestamps.append(datetime.now())

            # Improved MCQ Detection
            lines = full_text.strip().splitlines()
            body_lines, options = [], []
            for line in lines:
                if re.match(r"^[A-Da-d][).]?\s", line):
                    options.append(line.strip())
                else:
                    body_lines.append(line.strip())
            st.session_state.question_body = "\n".join(body_lines).strip()
            st.session_state.current_options = options
            is_mcq = len(options) >= 2
            st.session_state.is_mcq = is_mcq
            st.session_state.question_type = "MCQ" if is_mcq else "Short Answer"

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
                run = client.beta.threads.runs.create(thread_id=thread_id, assistant_id=BIOCHEM_ASSISTANT_ID)
                while run.status != "completed":
                    time.sleep(1)
                    run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
                messages = client.beta.threads.messages.list(thread_id=thread_id)
                feedback = messages.data[0].content[0].text.value
                feedback = re.sub(r"(?i)(The provided answer is incorrect\\.)", r":red[\\1]", feedback)
                st.success("🧠 Feedback from Tutor")
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
            run = client.beta.threads.runs.create(thread_id=thread_id, assistant_id=BIOCHEM_ASSISTANT_ID)
            while run.status != "completed":
                time.sleep(1)
                run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
            messages = client.beta.threads.messages.list(thread_id=thread_id)
            st.session_state.score_summary = messages.data[0].content[0].text.value
        st.subheader("📊 Final Tutor Report")
        st.markdown(st.session_state.score_summary)

        if st.button("🔁 Start Over"):
            st.session_state.start_over = True
            st.rerun()
        
        # Handle session reset cleanly on next run
        if st.session_state.get("start_over"):
            user_id = st.session_state.get("user_id")
            st.session_state.clear()
            st.session_state["user_id"] = user_id
            st.session_state["start_over"] = False
            st.rerun()

