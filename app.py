from flask import Flask, request, jsonify, render_template
import requests, os, json, csv, base64, mimetypes
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta
import google.generativeai as genai

# ------------------------
# Setup
# ------------------------
load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

app = Flask(__name__)

FARMER_NEWS = []


UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

HISTORY_FILE = "hist.txt"
ESP_IP = os.getenv("ESP_IP")
DATA_CSV = "esp_data.csv"
LAST_PUMP = None
IST = timezone(timedelta(hours=5, minutes=30))


# ------------------------
# Helpers
# ------------------------
def load_history():
    return open(HISTORY_FILE, "r", encoding="utf-8").read() if os.path.exists(HISTORY_FILE) else ""

def save_to_history(user, ai):
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(f"User: {user}\nAI: {ai}\n\n")

def clear_history():
    open(HISTORY_FILE, "w").close()

#for news 
def generate_farmer_news():
    global FARMER_NEWS

    prompt = """
Generate 10 short news updates for Indian farmers in Hindi.
Rules:
- One line per news
- Very simple Hindi
- Practical farming related
- No numbering
- No special characters
- Plain text only
"""

    model = genai.GenerativeModel("gemini-2.5-flash")
    response = model.generate_content(prompt).text

    # convert response into list
    news_list = [n.strip() for n in response.split("\n") if n.strip()]

    FARMER_NEWS = news_list[:10]


# ------------------------
# Routes
# ------------------------
@app.route("/")
def home():
    return render_template("index.html")


# -------- CHAT ----------
@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_msg = data.get("message")

    if not user_msg:
        return jsonify({"error": "Message required"}), 400

    history = load_history()

    field_data = {}
    try:
        if ESP_IP:
            url = ESP_IP if ESP_IP.startswith("http") else f"http://{ESP_IP}"
            field_data = requests.get(url, timeout=2).json()
    except:
        field_data = {"error": "ESP not reachable"}

    prompt = f"""
You are an intelligent farming assistant for Indian farmers.

Previous conversation:
{history}

User message:
{user_msg}

Field data:
{json.dumps(field_data)}

Reply in same language and tone as user.
Short, friendly, practical.
Plain text only.
"""

    model = genai.GenerativeModel("gemini-2.5-flash")
    ai_reply = model.generate_content(prompt).text

    save_to_history(user_msg, ai_reply)
    return jsonify({"reply": ai_reply})


# -------- LEAF IMAGE ----------
@app.route("/leaf", methods=["POST"])
def leaf():
    file = request.files.get("leaf")
    language = request.form.get("language", "hi-IN")

    if not file:
        return jsonify({"error": "No image uploaded"}), 400

    path = Path(UPLOAD_FOLDER) / file.filename
    file.save(path)

    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    img_b64 = base64.b64encode(path.read_bytes()).decode()
    data_url = f"data:{mime};base64,{img_b64}"

    payload = {
        "model": "google/gemma-3-27b-it:featherless-ai",
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text":
                 "Identify plant, disease, and remedy. Reply in hindi language only without any special chararcters. One short line only."},
                {"type": "image_url", "image_url": {"url": data_url}}
            ]
        }]
    }

    headers = {
        "Authorization": f"Bearer {os.getenv('HF_TOKEN')}",
        "Content-Type": "application/json",
    }

    r = requests.post(
        "https://router.huggingface.co/v1/chat/completions",
        headers=headers,
        json=payload
    ).json()

    reply = r["choices"][0]["message"]["content"]
    save_to_history("Leaf image uploaded", reply)

    return jsonify({"reply": reply})


# -------- CLEAR ----------
@app.route("/clear", methods=["POST"])
def clear():
    clear_history()
    return jsonify({"status": "Chat cleared"})


# -------- ESP DATA ----------
@app.route("/getdata")
def getdata():
    try:
        url = ESP_IP if ESP_IP.startswith("http") else f"http://{ESP_IP}"
        data = requests.get(url, timeout=2).json()
        return jsonify(data)
    except:
        return jsonify({"error": "ESP not reachable"})


@app.route("/farmer-news")
def farmer_news():
    if not FARMER_NEWS:
        generate_farmer_news()

    return jsonify({
        "news": FARMER_NEWS,
        "count": len(FARMER_NEWS)
    })



if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True)
