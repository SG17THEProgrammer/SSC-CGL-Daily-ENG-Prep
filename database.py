"""
All SQLite access lives here. The database.db file itself is committed back
to the git repo by the GitHub Actions workflows after every run -- that's
what makes state persist without any external database service.
"""

import sqlite3
import hashlib
import json
from datetime import date, datetime, timedelta

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL,
    question_text TEXT NOT NULL,
    question_hash TEXT NOT NULL UNIQUE,
    focus_word TEXT,              -- the core word/idiom this question tests
    options TEXT NOT NULL,        -- JSON array of 4 strings
    correct_index INTEGER NOT NULL,  -- 0-based index into options
    explanation TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sent_polls (
    poll_id TEXT PRIMARY KEY,
    question_id INTEGER NOT NULL,
    telegram_chat_id TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    answered INTEGER DEFAULT 0,
    FOREIGN KEY (question_id) REFERENCES questions (id)
);

CREATE TABLE IF NOT EXISTS responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id INTEGER NOT NULL,
    topic TEXT NOT NULL,
    selected_index INTEGER,
    is_correct INTEGER NOT NULL,
    answered_at TEXT NOT NULL,
    FOREIGN KEY (question_id) REFERENCES questions (id)
);

CREATE TABLE IF NOT EXISTS revision_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id INTEGER NOT NULL UNIQUE,
    interval_days INTEGER DEFAULT 1,
    next_review_date TEXT NOT NULL,
    correct_streak INTEGER DEFAULT 0,
    FOREIGN KEY (question_id) REFERENCES questions (id)
);

CREATE TABLE IF NOT EXISTS update_offset (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    last_update_id INTEGER DEFAULT 0
);
"""


def get_conn():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_conn()
    conn.executescript(SCHEMA)
    conn.execute(
        "INSERT OR IGNORE INTO update_offset (id, last_update_id) VALUES (1, 0)"
    )
    conn.commit()
    conn.close()
    _migrate()


def _migrate():
    """Add columns to an existing database.db that predates this column."""
    conn = get_conn()
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(questions)").fetchall()]
    if "focus_word" not in cols:
        conn.execute("ALTER TABLE questions ADD COLUMN focus_word TEXT")
        conn.commit()
    conn.close()


def _normalize(text):
    return " ".join(text.lower().split())


def hash_question(question_text):
    return hashlib.sha256(_normalize(question_text).encode("utf-8")).hexdigest()


def question_exists(question_text):
    h = hash_question(question_text)
    conn = get_conn()
    row = conn.execute(
        "SELECT id FROM questions WHERE question_hash = ?", (h,)
    ).fetchone()
    conn.close()
    return row is not None


def save_question(topic, question_text, options, correct_index, explanation, focus_word=None):
    h = hash_question(question_text)
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO questions
           (topic, question_text, question_hash, focus_word, options, correct_index, explanation, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            topic,
            question_text,
            h,
            focus_word,
            json.dumps(options),
            correct_index,
            explanation,
            datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()
    qid = cur.lastrowid
    conn.close()
    return qid


def get_recent_focus_words(limit=60):
    """Recent focus words across ALL topics, most recent first -- used to tell
    the generator which words are off-limits so it doesn't reuse the same
    word across different topics/sessions."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT DISTINCT focus_word FROM questions
           WHERE focus_word IS NOT NULL AND focus_word != ''
           ORDER BY created_at DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()
    return [r["focus_word"] for r in rows]


def get_question(question_id):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM questions WHERE id = ?", (question_id,)
    ).fetchone()
    conn.close()
    return row


def record_sent_poll(poll_id, question_id, chat_id):
    conn = get_conn()
    conn.execute(
        """INSERT INTO sent_polls (poll_id, question_id, telegram_chat_id, sent_at)
           VALUES (?, ?, ?, ?)""",
        (poll_id, question_id, chat_id, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def get_pending_poll(poll_id):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM sent_polls WHERE poll_id = ? AND answered = 0", (poll_id,)
    ).fetchone()
    conn.close()
    return row


def mark_poll_answered(poll_id):
    conn = get_conn()
    conn.execute("UPDATE sent_polls SET answered = 1 WHERE poll_id = ?", (poll_id,))
    conn.commit()
    conn.close()


def record_response(question_id, topic, selected_index, is_correct):
    conn = get_conn()
    conn.execute(
        """INSERT INTO responses (question_id, topic, selected_index, is_correct, answered_at)
           VALUES (?, ?, ?, ?, ?)""",
        (question_id, topic, selected_index, int(is_correct), datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def get_topic_accuracy(topic, window=None):
    window = window or config.ACCURACY_WINDOW
    conn = get_conn()
    rows = conn.execute(
        """SELECT is_correct FROM responses
           WHERE topic = ?
           ORDER BY answered_at DESC
           LIMIT ?""",
        (topic, window),
    ).fetchall()
    conn.close()
    if not rows:
        return None
    correct = sum(r["is_correct"] for r in rows)
    return round(100.0 * correct / len(rows), 1)


def get_last_update_id():
    conn = get_conn()
    row = conn.execute("SELECT last_update_id FROM update_offset WHERE id = 1").fetchone()
    conn.close()
    return row["last_update_id"] if row else 0


def set_last_update_id(update_id):
    conn = get_conn()
    conn.execute("UPDATE update_offset SET last_update_id = ? WHERE id = 1", (update_id,))
    conn.commit()
    conn.close()


# --- Revision queue / spaced repetition ---

def upsert_revision_wrong(question_id):
    """Answered wrong -> reset to the front of the revision queue."""
    conn = get_conn()
    next_date = (date.today() + timedelta(days=config.REVISION_INITIAL_INTERVAL_DAYS)).isoformat()
    existing = conn.execute(
        "SELECT id FROM revision_queue WHERE question_id = ?", (question_id,)
    ).fetchone()
    if existing:
        conn.execute(
            """UPDATE revision_queue
               SET interval_days = ?, next_review_date = ?, correct_streak = 0
               WHERE question_id = ?""",
            (config.REVISION_INITIAL_INTERVAL_DAYS, next_date, question_id),
        )
    else:
        conn.execute(
            """INSERT INTO revision_queue (question_id, interval_days, next_review_date, correct_streak)
               VALUES (?, ?, ?, 0)""",
            (question_id, config.REVISION_INITIAL_INTERVAL_DAYS, next_date),
        )
    conn.commit()
    conn.close()


def advance_revision_correct(question_id):
    """Answered correctly while in the revision queue -> push interval out, or retire."""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM revision_queue WHERE question_id = ?", (question_id,)
    ).fetchone()
    if not row:
        conn.close()
        return
    streak = row["correct_streak"] + 1
    if streak >= config.REVISION_STREAK_TO_RETIRE:
        conn.execute("DELETE FROM revision_queue WHERE question_id = ?", (question_id,))
    else:
        new_interval = min(
            row["interval_days"] * config.REVISION_INTERVAL_MULTIPLIER,
            config.REVISION_MAX_INTERVAL_DAYS,
        )
        next_date = (date.today() + timedelta(days=new_interval)).isoformat()
        conn.execute(
            """UPDATE revision_queue
               SET interval_days = ?, next_review_date = ?, correct_streak = ?
               WHERE question_id = ?""",
            (new_interval, next_date, streak, question_id),
        )
    conn.commit()
    conn.close()


def get_due_revision_questions(topics):
    """Questions due for revision today, restricted to the given topic list."""
    if not topics:
        return []
    conn = get_conn()
    placeholders = ",".join("?" for _ in topics)
    rows = conn.execute(
        f"""SELECT q.* FROM revision_queue r
            JOIN questions q ON q.id = r.question_id
            WHERE r.next_review_date <= ? AND q.topic IN ({placeholders})
            ORDER BY r.next_review_date ASC""",
        (date.today().isoformat(), *topics),
    ).fetchall()
    conn.close()
    return rows


def get_weekly_stats(days=7):
    conn = get_conn()
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()
    rows = conn.execute(
        """SELECT topic, is_correct FROM responses WHERE answered_at >= ?""",
        (since,),
    ).fetchall()
    conn.close()

    stats = {}
    for r in rows:
        t = r["topic"]
        stats.setdefault(t, {"correct": 0, "total": 0})
        stats[t]["total"] += 1
        stats[t]["correct"] += r["is_correct"]

    total_q = sum(v["total"] for v in stats.values())
    total_c = sum(v["correct"] for v in stats.values())
    return stats, total_q, total_c