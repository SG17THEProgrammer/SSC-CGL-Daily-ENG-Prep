"""
Entry point run three times daily by GitHub Actions:
    python send_quiz.py morning
    python send_quiz.py afternoon
    python send_quiz.py evening

Sends a FIXED number of questions per topic (config.QUESTIONS_PER_TOPIC) --
this is what keeps the count consistent every single run instead of
swinging between 2 and 4. No answer-collection, no accuracy-adaptive
counts, no revision queue: this is pure practice-volume mode for SBI PO,
running as fast as possible without waiting on Telegram poll answers.
"""

import json
import sys

import config
import database as db
import generator
import telegram_client as tg


def send_new_question(topic):
    qid, focus_word = generator.generate_unique_question(topic)
    if qid is None:
        print(f"Skipping send for topic={topic}: generation failed after retries")
        return False

    question_row = db.get_question(qid)
    options = json.loads(question_row["options"])
    explanation = question_row["explanation"] or ""

    tg.send_quiz_poll(
        question_row["question_text"],
        options,
        question_row["correct_index"],
        explanation,
    )
    # Only sends a second message if the explanation didn't fit inline --
    # normal case is a single crisp sentence that fits in the poll itself.
    tg.send_full_explanation_if_needed(explanation, topic=topic)
    return True


def run_session(session_name):
    if session_name not in config.SESSION_TOPICS:
        raise SystemExit(f"Unknown session '{session_name}'. Use one of: {list(config.SESSION_TOPICS)}")

    topics = config.SESSION_TOPICS[session_name]
    print(f"Running '{session_name}' session for topics: {topics}")
    print(f"Fixed questions per topic: {config.QUESTIONS_PER_TOPIC} "
          f"-> {config.QUESTIONS_PER_TOPIC * len(topics)} total this session")
    print(f"Total unique words used so far (all-time): {db.used_words_count()}")

    sent = 0
    for topic in topics:
        for _ in range(config.QUESTIONS_PER_TOPIC):
            if send_new_question(topic):
                sent += 1

    print(f"Session complete: {sent}/{config.QUESTIONS_PER_TOPIC * len(topics)} questions sent successfully.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(f"Usage: python send_quiz.py <{'|'.join(config.SESSION_TOPICS)}>")

    if not (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID and config.GROQ_API_KEY):
        raise SystemExit(
            "Missing required env vars. Need TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, GROQ_API_KEY."
        )

    db.init_db()
    run_session(sys.argv[1])