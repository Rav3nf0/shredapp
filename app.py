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
    .stButton>button { width: 100%; border-radius: 10px; height: 3em; background-color: #262730; color: white; border: 1px solid #00FFAA; }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { height: 50px; background-color: #1E1E1E; border-radius: 5px; color: white; }
    .stTextInput>div>div>input { background-color: #161B22; color: #00FFAA; }
    </style>
    """, unsafe_allow_html=True)

st.title("🏹 The 8% Project")

# --- TOP METRICS BAR ---
stats = db.get_daily_summary()
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

# --- TAB 1: FOOD LOGGING (GEMINI 3 FLASH) ---
with tab_food:
    st.subheader("Interactive Nutrition")
    img_file = st.camera_input("Capture Meal")
    note = st.text_input("Extra details?")
    
    if img_file:
        if 'meal_data' not in st.session_state:
            with st.spinner("Gemini 3 Flash analyzing..."):
                img = Image.open(img_file)
                st.session_state.meal_data = analyze_meal_with_feedback(img, note)
        
        res = st.session_state.meal_data
        
        if res.get("status") == "pending":
            st.warning(f"🤔 **AI Question:** {res['question']}")
            ans = st.text_input("Answer to refine:")
            
            c_left, c_right = st.columns(2)
            if c_left.button("Confirm Details"):
                with st.spinner("Refining..."):
                    st.session_state.meal_data = analyze_meal_with_feedback(None, note, ans)
                    st.rerun()
            
            if c_right.button("⏩ Skip & Log Guess"):
                db.log_metric('meal', res['cal'], res['p'], res['item'])
                del st.session_state.meal_data
                st.toast("Logged best guess!")
                st.rerun()
        else:
            st.success(f"Verified: {res['item']}")
            ma1, ma2, ma3 = st.columns(3)
            ma1.metric("Cals", res['cal'])
            ma2.metric("P", f"{res['p']}g")
            ma3.metric("F", f"{res['f']}g")
            
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
        with st.spinner("Scraping Hevy..."):
            data = scrape_hevy(hevy_url)
            if data['vol'] > 0:
                st.balloons()
                st.metric("Volume Lifted", f"{data['vol']} lbs")
                if st.button("Confirm & Save Burn"):
                    db.log_metric('workout', data['burn'], 0, f"Hevy Vol: {data['vol']}")
                    st.rerun()
            else:
                st.error("Check link privacy.")

# --- TAB 3: GOOGLE FIT SYNC ---
with tab_sync:
    st.subheader("Health Cloud Sync")
    
    # Try an initial sync
    fit_result = sync_google_fit()
    
    if isinstance(fit_result, dict) and "auth_url" in fit_result:
        st.info("Setup Required: Link your Google Fit account.")
        st.link_button("1. Get Authorization Code", fit_result['auth_url'])
        
        auth_code = st.text_input("2. Paste Code from Google here:")
        if st.button("3. Complete Handshake"):
            with st.spinner("Connecting..."):
                final_sync = sync_google_fit(auth_code)
                if "error" not in final_sync:
                    st.success("Google Fit Linked!")
                    st.rerun()
                else:
                    st.error(final_sync["error"])
    else:
        if st.button("🔄 Refresh Data"):
            fit = sync_google_fit()
            if "error" in fit:
                st.error(f"Sync Failed: {fit['error']}")
            else:
                st.success("Successfully Synced!")
                s1, s2, s3 = st.columns(3)
                s1.metric("Steps", fit.get('steps', 0))
                s2.metric("Weight", f"{fit.get('weight', 0)}kg")
                s3.metric("BF %", f"{fit.get('body_fat', 0)}%")
                
                # Auto-log step burn
                if fit.get('steps', 0) > 0:
                    step_burn = fit['steps'] * 0.04
                    db.log_metric('workout', step_burn, 0, "Steps NEAT")

st.divider()
st.caption(f"Last Refresh: {datetime.datetime.now().strftime('%H:%M:%S')} | User: 68kg | 13.3% BF")