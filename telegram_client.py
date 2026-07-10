"""
Thin wrapper around the relevant Telegram Bot API HTTP endpoints.
No telegram library dependency needed -- these scripts run once and exit,
so a heavier bot framework built for long-running polling isn't a good fit.
"""

import requests

import config

API_BASE = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}"


def send_quiz_poll(question_text, options, correct_index, explanation):
    """
    Sends a native Telegram quiz poll. Telegram itself shows correct/incorrect
    and the explanation instantly when the user taps an option.
    Returns the poll_id.
    """
    url = f"{API_BASE}/sendPoll"
    payload = {
        "chat_id": config.TELEGRAM_CHAT_ID,
        "question": question_text[:300],  # Telegram poll question length limit
        "options": [opt[:100] for opt in options],  # Telegram option length limit
        "type": "quiz",
        "correct_option_id": correct_index,
        "explanation": (explanation or "")[:200],  # Telegram explanation length limit
        "is_anonymous": False,
    }
    resp = requests.post(url, json=payload, timeout=15)
    resp.raise_for_status()
    result = resp.json()["result"]
    return result["poll"]["id"]


def send_message(text):
    url = f"{API_BASE}/sendMessage"
    payload = {
        "chat_id": config.TELEGRAM_CHAT_ID,
        "text": text[:4000],
        "parse_mode": "Markdown",
    }
    resp = requests.post(url, json=payload, timeout=15)
    resp.raise_for_status()
    return resp.json()


def get_updates(offset):
    url = f"{API_BASE}/getUpdates"
    payload = {
        "offset": offset,
        "timeout": 0,
        "allowed_updates": ["poll_answer"],
    }
    resp = requests.post(url, json=payload, timeout=15)
    resp.raise_for_status()
    return resp.json()["result"]
