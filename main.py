import os
import json
import random
from groq import Groq
from telegram import Bot, Poll  # Poll from telegram
from telegram.constants import ParseMode  # Optional, agar future mein use ho

# Environment variables
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
GROK_API_KEY = os.getenv('GROK_API_KEY')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
GROK_MODEL = "groq/compound"  # Valid Groq model
GROK_API_URL = "https://api.groq.com/openai/v1"  # Fix: Base URL only

# Topics from NCERT Class 11 & Nitin Singhania (chapter-wise, sub-headings inspired)
TOPICS = [
    # NCERT Class 11: An Introduction to Indian Art
    "Prehistoric Rock Paintings (Bhimbetka, hunting scenes)",
    "Arts of the Indus Valley (Harappan seals, pottery)",
    "Arts of the Mauryan Period (Ashokan pillars, polished sandstone)",
    "Post-Mauryan Trends in Indian Art and Architecture (Kushan, Satavahana sculptures)",
    "Later Mural Traditions (Ajanta caves, Bagh paintings)",
    "Temple Architecture and Sculpture (Nagara, Dravida styles)",
    "Indian Bronze Sculpture (Chola bronzes, Nataraja)",
    "Some Aspects of Indo-Islamic Architecture (Qutub Minar, Taj Mahal)",
    
    # Nitin Singhania: Visual Arts
    "Pre-Historic Cultures in India (rock art, cave paintings)",
    "Indian Architecture (Buddhist stupas, Hindu temples)",
    "Sculpture and Pottery (Mauryan, Gupta era)",
    "Edicts and Inscriptions (Ashoka's edicts)",
    "Coins in India (ancient punch-marked coins)",
    "Legendary Cities of India (Indraprastha, Hastinapur)",
    "Indian Paintings (miniature schools: Mughal, Rajput)",
    "Indian Handicrafts (textiles, metalwork)",
    "Geographical Indications (GI tags for crafts)",
    
    # Performing Arts
    "Indian Music (Hindustani, Carnatic, ragas)",
    "Indian Dance (classical: Bharatanatyam, Kathak; folk dances)",
    "Indian Theatre, Puppetry, Circus (Kathakali, shadow puppets)",
    "Indian Cinema (early films, parallel cinema)",
    
    # Literary Arts & Heritage
    "Languages and Scripts (Devanagari, Brahmi)",
    "Indian Literature (Vedas, epics, Bhakti poetry)",
    "Religion and Philosophy (Hinduism, Buddhism, Jainism)",
    "Bhakti and Sufi Movements (saints like Kabir, Chaitanya)",
    "Fairs and Festivals (Kumbh Mela, Diwali)",
    "Tribal Art and Culture (Warli, Gond paintings)",
    "Science and Technology through the Ages (ancient metallurgy)",
    "India through the eyes of foreign Travellers (Fa-Hien, Ibn Battuta)"
]

# Load used questions
USED_QUESTIONS_FILE = 'used_questions.json'
try:
    with open(USED_QUESTIONS_FILE, 'r') as f:
        used_questions = set(json.load(f))
except FileNotFoundError:
    used_questions = set()

client = Groq(api_key=GROK_API_KEY, base_url=GROK_API_URL)
bot = Bot(token=TELEGRAM_BOT_TOKEN)

def generate_mcq(topic):
    prompt = f"""
    Generate ONE MCQ on '{topic}' from Indian Art and Culture syllabus (NCERT Class 11 or Nitin Singhania level).
    - Difficulty: PCS/SSC exam level (factual, analytical like PYQs e.g., SSC CGL/UPPCS previous questions).
    - Format: Question text. Then options A, B, C, D. Then correct answer as 'Correct: A (explanation)'.
    - 4 options, one correct.
    - Question should be unique, detailed, chapter-specific.
    - Keep question under 200 chars, options short.
    Example: Q: Which cave site has prehistoric paintings of hunting? A) Bhimbetka B) Ajanta C) Ellora D) Elephanta Correct: A (Bhimbetka in MP has Mesolithic rock art).
    """
    
    response = client.chat.completions.create(
        model=GROK_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=200,
        temperature=0.7
    )
    
    generated = response.choices[0].message.content.strip()
    # Parse: Assume format Q: ... A) ... B) ... C) ... D) ... Correct: X (exp)
    lines = generated.split('\n')
    question = lines[0].replace('Q: ', '').strip()
    options = [opt.strip() for opt in lines[1:5]]  # A, B, C, D
    correct_str = [line for line in lines if line.startswith('Correct:')][0]
    correct_letter = correct_str.split(':')[1].split(' ')[0].strip()  # A, B, C, D
    correct_index = ord(correct_letter) - ord('A')  # 0-3
    explanation = correct_str.split('(')[1].rstrip(')') if '(' in correct_str else ''
    
    full_question = f"{question}\n{chr(10).join(options)}"  # For tracking
    return question, options, correct_index, explanation, full_question

def send_mcq_to_telegram(question, options, correct_index, explanation):
    # Shuffle options randomly, adjust correct_index
    shuffled_options = options.copy()
    random.shuffle(shuffled_options)
    new_correct_index = shuffled_options.index(options[correct_index])
    
    # Send quiz poll
    message = bot.send_poll(
        chat_id=TELEGRAM_CHAT_ID,
        question=question,
        options=shuffled_options,
        type=Poll.QUIZ,
        correct_option_id=new_correct_index,
        explanation=explanation,
        is_anonymous=False,  # Show who voted
        open_period=86400  # 24 hours
    )
    print(f"Poll sent: {message.poll.id}")

if __name__ == "__main__":
    topic = random.choice(TOPICS)
    question, options, correct_index, explanation, full_question = generate_mcq(topic)
    
    # Check repeat
    if full_question in used_questions:
        print("Repeat found, regenerating...")
        # Simple retry, can loop if needed
        topic = random.choice(TOPICS)
        question, options, correct_index, explanation, full_question = generate_mcq(topic)
    
    # Save to used
    used_questions.add(full_question)
    with open(USED_QUESTIONS_FILE, 'w') as f:
        json.dump(list(used_questions), f)
    
    # Send
    send_mcq_to_telegram(question, options, correct_index, explanation)
    print(f"MCQ sent on topic: {topic}")
