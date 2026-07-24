"""
Entry point run once a week (Sunday) by GitHub Actions:
    python weekly_summary.py

Reports practice VOLUME and topic coverage over the last 7 days. Accuracy
tracking was removed along with the answer-collector (per your request to
drop it for speed), so this reports what's still knowable: how many
questions you were sent, per topic, and your total vocabulary coverage
so far -- useful for confirming the bot is actually running consistently
in the run-up to Aug 1.
"""

import config
import database as db
import telegram_client as tg


def build_summary_text():
    stats, total = db.get_weekly_volume_stats(days=7)
    total_words_ever = db.used_words_count()

    if total == 0:
        return (
            "*SBI PO English -- Weekly Summary*\n\n"
            "No questions were sent this week. Check the GitHub Actions tab "
            "for failed workflow runs."
        )

    lines = [
        "*SBI PO English -- Weekly Summary*",
        "",
        f"Questions sent this week: {total}",
        f"Total unique words/concepts covered so far: {total_words_ever}",
        "",
        "*By topic (last 7 days):*",
    ]
    for topic, count in sorted(stats.items(), key=lambda x: -x[1]):
        lines.append(f"- {topic.replace('_', ' ').title()}: {count}")

    return "\n".join(lines)


if __name__ == "__main__":
    if not (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID):
        raise SystemExit("Missing required env vars. Need TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID.")

    db.init_db()
    text = build_summary_text()
    tg.send_message(text)
    print("Weekly summary sent.")