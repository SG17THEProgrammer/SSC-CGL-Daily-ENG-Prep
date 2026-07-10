"""
Entry point run once a week (Sunday) by GitHub Actions:
    python weekly_summary.py

Computes accuracy over the last 7 days, overall and per topic, and sends
a formatted summary to Telegram. No dashboard/hosting needed for this.
"""

import config
import database as db
import telegram_client as tg


def build_summary_text():
    stats, total_q, total_c = db.get_weekly_stats(days=7)

    if total_q == 0:
        return "*Weekly Summary*\n\nNo questions were answered this week."

    overall_pct = round(100.0 * total_c / total_q, 1)

    lines = [
        "*SSC CGL English -- Weekly Summary*",
        "",
        f"Total questions attempted: {total_q}",
        f"Overall accuracy: {overall_pct}%",
        "",
        "*By topic:*",
    ]

    topic_rows = []
    for topic, v in stats.items():
        pct = round(100.0 * v["correct"] / v["total"], 1) if v["total"] else 0.0
        topic_rows.append((topic, pct, v["total"]))
        lines.append(f"- {topic.replace('_', ' ').title()}: {pct}% ({v['correct']}/{v['total']})")

    if topic_rows:
        strongest = max(topic_rows, key=lambda r: r[1])
        weakest = min(topic_rows, key=lambda r: r[1])
        lines += [
            "",
            f"Strongest topic: {strongest[0].replace('_', ' ').title()} ({strongest[1]}%)",
            f"Weakest topic: {weakest[0].replace('_', ' ').title()} ({weakest[1]}%)",
            "",
            f"Recommended focus: extra practice on "
            f"{weakest[0].replace('_', ' ')} next week.",
        ]

    return "\n".join(lines)


if __name__ == "__main__":
    if not (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID):
        raise SystemExit("Missing required env vars. Need TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID.")

    db.init_db()
    text = build_summary_text()
    tg.send_message(text)
    print("Weekly summary sent.")
