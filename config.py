"""
Central configuration for the SSC CGL English AI Coach.
All secrets are read from environment variables (set as GitHub Actions Secrets).
Nothing sensitive is hardcoded here since this repo is public.
"""

import os

# --- Secrets (set these in GitHub repo Settings -> Secrets and variables -> Actions) ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

# --- Groq model ---
# Check https://console.groq.com/docs/models for currently available free models.
# llama-3.3-70b-versatile is a strong general-purpose free-tier model as of writing.
# GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")

# --- Database ---
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database.db")

# --- Topics ---
# SBI PO 2026-focused English topics, split across 3 daily sessions so the
# frequency is higher without any single session running too long.
MORNING_TOPICS = ["synonyms", "antonyms", "one_word_substitution", "error_spotting"]
AFTERNOON_TOPICS = ["cloze_test", "fill_in_the_blanks", "phrase_replacement", "sentence_improvement"]
EVENING_TOPICS = ["idioms", "spelling", "para_jumbles" , "error_spotting"]
ALL_TOPICS = MORNING_TOPICS + AFTERNOON_TOPICS + EVENING_TOPICS

SESSION_TOPICS = {
    "morning": MORNING_TOPICS,
    "afternoon": AFTERNOON_TOPICS,
    "evening": EVENING_TOPICS,
}

# --- Question count ---
# FIXED per topic per session -- this is what actually stops the "sometimes 2,
# sometimes 4" unevenness. Total per session = QUESTIONS_PER_TOPIC * len(topics)
# = 3 * 4 = 12 questions -> 36 questions/day across 3 sessions.
QUESTIONS_PER_TOPIC = 3

# --- Generation ---
MAX_GENERATION_RETRIES = 12  # retries per question if duplicate/invalid/word-already-used
GROQ_MAX_TOKENS = 1200  # raised so the model never has to cut a question/explanation short
GROQ_TIMEOUT_SECONDS = 45