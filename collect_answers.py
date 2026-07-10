"""
Entry point run every ~15 minutes by GitHub Actions:
    python collect_answers.py

Telegram doesn't push poll answers to an ephemeral script -- they have to be
fetched via getUpdates. This script fetches any new updates since the last
run, matches poll_answer events back to the question that was sent, records
whether it was correct, and updates the spaced-repetition revision queue.
"""

import config
import database as db
import telegram_client as tg


def run():
    db.init_db()
    offset = db.get_last_update_id()
    updates = tg.get_updates(offset + 1 if offset else 0)

    if not updates:
        print("No new updates.")
        return

    highest_update_id = offset
    processed = 0

    for update in updates:
        highest_update_id = max(highest_update_id, update["update_id"])

        poll_answer = update.get("poll_answer")
        if not poll_answer:
            continue

        poll_id = poll_answer["poll_id"]
        selected = poll_answer.get("option_ids", [])
        if not selected:
            # User retracted their answer -- nothing to record.
            continue
        selected_index = selected[0]

        pending = db.get_pending_poll(poll_id)
        if pending is None:
            # Either already processed, or not one of ours.
            continue

        question = db.get_question(pending["question_id"])
        is_correct = selected_index == question["correct_index"]

        db.record_response(question["id"], question["topic"], selected_index, is_correct)
        db.mark_poll_answered(poll_id)

        if is_correct:
            db.advance_revision_correct(question["id"])
        else:
            db.upsert_revision_wrong(question["id"])

        processed += 1
        print(
            f"Recorded answer: topic={question['topic']} "
            f"correct={is_correct} question_id={question['id']}"
        )

    db.set_last_update_id(highest_update_id)
    print(f"Processed {processed} poll answer(s). Offset now {highest_update_id}.")


if __name__ == "__main__":
    if not (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID):
        raise SystemExit("Missing required env vars. Need TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID.")
    run()
