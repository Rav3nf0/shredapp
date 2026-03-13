import os
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
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# --- SCOPES ---
SCOPES = [
    'https://www.googleapis.com/auth/fitness.activity.read',
    'https://www.googleapis.com/auth/fitness.body.read',
    'https://www.googleapis.com/auth/fitness.location.read',
    'https://www.googleapis.com/auth/fitness.nutrition.read',
    'https://www.googleapis.com/auth/fitness.sleep.read'
]

# --- 1. NUTRITION AGENT ---
def analyze_meal_with_feedback(image, note="", user_answer=""):
    model = genai.GenerativeModel('gemini-3-flash-preview')
    context = f"Note: {note} | User Answer: {user_answer}"
    prompt = """
    Identify macros for a 68kg male (8% BF goal). 
    If unsure of oils/portions, set 'status' to 'pending' and ask a 'question'.
    Return ONLY JSON: {"item": "str", "cal": int, "p": int, "f": int, "c": int, "question": "str", "status": "pending/complete"}
    """
    response = model.generate_content([prompt, image] if image else [prompt])
    return json.loads(response.text.replace("```json", "").replace("```", "").strip())

# --- 2. HEVY AGENT ---
def scrape_hevy(url):
    res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
    soup = BeautifulSoup(res.text, 'html.parser')
    text = soup.get_text()
    vol = re.search(r'([\d,.]+)\s*lbs', text)
    volume = float(vol.group(1).replace(',', '')) if vol else 0
    burn = (7.5 * 3.5 * 68 / 200) * 60 
    return {"vol": volume, "burn": round(burn)}

# --- 3. GOOGLE FIT AGENT ---

def get_fit_service():
    """Handles OAuth handshake and returns the service object."""
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=8080)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    
    return build('fitness', 'v1', credentials=creds)

def sync_google_fit():
    """Fetches metrics one-by-one to prevent 403 errors from blocking everything."""
    try:
        service = get_fit_service()
        now = datetime.datetime.now()
        start_ms = int(now.replace(hour=0, minute=0, second=0).timestamp() * 1000)
        end_ms = int(now.timestamp() * 1000)

        # The core metrics for your 8% goal
        target_metrics = {
            "steps": "com.google.step_count.delta",
            "calories": "com.google.calories.expended",
            "heart_points": "com.google.heart_minutes",
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
                # Extract the value safely
                points = response['bucket'][0]['dataset'][0].get('point', [])
                if points:
                    val = points[0]['value'][0]
                    shred_data[label] = val.get('intVal') or round(val.get('fpVal', 0), 2)
                else:
                    shred_data[label] = 0
            except Exception:
                shred_data[label] = "No Access/Data"

        return shred_data
        
    except Exception as e:
        return {"error": str(e)}