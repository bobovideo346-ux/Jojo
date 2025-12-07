import os
import requests
import json
import re
import time

# Secrets
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not TELEGRAM_TOKEN or not CHAT_ID or not GROQ_API_KEY:
    print("Missing required environment variables. Make sure TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, and GROQ_API_KEY are set.")
    exit(1)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

PROMPT = """
Generate a fresh, interesting multiple choice quiz question (MCQ) strictly from NCERT syllabus for Classes 6 to 12 ...
(keep the rest of your original prompt here)
"""

def extract_json_from_text(text: str):
    # 1) Try to extract code block content ```...```
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if m:
        candidate = m.group(1).strip()
    else:
        # 2) Fallback: find first balanced { ... } by last closing brace
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1 and end > start:
            candidate = text[start:end+1]
        else:
            return None

    # 3) Clean common issues: trailing commas before closing braces/brackets
    candidate = re.sub(r",\s*}", "}", candidate)
    candidate = re.sub(r",\s*]", "]", candidate)
    return candidate

def validate_quiz_dict(data: dict):
    if not isinstance(data, dict):
        return False, "parsed data is not a JSON object"
    for key in ("question", "options", "correct_option_id", "explanation"):
        if key not in data:
            return False, f"missing key: {key}"
    if not isinstance(data["options"], list) or len(data["options"]) < 2:
        return False, "options must be a list with at least 2 items"
    if not isinstance(data["correct_option_id"], int):
        return False, "correct_option_id must be an integer"
    return True, None

def call_groq(retries=3, backoff=2):
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

    attempt = 0
    while attempt < retries:
        attempt += 1
        try:
            r = requests.post(GROQ_URL, headers=headers, json=payload, timeout=20)
            r.raise_for_status()
            full_text = r.text  # raw text for diagnostics

            # Try to get the content in structured response if present
            response_text = None
            try:
                j = r.json()
                # safe navigation
                response_text = j.get("choices", [{}])[0].get("message", {}).get("content")
                if response_text:
                    response_text = response_text.strip()
            except Exception:
                # r.json() may fail or structure may differ; leave response_text None
                response_text = None

            # If we didn't get content via parsed JSON, use raw text
            if not response_text:
                response_text = full_text.strip()

            # First try direct JSON parse
            try:
                data = json.loads(response_text)
                valid, err = validate_quiz_dict(data)
                if not valid:
                    raise json.JSONDecodeError(f"Structure invalid: {err}", response_text, 0)
                print(f"Generated Quiz: {data['question'][:50]}...")
                return data
            except json.JSONDecodeError:
                # Try to extract JSON block from any surrounding text
                candidate = extract_json_from_text(response_text)
                if candidate:
                    try:
                        data = json.loads(candidate)
                        valid, err = validate_quiz_dict(data)
                        if not valid:
                            print(f"Parsed JSON but structure invalid: {err}")
                            raise ValueError(err)
                        print(f"Generated Quiz (extracted): {data['question'][:50]}...")
                        return data
                    except Exception as e:
                        print(f"JSON extraction parse failed: {e}")
                        # fall through to logging
                # If we reach here, parsing failed
                print("JSON Parse Error: Could not parse model output as valid JSON.")
                print("Full response for debugging:")
                print(full_text)
                return None

        except requests.HTTPError as e:
            status = getattr(e.response, "status_code", None)
            print(f"Groq API HTTP error (attempt {attempt}/{retries}): {e} - status {status}")
        except requests.RequestException as e:
            print(f"Groq API request error (attempt {attempt}/{retries}): {e}")
        except Exception as e:
            print(f"Unexpected error calling Groq API (attempt {attempt}/{retries}): {e}")

        # backoff before retrying
        if attempt < retries:
            time.sleep(backoff * attempt)

    print("Groq API: exhausted retries, giving up.")
    return None

def send_poll_to_telegram(data):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPoll"
    payload = {
        "chat_id": CHAT_ID,
        "question": data['question'],
        "options": json.dumps(data['options']),
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
        resp_text = r.text if 'r' in locals() and getattr(r, "text", None) else "No response body"
        print(f"Telegram Poll send error: {e} - Response: {resp_text}")
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
