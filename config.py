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
MORNING_TOPICS = ["synonyms", "antonyms", "vocabulary", "one_word_substitution"]
EVENING_TOPICS = ["idioms", "spelling", "homonyms", "pronunciation"]
ALL_TOPICS = MORNING_TOPICS + EVENING_TOPICS

SESSION_TOPICS = {
    "morning": MORNING_TOPICS,
    "evening": EVENING_TOPICS,
}

# --- Adaptive difficulty tiers ---
# Based on rolling accuracy per topic (last N responses), decide how many
# NEW questions of that topic to send this session (in addition to any
# revision-queue questions due today for that topic).
ACCURACY_WINDOW = 20  # look at last N answered questions per topic

def questions_for_accuracy(accuracy_pct):
    """Return how many new questions a topic gets this session based on accuracy."""
    if accuracy_pct is None:
        return 1  # no data yet -> baseline
    if accuracy_pct < 60:
        return 3
    if accuracy_pct < 75:
        return 2
    return 1

# --- Spaced repetition ---
# On wrong answer: reset interval to 1 day.
# On correct answer while in revision queue: multiply interval (capped),
# and drop from queue after 3 consecutive correct reviews.
REVISION_INITIAL_INTERVAL_DAYS = 1
REVISION_INTERVAL_MULTIPLIER = 2
REVISION_MAX_INTERVAL_DAYS = 30
REVISION_STREAK_TO_RETIRE = 3

# --- Generation ---
MAX_GENERATION_RETRIES = 5  # retries per question if duplicate/invalid
