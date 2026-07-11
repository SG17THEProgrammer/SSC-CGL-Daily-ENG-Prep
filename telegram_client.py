"""
Thin wrapper around the relevant Telegram Bot API HTTP endpoints.
No telegram library dependency needed -- these scripts run once and exit,
so a heavier bot framework built for long-running polling isn't a good fit.
"""

import requests

import config

API_BASE = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}"

# Telegram's hard limits for quiz polls.
POLL_QUESTION_LIMIT = 300
POLL_OPTION_LIMIT = 100
POLL_EXPLANATION_LIMIT = 200


def _smart_truncate(text, limit):
    """Cut at the last full word within the limit instead of mid-word/mid-sentence."""
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    last_space = cut.rfind(" ")
    if last_space > 0:
        cut = cut[:last_space]
    return cut.rstrip(",;: ") + "…"


def send_quiz_poll(question_text, options, correct_index, explanation):
    """
    Sends a native Telegram quiz poll. Telegram itself shows correct/incorrect
    instantly when the user taps an option. Because Telegram caps the in-poll
    explanation at 200 characters -- and we want full explanations covering
    all 4 options, not a clipped one -- the poll's own explanation field just
    points to the follow-up message; send_full_explanation() carries the
    actual content and is always sent right after this.
    Returns the poll_id.
    """
    url = f"{API_BASE}/sendPoll"
    payload = {
        "chat_id": config.TELEGRAM_CHAT_ID,
        "question": _smart_truncate(question_text, POLL_QUESTION_LIMIT),
        "options": [_smart_truncate(opt, POLL_OPTION_LIMIT) for opt in options],
        "type": "quiz",
        "correct_option_id": correct_index,
        "explanation": _smart_truncate(explanation or "", POLL_EXPLANATION_LIMIT),
        "is_anonymous": False,
    }
    resp = requests.post(url, json=payload, timeout=15)
    resp.raise_for_status()
    result = resp.json()["result"]
    return result["poll"]["id"]


def send_full_explanation(explanation, topic=None):
    """
    Always sent as a normal follow-up message right after the poll, so the
    full explanation (why the correct option is right + what the other 3
    options mean) is never lost to Telegram's 200-char poll-field limit.
    """
    prefix = f"*{topic.replace('_', ' ').title()}* — explanation:\n" if topic else "Explanation:\n"
    send_message(prefix + explanation)


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