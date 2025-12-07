import os
import requests
import json

# Secrets से values लेंगे (GitHub में डालोगे)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID") 
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Groq API (तुम्हारा वाला ही)
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

# Prompt जो हर बार नया MCQ मंगेगा
PROMPT = """
Generate a fresh, interesting multiple choice quiz question (MCQ) in Hindi or English on any topic (science, GK, history, tech, fun facts etc).
Format must be exactly like this:

❓ प्रश्न: ...
A) ...
B) ...
C) ...
D) ...

सही जवाब: (A/B/C/D में से एक)
"""

def call_groq():
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": PROMPT}],
        "temperature": 0.9,
        "max_tokens": 300
    }
    try:
        r = requests.post(GROQ_URL, headers=headers, json=payload, timeout=20)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Groq API Error: {str(e)}"

def send_to_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print("Telegram send error:", e)

if __name__ == "__main__":
    print("Generating new quiz...")
    quiz = call_groq()
    full_message = f"<b>Quiz Time!</b>\n\n{quiz}"
    send_to_telegram(full_message)
    print("Quiz sent successfully!")
