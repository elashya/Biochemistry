import streamlit as st
from openai import OpenAI
import time
import re
import pandas as pd
from datetime import datetime, timedelta

# === Config ===
BIOCHEM_ASSISTANT_ID = "asst_uZSql3UUgVbDRKD4jaMXUkU5"
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
APP_PIN = st.secrets["APP_PIN"]

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
        if cumulative + row["# of slides"] >= slides_completed:
            slide_within = slides_completed - cumulative
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

# === Load Progress and Show Stats ===
if not st.session_state.quiz_started:
    df = load_study_data()
    df["Course"] = df["Course"].replace({"Intro": "Biology", "Bilology": "Biology"})
    bio_df = df[df["Course"] == "Biology"]
    chem_df = df[df["Course"] == "Chemistry"]

    start_date = datetime(2025, 6, 14)
    today = datetime.today()
    days_elapsed = (today - start_date).days
    slides_completed = (days_elapsed // 2) * 7

    bio_progress = compute_progress(bio_df, slides_completed)
    chem_progress = compute_progress(chem_df, slides_completed)

    bio_total_slides = bio_df["# of slides"].sum()
    chem_total_slides = chem_df["# of slides"].sum()

    bio_days_needed = (bio_total_slides + 6) // 7
    chem_days_needed = (chem_total_slides + 6) // 7
    bio_completion_date = start_date + timedelta(days=bio_days_needed * 2)
    chem_completion_date = start_date + timedelta(days=chem_days_needed * 2)

    st.markdown("""
    ### 👋 Assalamu Alaikum, Sohail!

    Welcome back to your personal revision coach. You're on the path to an **A+**, insha’Allah. Let's sharpen your science skills!

    ### 📊 Here is your expected progress status:
    - **Biology:** Unit {unit_bio} – {title_bio}, Slide {slide_bio} ({pct_bio}%)
    - **Chemistry:** Unit {unit_chem} – {title_chem}, Slide {slide_chem} ({pct_chem}%)

    ### 📅 Expected Completion Dates
    - 🧬 **Biology:** {bio_date}
    - ⚗️ **Chemistry:** {chem_date}
    """.format(
        unit_bio=bio_progress['unit_number'],
        title_bio=bio_progress['unit_title'],
        slide_bio=bio_progress['slide_number'],
        pct_bio=bio_progress['percent_complete'],
        unit_chem=chem_progress['unit_number'],
        title_chem=chem_progress['unit_title'],
        slide_chem=chem_progress['slide_number'],
        pct_chem=chem_progress['percent_complete'],
        bio_date=bio_completion_date.strftime('%A, %d %B %Y'),
        chem_date=chem_completion_date.strftime('%A, %d %B %Y')
    ))

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
