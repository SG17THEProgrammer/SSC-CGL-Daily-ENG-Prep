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
    Sends a native Telegram quiz poll. Telegram shows correct/incorrect AND
    the explanation (up to 200 chars) instantly inline when the user taps an
    option -- no separate message needed for the common case, since the
    generator now produces a single crisp sentence that almost always fits.
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


def send_full_explanation_if_needed(explanation, topic=None):
    """
    Only sends a separate follow-up message if the explanation genuinely did
    NOT fit inside the poll's 200-char inline field. This is what stops the
    chat from getting crowded with a second message after every single
    question -- most explanations are one short sentence and fit inline.
    """
    if not explanation or len(explanation) <= POLL_EXPLANATION_LIMIT:
        return
    prefix = f"*{topic.replace('_', ' ').title()}* — full explanation:\n" if topic else "Full explanation:\n"
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