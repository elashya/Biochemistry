import streamlit as st
from openai import OpenAI
import time
import re
import pandas as pd
from datetime import datetime

# === Config ===
BIOCHEM_ASSISTANT_ID = "asst_uZSql3UUgVbDRKD4jaMXUkU5"
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
APP_PIN = st.secrets["APP_PIN"]

client = OpenAI(api_key=OPENAI_API_KEY)

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

# === Course & Units ===
courses = {
    "Biology": ["Biochemistry", "Metabolic Processes", "Molecular Genetics", "Homeostasis", "Population Dynamics"],
    "Chemistry": ["Matter & Bonding", "Chemical Reactions", "Quantities & Solutions", "Equilibrium", "Atomic Structure"]
}

# === Study Plan Progress Tracker ===
def get_course_progress(course_df, start_date, today):
    days_elapsed = (today - start_date).days
    study_days = days_elapsed // 2
    slides_covered = study_days * 7
    total_slides = course_df["# of slides"].sum()
    slides_remaining = slides_covered
    progress_info = {}

    for _, row in course_df.iterrows():
        unit_slides = row["# of slides"]
        if slides_remaining < unit_slides:
            progress_info = {
                "unit_number": row["Unit#"],
                "unit_title": row["Unit Title"],
                "slide_number": slides_remaining + 1,
                "percent_complete": min(100, round((slides_covered / total_slides) * 100, 1))
            }
            break
        slides_remaining -= unit_slides

    if not progress_info:
        last_row = course_df.iloc[-1]
        progress_info = {
            "unit_number": last_row["Unit#"],
            "unit_title": last_row["Unit Title"],
            "slide_number": last_row["# of slides"],
            "percent_complete": 100.0
        }

    return progress_info

@st.cache_data
def load_study_data():
    return pd.read_excel("study_plan.xlsx")

if not st.session_state.quiz_started:
    df = load_study_data()
    bio_df = df[df["Course"].str.lower().str.contains("bio")]
    chem_df = df[df["Course"].str.lower() == "chemistry"]
    start_date = datetime(2025, 6, 12)
    today = datetime.today()
    bio_progress = get_course_progress(bio_df, start_date, today)
    chem_progress = get_course_progress(chem_df, start_date, today)

    start_date = st.date_input("📅 Select your study start date:", datetime(2025, 6, 14))
start_date = datetime.combine(start_date, datetime.min.time())

bio_df = df[df["Course"] == "biology"]
chem_df = df[df["Course"] == "chemistry"]

today = datetime.today()
bio_progress = get_course_progress(bio_df, start_date, today)
chem_progress = get_course_progress(chem_df, start_date, today)

bio_total_slides = bio_df["# of slides"].sum()
chem_total_slides = chem_df["# of slides"].sum()
bio_days_needed = (bio_total_slides + 6) // 7
chem_days_needed = (chem_total_slides + 6) // 7
bio_completion_date = start_date + pd.Timedelta(days=bio_days_needed * 2)
chem_completion_date = start_date + pd.Timedelta(days=chem_days_needed * 2)
estimated_completion_date = start_date + pd.Timedelta(days=estimated_completion_days)

st.markdown(f"""
### 👋 Assalamu Alaikum, Sohail!

Welcome back to your personal revision coach. You're on the path to an **A+**, insha’Allah. Let's sharpen your science skills!

#### 📊 Progress Stats
- **Biology:** Unit {bio_progress['unit_number']} – {bio_progress['unit_title']}, Slide {bio_progress['slide_number']} ({bio_progress['percent_complete']}%)
- **Chemistry:** Unit {chem_progress['unit_number']} – {chem_progress['unit_title']}, Slide {chem_progress['slide_number']} ({chem_progress['percent_complete']}%)

📅 **Expected Completion Dates**
- 🧬 Biology: {bio_completion_date.strftime('%A, %d %B %Y')}
- ⚗️ Chemistry: {chem_completion_date.strftime('%A, %d %B %Y')}
""")

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
