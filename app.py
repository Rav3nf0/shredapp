import streamlit as st
from PIL import Image
import datetime
from database import ShredDB
from logic import analyze_meal_with_feedback, scrape_hevy, sync_google_fit

# Initialize Database
db = ShredDB()

# Page Configuration
st.set_page_config(page_title="8% Shred", page_icon="🏹", layout="centered")

# Custom CSS for Dark Mode & Mobile Optimization
st.markdown("""
    <style>
    .main { background-color: #0E1117; }
    [data-testid="stMetricValue"] { font-size: 1.8rem; color: #00FFAA; }
    .stButton>button { width: 100%; border-radius: 10px; height: 3em; background-color: #262730; color: white; border: 1px solid #444; }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { height: 50px; background-color: #1E1E1E; border-radius: 5px; color: white; }
    </style>
    """, unsafe_allow_html=True)

st.title("🏹 The 8% Project")

# --- TOP METRICS BAR ---
stats = db.get_daily_summary()
# BMR calculation for 68kg male
BMR_BASE = 1650 
total_calories_out = BMR_BASE + stats['calories_out']
net_deficit = total_calories_out - stats['calories_in']

col1, col2, col3 = st.columns(3)
col1.metric("Deficit", f"{int(net_deficit)}", "kcal")
col2.metric("Protein", f"{int(stats['protein_in'])}g", "/ 140g")
col3.metric("Burn", f"{int(total_calories_out)}", "kcal")

st.divider()

# --- MAIN NAVIGATION ---
tab_food, tab_gym, tab_sync = st.tabs(["📸 Food", "🏋️ Gym", "☁️ Sync"])

# --- TAB 1: FOOD LOGGING (GEMINI) ---
with tab_food:
    st.subheader("Interactive Nutrition")
    img_file = st.camera_input("Capture Meal")
    note = st.text_input("Extra details? (e.g. '1 tsp butter')")
    
    if img_file:
        # State machine for Gemini interaction
        if 'meal_data' not in st.session_state:
            with st.spinner("Gemini 3 Flash is analyzing..."):
                img = Image.open(img_file)
                st.session_state.meal_data = analyze_meal_with_feedback(img, note)
        
        res = st.session_state.meal_data
        
        if res.get("status") == "pending":
            st.warning(f"🤔 **Question:** {res['question']}")
            ans = st.text_input("Your response:")
            if st.button("Confirm Details"):
                with st.spinner("Refining macros..."):
                    st.session_state.meal_data = analyze_meal_with_feedback(None, note, ans)
                    st.rerun()
        else:
            st.success(f"Verified: {res['item']}")
            c1, c2, c3 = st.columns(3)
            c1.metric("Cals", res['cal'])
            c2.metric("P", f"{res['p']}g")
            c3.metric("C", f"{res['c']}g")
            
            if st.button("💾 Log to Shred History"):
                db.log_metric('meal', res['cal'], res['p'], res['item'])
                del st.session_state.meal_data
                st.toast("Meal Saved!")
                st.rerun()

# --- TAB 2: GYM LOGGING (HEVY) ---
with tab_gym:
    st.subheader("Workout Volume Sync")
    hevy_url = st.text_input("Paste Hevy Workout Link")
    if st.button("Extract Volume"):
        with st.spinner("Scraping Hevy session..."):
            data = scrape_hevy(hevy_url)
            if data['vol'] > 0:
                st.balloons()
                st.metric("Volume Lifted", f"{data['vol']} lbs")
                st.info(f"Estimated Burn: {data['burn']} kcal")
                if st.button("Confirm Workout"):
                    db.log_metric('workout', data['burn'], 0, f"Hevy Vol: {data['vol']}")
                    st.rerun()
            else:
                st.error("Could not find volume. Is the profile public?")

# --- TAB 3: GOOGLE FIT SYNC ---
with tab_sync:
    st.subheader("Health Cloud Sync")
    if st.button("🔄 Sync Google Fit Now"):
        with st.spinner("Accessing Google Health..."):
            fit = sync_google_fit()
            
            if "error" in fit:
                st.error(f"Sync Failed: {fit['error']}")
            else:
                st.success("Successfully Synced!")
                
                # Visual Metrics for Sync
                s1, s2 = st.columns(2)
                s1.metric("Steps Today", fit.get('steps', 0))
                s2.metric("Active Burn", f"{fit.get('calories', 0)} kcal")
                
                with st.expander("Show Detailed Payload"):
                    st.json(fit)
                
                # Update DB with step calories (approx 0.04 kcal per step)
                if fit.get('steps', 0) > 0:
                    step_burn = fit['steps'] * 0.04
                    db.log_metric('workout', step_burn, 0, "Steps NEAT")

st.divider()
st.caption("8% Project Dashboard | Powered by Gemini 3 Flash & Google Fit")