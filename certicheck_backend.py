from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template
from openai import OpenAI
from supabase import create_client, Client
from datetime import datetime, timezone
import os
import re
import requests
from functools import wraps
from flask import request, Response
from dotenv import load_dotenv
load_dotenv()

# trigger redeploy

# Basic Auth Config
USERNAME = "admin"
PASSWORD = "h^4$D!DBkmLZCpJkGKhn"  # 👉🏽 Change this to something strong

def check_auth(username, password):
    return username == USERNAME and password == PASSWORD

def authenticate():
    return Response(
        'Access denied.\n'
        'You must log in with the correct credentials.', 401,
        {'WWW-Authenticate': 'Basic realm="Login Required"'}
    )

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated


app = Flask(__name__)

@app.route("/")
def home():
    return render_template("index.html")

# Config: replace with your actual keys
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# GPT Prompt builder
def build_prompt(job_offer_text):
    return f"""
You are a fraud detection assistant. Analyze the job offer message below and return the following:

1. Scam Likelihood Score (0 to 10)
2. Red Flags Detected (bullet points)
3. Trust Signals (bullet points)
4. Recommended Action (one of: 'Safe to proceed', 'Proceed with caution', 'Do not trust this offer')
5. Explanation (short paragraph)

Here is the job offer message:

\"\"\"{job_offer_text}\"\"\"
"""

@app.route('/check-job', methods=['POST'])
def check_job():
    data = request.get_json()
    job_text = data.get("text", "").strip()

    if not job_text:
        return jsonify({"error": "No text provided"}), 400

    prompt = build_prompt(job_text)

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a scam detection assistant."},
                {"role": "user", "content": prompt}
            ]
        )

        result_text = response.choices[0].message.content if response.choices else "No response from GPT"
 
        print("📜 Raw GPT text:")
        print(result_text)
        print("✅ GPT Response:", result_text)

        # Parse response
        scam_score = None
        red_flags = []
        recommendation = ""
        explanation = ""
        parsing = None

        # Parse response
        lines = result_text.split("\n")
        scam_score = None
        red_flags = []
        recommendation = ""
        explanation = ""
        parsing = None

        for line in lines:
            if "Scam Likelihood Score" in line:
                match = re.search(r"Scam Likelihood Score[:\s]+(\d{1,2})", line)
                if match:
                    scam_score = int(match.group(1))
                    scam_score = max(0, min(10, scam_score))  # Clamp 0-10
            elif "Red Flags Detected" in line:
                parsing = "red_flags"
            elif "Trust Signals" in line:
                parsing = None  # We ignore trust signals for now
            elif "Recommended Action" in line:
                recommendation = line.split(":", 1)[1].strip()
                parsing = None
            elif "Explanation" in line:
                parsing = "explanation"
            elif line.strip().startswith("-") or line.strip().startswith("•"):
                if parsing == "red_flags":
                    red_flags.append(line.strip("-• ").strip())
            elif parsing == "explanation":
                explanation += line.strip() + " "

        if scam_score is None:
            raise ValueError("Scam score missing in GPT response.")

        # Store result in Supabase
        res = supabase.table("scam_checks").insert({
            "text_submitted": job_text,
            "scam_score": scam_score,
            "red_flags": red_flags,
            "recommendation": recommendation,
            "explanation": explanation.strip(),
            "checked_at": datetime.now(timezone.utc).isoformat()
        }).execute()

        print("✅ Supabase insert result:", res)
        print("🧠 Final JSON:", {
            "scam_score": scam_score,
            "red_flags": red_flags,
            "recommendation": recommendation,
            "explanation": explanation.strip()
        })
        return jsonify({
            "scam_score": scam_score,
            "red_flags": red_flags,
            "recommendation": recommendation,
            "explanation": explanation.strip(),
            "raw_gpt_response": result_text
        })

    except Exception as e:
        print("❌ Error during GPT or Supabase:", e)
        return jsonify({"error": str(e)}), 500
@app.route("/dashboard")
@requires_auth
def dashboard():
    url = "https://eyzvhwtxentuxoqunoyu.supabase.co/rest/v1/scam_checks?order=checked_at.desc"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}"
    }

    response = requests.get(url, headers=headers)
    records = response.json()

    return render_template("dashboard.html", records=records)

if __name__ == '__main__':
app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))