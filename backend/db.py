

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


# def insert_log(error_summary: str, analysis: str) -> int:
#     """Insert a log record and return the new log id."""
#     conn = sqlite3.connect(DB_FILE)
#     cursor = conn.cursor()
#     cursor.execute(
#         "INSERT INTO logs (error_message, analysis, created_at) VALUES (?, ?, ?)",
#         (error_summary, analysis, datetime.now().isoformat())
#     )
#     log_id = cursor.lastrowid
#     conn.commit()
#     conn.close()
#     return log_id

def insert_log(error_summary: str, analysis: str) -> int:
    """Insert a log record if it doesn't already exist, else return existing id."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Check if an identical log already exists
    cursor.execute(
        "SELECT id FROM logs WHERE error_message = ? AND analysis = ?",
        (error_summary, analysis)
    )
    existing = cursor.fetchone()
    if existing:
        conn.close()
        return existing[0]

    # Insert new log if not found
    cursor.execute(
        "INSERT INTO logs (error_message, analysis, created_at) VALUES (?, ?, ?)",
        (error_summary, analysis, datetime.now().isoformat())
    )
    log_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return log_id


def insert_feedback(log_id: int, feedback_choice: str, feedback_text: str) -> int:
    """Insert feedback linked to a log_id and return the new feedback id."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO feedback (log_id, feedback_choice, feedback_text, created_at) VALUES (?, ?, ?, ?)",
        (log_id, feedback_choice, feedback_text, datetime.now().isoformat())
    )
    feedback_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return feedback_id


def fetch_logs(limit: int = 10):
    """
    Fetch recent logs joined with feedback (if any).
    Returns rows with columns:
    (id, created_at, error_message, analysis, feedback_choice, feedback_text)
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # Return one row per log. If multiple feedback rows exist for a log, pick the latest feedback entry.
    cursor.execute("""
        SELECT
            l.id,
            l.created_at,
            l.error_message,
            l.analysis,
            (
                SELECT feedback_choice
                FROM feedback f2
                WHERE f2.log_id = l.id
                ORDER BY f2.created_at DESC
                LIMIT 1
            ) AS feedback_choice,
            (
                SELECT feedback_text
                FROM feedback f3
                WHERE f3.log_id = l.id
                ORDER BY f3.created_at DESC
                LIMIT 1
            ) AS feedback_text
        FROM logs l
        ORDER BY l.created_at DESC
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return rows


def fetch_logs_with_log_id(limit: int = 10):
    """
    Fetch recent logs whose analysis text contains a top-level "log_id" field.
    This uses a simple text-match on the analysis column and returns the same
    column layout as fetch_logs.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            l.id,
            l.created_at,
            l.error_message,
            l.analysis,
            (
                SELECT feedback_choice
                FROM feedback f2
                WHERE f2.log_id = l.id
                ORDER BY f2.created_at DESC
                LIMIT 1
            ) AS feedback_choice,
            (
                SELECT feedback_text
                FROM feedback f3
                WHERE f3.log_id = l.id
                ORDER BY f3.created_at DESC
                LIMIT 1
            ) AS feedback_text
        FROM logs l
        WHERE l.analysis LIKE '%"log_id"%'
        ORDER BY l.created_at DESC
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return rows


def fetch_log_by_id(log_id: int):
    """
    Fetch a single log row by id and include the latest feedback (if any).
    Returns a tuple in the same shape as fetch_logs: (id, created_at, error_message, analysis, feedback_choice, feedback_text)
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            l.id,
            l.created_at,
            l.error_message,
            l.analysis,
            (
                SELECT feedback_choice
                FROM feedback f2
                WHERE f2.log_id = l.id
                ORDER BY f2.created_at DESC
                LIMIT 1
            ) AS feedback_choice,
            (
                SELECT feedback_text
                FROM feedback f3
                WHERE f3.log_id = l.id
                ORDER BY f3.created_at DESC
                LIMIT 1
            ) AS feedback_text
        FROM logs l
        WHERE l.id = ?
        LIMIT 1
    """, (log_id,))
    row = cursor.fetchone()
    conn.close()
    return row