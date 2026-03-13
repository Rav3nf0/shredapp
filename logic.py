import os
import streamlit as st
import json
import re
import requests
import datetime
from bs4 import BeautifulSoup
import google.generativeai as genai
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# --- NUTRITION AGENT (GEMINI 3 FLASH) ---
def analyze_meal_with_feedback(image, note="", user_answer=""):
    # Configure using Streamlit Secrets for Cloud Deployment
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel('gemini-3-flash')
    
    # Prompt hardcoded with your 13.3% -> 8% BF journey details
    prompt = f"""
    Context: User is a 68kg male, 13.3% body fat, training 5x/week. Goal: 8% BF.
    User is an Offensive Security professional and prefers efficiency over conversation.
    
    TASK: Identify macros for the meal.
    - Be aggressive with protein estimates (Target: 140g+ daily).
    - Tell the calories consumed, along with other nutrition data
    - If portions/oils are unclear, MAKE A BEST GUESS based on athletic standards.
    - Only set 'status' to 'pending' if the calories could vary by >150. Otherwise, 'complete'.
    
    Input Context: Note: {note} | User Answer: {user_answer}
    
    Return ONLY JSON: 
    {{"item": "str", "cal": int, "p": int, "f": int, "c": int, "question": "str", "status": "pending/complete"}}
    """
    
    response = model.generate_content([prompt, image] if image else [prompt])
    # Clean response for JSON parsing
    clean_text = response.text.replace("```json", "").replace("```", "").strip()
    return json.loads(clean_text)

# --- HEVY AGENT ---
def scrape_hevy(url):
    res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
    soup = BeautifulSoup(res.text, 'html.parser')
    text = soup.get_text()
    vol = re.search(r'([\d,.]+)\s*lbs', text)
    volume = float(vol.group(1).replace(',', '')) if vol else 0
    # MET formula for weightlifting
    burn = (7.5 * 3.5 * 68 / 200) * 60 
    return {"vol": volume, "burn": round(burn)}

# --- GOOGLE FIT AGENT (CLOUD OPTIMIZED) ---
SCOPES = [
    'https://www.googleapis.com/auth/fitness.activity.read',
    'https://www.googleapis.com/auth/fitness.body.read',
    'https://www.googleapis.com/auth/fitness.location.read',
    'https://www.googleapis.com/auth/fitness.nutrition.read',
    'https://www.googleapis.com/auth/fitness.sleep.read'
]

def get_fit_service(auth_code=None):
    """Handles OAuth for Streamlit Cloud via manual code entry or existing token."""
    creds = None
    token_path = '/tmp/token.json' # Writable path in Streamlit Cloud
    
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Load credentials from Streamlit Secrets (ensure TOML matches this structure)
            creds_info = {"installed": st.secrets["google_credentials"]}
            flow = InstalledAppFlow.from_client_config(creds_info, SCOPES)
            
            if auth_code:
                # Process the manual code entered in the UI
                flow.fetch_token(code=auth_code)
                creds = flow.credentials
            else:
                # Return the URL to trigger the UI link button in app.py
                auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')
                return auth_url

        with open(token_path, 'w') as token:
            token.write(creds.to_json())
            
    return build('fitness', 'v1', credentials=creds)

def sync_google_fit(auth_code=None):
    """Fetches metrics. Returns auth_url if login is needed, or the data if successful."""
    try:
        service_or_url = get_fit_service(auth_code)
        
        # If it's a string, it's the auth_url for first-time login
        if isinstance(service_or_url, str):
            return {"auth_url": service_or_url}
            
        service = service_or_url
        now = datetime.datetime.now()
        start_ms = int(now.replace(hour=0, minute=0, second=0).timestamp() * 1000)
        end_ms = int(now.timestamp() * 1000)

        target_metrics = {
            "steps": "com.google.step_count.delta",
            "calories": "com.google.calories.expended",
            "weight": "com.google.weight",
            "body_fat": "com.google.body.fat.percentage"
        }
        
        shred_data = {}
        for label, data_type in target_metrics.items():
            body = {
                "aggregateBy": [{"dataTypeName": data_type}],
                "bucketByTime": {"durationMillis": 86400000},
                "startTimeMillis": start_ms,
                "endTimeMillis": end_ms
            }
            try:
                response = service.users().dataset().aggregate(userId='me', body=body).execute()
                points = response['bucket'][0]['dataset'][0].get('point', [])
                if points:
                    val = points[0]['value'][0]
                    shred_data[label] = val.get('intVal') or round(val.get('fpVal', 0), 2)
                else:
                    shred_data[label] = 0
            except Exception:
                shred_data[label] = "No Access"

        return shred_data
        
    except Exception as e:
        return {"error": str(e)}