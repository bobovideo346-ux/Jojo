import os
import requests
import json
import logging
import sys
import time
import random  # For shuffling options
import hashlib  # For hashing questions to track uniqueness
import sqlite3  # For persistent storage of used MCQs
from typing import Dict, List, Optional, Tuple

# Configure logging for GitHub/ production use
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('vocab_quiz_bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# Environment variables (set in GitHub Secrets or .env)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Validate required env vars
if not all([TELEGRAM_TOKEN, CHAT_ID, GROQ_API_KEY]):
    logger.error("Missing required environment variables: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, GROQ_API_KEY")
    sys.exit(1)

# Database file for tracking used MCQs (persists across runs)
DB_FILE = 'used_mcqs.db'

# Groq API config
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"  # Or use "llama3-8b-8192" if needed

# Telegram API base
TELEGRAM_BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# Prompt for generating English Vocabulary MCQ in JSON format (updated to encourage variety)
PROMPT = """
You are an English vocabulary expert. Generate a fresh, engaging MCQ to build vocabulary skills. Focus on synonyms, antonyms, meanings, word usage, idioms, or phrasal verbs. Use intermediate to advanced level words suitable for learners. Ensure it's unique and not overused.

Return ONLY valid JSON (no extra text) in this exact format:
{
  "question": "The question text here (e.g., What is the synonym of 'ephemeral'?)",
  "options": ["Option A text", "Option B text", "Option C text", "Option D text"],
  "correct_index": 0,
  "explanation": "Short explanation why this is correct, with example sentence."
}

Requirements:
- Question: Clear, concise (under 200 chars), in English. Avoid common words like 'happy', 'big'.
- Options: Exactly 4 plausible choices (one correct), no prefixes like (A).
- correct_index: 0-3 (A=0, B=1, etc.).
- Explanation: Educational, under 150 chars, include word origin or usage tip.
- Vary types: 40% synonyms, 30% meanings, 20% antonyms, 10% idioms/usage.
- Make it fun and challenging; rotate themes like literature, science, daily life.
"""

def init_db():
    """Initialize SQLite DB to track used MCQs."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS used_mcqs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_hash TEXT UNIQUE,
            question TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def is_mcq_used(question: str) -> bool:
    """Check if the question has been used before by hashing it."""
    question_hash = hashlib.md5(question.encode()).hexdigest()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM used_mcqs WHERE question_hash = ?', (question_hash,))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists

def mark_mcq_used(question: str):
    """Mark the MCQ as used in the DB."""
    question_hash = hashlib.md5(question.encode()).hexdigest()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        'INSERT OR IGNORE INTO used_mcqs (question_hash, question) VALUES (?, ?)',
        (question_hash, question)
    )
    conn.commit()
    conn.close()

def call_groq(attempt: int = 0) -> Optional[Dict]:
    """Call Groq API to generate MCQ JSON. Retry up to 3 times if duplicate."""
    if attempt >= 3:
        logger.warning("Max retries reached; using fallback.")
        return None

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": PROMPT}],
        "temperature": 0.7 + (attempt * 0.1),  # Increase temp for variety on retry
        "max_tokens": 400
    }
    try:
        response = requests.post(GROQ_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"].strip()
        
        # Clean up if wrapped in markdown
        if content.startswith("```json"):
            content = content[7:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
        mcq_data = json.loads(content)
        if all(key in mcq_data for key in ["question", "options", "correct_index", "explanation"]):
            if len(mcq_data["options"]) == 4 and 0 <= mcq_data["correct_index"] <= 3:
                question_text = mcq_data["question"]
                if is_mcq_used(question_text):
                    logger.info(f"Generated duplicate MCQ (attempt {attempt + 1}); retrying...")
                    return call_groq(attempt + 1)
                logger.info("Successfully generated unique vocabulary MCQ.")
                return mcq_data
        logger.warning("Invalid MCQ format from Groq.")
        return call_groq(attempt + 1)  # Retry on invalid
    except requests.exceptions.RequestException as e:
        logger.error(f"Groq API error: {e}")
        return call_groq(attempt + 1)
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error: {e}")
        return call_groq(attempt + 1)
    except Exception as e:
        logger.error(f"Unexpected error in call_groq: {e}")
        return call_groq(attempt + 1)

def send_poll_to_telegram(mcq: Dict) -> bool:
    """Send MCQ as a Telegram quiz poll."""
    url = f"{TELEGRAM_BASE_URL}/sendPoll"
    
    # Format options for poll (Telegram expects list of strings)
    options = mcq["options"]
    
    # Randomize options order for better learning (but keep correct_index updated)
    original_correct = options[mcq["correct_index"]]
    random.shuffle(options)
    new_correct_index = options.index(original_correct)
    
    payload = {
        "chat_id": CHAT_ID,
        "question": f"📚 Vocabulary Boost: {mcq['question']}",  # Add emoji for fun
        "options": json.dumps(options),  # Telegram expects JSON string for options? Wait, no: use list directly in data
        "type": "quiz",
        "correct_option_id": new_correct_index,
        "explanation": mcq["explanation"],
        "explanation_parse_mode": "HTML"  # For bold/italic in explanation if needed
    }
    
    try:
        response = requests.post(url, data=payload, timeout=20)
        response.raise_for_status()
        logger.info("Poll sent successfully to Telegram.")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Telegram poll send error: {e}")
        # Fallback: Send as text message
        fallback_msg = f"<b>📚 Vocabulary Quiz!</b>\n\n<i>{mcq['question']}</i>\n\nA) {options[0]}\nB) {options[1]}\nC) {options[2]}\nD) {options[3]}\n\n<b>Correct: {chr(65 + new_correct_index)}</b>\n\n<i>{mcq['explanation']}</i>"
        send_text_to_telegram(fallback_msg)
        return False
    except Exception as e:
        logger.error(f"Unexpected error in send_poll: {e}")
        return False

def send_text_to_telegram(text: str) -> bool:
    """Fallback: Send as HTML-formatted text message."""
    url = f"{TELEGRAM_BASE_URL}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, data=payload, timeout=10)
        response.raise_for_status()
        logger.info("Fallback text message sent.")
        return True
    except Exception as e:
        logger.error(f"Telegram text send error: {e}")
        return False

def generate_and_send_quiz() -> bool:
    """Main function: Generate unique MCQ and send as poll."""
    logger.info("Generating new unique vocabulary MCQ...")
    mcq = call_groq()
    if not mcq:
        # Fallback hardcoded MCQ if API fails (check if used first)
        logger.warning("Using fallback MCQ due to API failure.")
        fallback_mcq = {
            "question": "What is the synonym of 'ephemeral'?",
            "options": ["Eternal", "Temporary", "Permanent", "Endless"],
            "correct_index": 1,
            "explanation": "Ephemeral means lasting for a very short time, like a mayfly's life."
        }
        if is_mcq_used(fallback_mcq["question"]):
            # Simple variation for fallback
            fallback_mcq["question"] = "Antonym of 'ephemeral'?"
            fallback_mcq["options"] = ["Eternal", "Fleeting", "Brief", "Short"]
            fallback_mcq["correct_index"] = 0
            fallback_mcq["explanation"] = "Ephemeral means short-lived; its antonym is eternal."
        mcq = fallback_mcq
    
    # Mark as used before sending
    mark_mcq_used(mcq["question"])
    
    success = send_poll_to_telegram(mcq)
    if success:
        logger.info("Unique vocabulary quiz cycle completed successfully.")
    else:
        logger.error("Failed to send quiz.")
    return success

def main():
    """Run the bot. For GitHub Actions/Cron, run once. For continuous, add loop."""
    # Init DB on startup
    init_db()
    
    # Single run (as in original)
    generate_and_send_quiz()
    
    # Optional: For continuous mode (uncomment and set INTERVAL_SEC)
    # INTERVAL_SEC = int(os.getenv("QUIZ_INTERVAL_SEC", 3600))  # e.g., hourly
    # while True:
    #     generate_and_send_quiz()
    #     time.sleep(INTERVAL_SEC)

if __name__ == "__main__":
    main()
