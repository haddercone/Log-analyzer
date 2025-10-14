import sqlite3
from datetime import datetime

DB_FILE = "log_history.db"


def init_db():
    """Initialize logs + feedback tables (idempotent)."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            error_message TEXT,
            analysis TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            log_id INTEGER,
            feedback_choice TEXT,
            feedback_text TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (log_id) REFERENCES logs(id)
        )
    """)

    conn.commit()
    conn.close()


def insert_log(error_summary: str, analysis: str) -> int:
    """Insert a log record and return the new log id."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO logs (error_message, analysis, created_at) VALUES (?, ?, ?)",
        (error_summary, analysis, datetime.now().isoformat())
    )
    log_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return log_id


def insert_feedback(log_id: int, feedback_choice: str, feedback_text: str):
    """Insert feedback linked to a log_id."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO feedback (log_id, feedback_choice, feedback_text, created_at) VALUES (?, ?, ?, ?)",
        (log_id, feedback_choice, feedback_text, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def fetch_logs(limit: int = 10):
    """
    Fetch recent logs joined with feedback (if any).
    Returns rows with columns:
    (id, created_at, error_message, analysis, feedback_choice, feedback_text)
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT l.id, l.created_at, l.error_message, l.analysis, f.feedback_choice, f.feedback_text
        FROM logs l
        LEFT JOIN feedback f ON l.id = f.log_id
        ORDER BY l.created_at DESC
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return rows
