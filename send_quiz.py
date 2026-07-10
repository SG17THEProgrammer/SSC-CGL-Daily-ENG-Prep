"""
Entry point run twice daily by GitHub Actions:
    python send_quiz.py morning
    python send_quiz.py evening

For each topic in the session:
  1. Send any revision-queue questions due today for that topic (spaced repetition).
  2. Generate and send N new questions, where N is adaptive based on recent accuracy.
"""

import json
import sys

import config
import database as db
import generator
import telegram_client as tg


def send_existing_question(question_row):
    options = json.loads(question_row["options"])
    poll_id = tg.send_quiz_poll(
        question_row["question_text"],
        options,
        question_row["correct_index"],
        question_row["explanation"],
    )
    db.record_sent_poll(poll_id, question_row["id"], config.TELEGRAM_CHAT_ID)


def send_new_question(topic):
    qid = generator.generate_unique_question(topic)
    if qid is None:
        print(f"Skipping send for topic={topic}: generation failed after retries")
        return
    question_row = db.get_question(qid)
    send_existing_question(question_row)


def run_session(session_name):
    if session_name not in config.SESSION_TOPICS:
        raise SystemExit(f"Unknown session '{session_name}'. Use 'morning' or 'evening'.")

    topics = config.SESSION_TOPICS[session_name]
    print(f"Running '{session_name}' session for topics: {topics}")

    # 1. Send due revision questions first (spaced repetition).
    due = db.get_due_revision_questions(topics)
    print(f"{len(due)} revision question(s) due today.")
    for row in due:
        send_existing_question(row)

    # 2. Send adaptive count of new questions per topic.
    for topic in topics:
        accuracy = db.get_topic_accuracy(topic)
        count = config.questions_for_accuracy(accuracy)
        print(f"Topic={topic} accuracy={accuracy} -> sending {count} new question(s)")
        for _ in range(count):
            send_new_question(topic)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python send_quiz.py <morning|evening>")

    if not (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID and config.GROQ_API_KEY):
        raise SystemExit(
            "Missing required env vars. Need TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, GROQ_API_KEY."
        )

    db.init_db()
    run_session(sys.argv[1])
