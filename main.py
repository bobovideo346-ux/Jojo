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

# Updated Prompt: NCERT Class 6-12 Syllabus Focus + JSON Output
PROMPT = """
Generate a fresh, interesting multiple choice quiz question (MCQ) strictly from NCERT syllabus for Classes 6 to 12 (any subject: Mathematics - geometry, algebra, numbers; Science - physics, chemistry, biology; Social Science - history, geography, civics, economics; English/Hindi - grammar, literature; or other electives like Environmental Science).

Syllabus Guidelines: Cover fundamental concepts from NCERT books (e.g., Class 6-8 basics, Class 9-10 intermediate, Class 11-12 advanced). Topics include: History (ancient/modern India), Geography (physical/human), Polity (constitution, governance), Economics (development, sectors), Science (motion, atoms, ecosystems), Maths (triangles, polynomials), etc.

Format your response EXACTLY as JSON (no extra text):

{
  "question": "The MCQ question in Hindi or English (keep it concise, 1-2 sentences).",
  "options": [
    "Option 1 (A equivalent)",
    "Option 2 (B equivalent)",
    "Option 3 (C equivalent)",
    "Option 4 (D equivalent)"
  ],
  "correct_option_id": 0,  // Integer: 0 for first option, 1 for second, etc. (0-3)
  "explanation": "Detailed explanation of the correct answer (1-3 sentences, why it's correct, reference to NCERT chapter if possible)."
}

Make it educational and fun. Only JSON output.
"""

def call_groq():
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": PROMPT}],
        "temperature": 0.7,
        "max_tokens": 400
    }
    try:
        r = requests.post(GROQ_URL, headers=headers, json=payload, timeout=20)
        r.raise_for_status()
        response_text = r.json()["choices"][0]["message"]["content"].strip()
        # Parse JSON
        data = json.loads(response_text)
        print(f"Generated Quiz: {data['question'][:50]}...")  # Log preview
        return data
    except json.JSONDecodeError as e:
        print(f"JSON Parse Error: {str(e)} - Response: {response_text}")
        return None
    except Exception as e:
        print(f"Groq API Error: {str(e)}")
        return None

def send_poll_to_telegram(data):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPoll"
    payload = {
        "chat_id": CHAT_ID,
        "question": data['question'],
        "options": json.dumps(data['options']),  # JSON array for options
        "is_quiz": True,
        "correct_option_id": data['correct_option_id'],
        "explanation": data['explanation'],
        "explanation_parse_mode": "HTML"
    }
    try:
        r = requests.post(url, data=payload, timeout=10)
        r.raise_for_status()
        print("Poll sent successfully!")
        return True
    except Exception as e:
        print(f"Telegram Poll send error: {str(e)} - Response: {r.text if 'r' in locals() else 'No response'}")
        return False

if __name__ == "__main__":
    print("Generating NCERT-based quiz...")
    data = call_groq()
    if not data:
        print("Failed to generate quiz. Exiting.")
        exit(1)
    
    success = send_poll_to_telegram(data)
    if success:
        print("NCERT Quiz Poll sent successfully!")
    else:
        print("Failed to send poll. Exiting.")
        exit(1)
