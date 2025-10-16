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
            FOREIGN KEY (log_id) REFERENCES logs(id) ON DELETE CASCADE
        )
    """)
    
    # Create indexes for better query performance
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_logs_created_at 
        ON logs(created_at DESC)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_feedback_log_id 
        ON feedback(log_id)
    """)
    
    conn.commit()
    conn.close()


def insert_log(error_summary: str, analysis: str) -> int:
    """Insert a log record and return its id."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    try:
        # Insert new log (removed duplicate check to allow analyzing same log multiple times)
        cursor.execute(
            "INSERT INTO logs (error_message, analysis, created_at) VALUES (?, ?, ?)",
            (error_summary, analysis, datetime.now().isoformat())
        )
        conn.commit()
        log_id = cursor.lastrowid
        return log_id
    except Exception as e:
        print(f"Error inserting log: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


def insert_feedback(log_id: int, feedback_choice: str, feedback_text: str):
    """Insert feedback linked to a log_id."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    try:
        # Check if feedback already exists for this log
        cursor.execute(
            "SELECT id FROM feedback WHERE log_id = ?",
            (log_id,)
        )
        existing = cursor.fetchone()
        
        if existing:
            # Update existing feedback
            cursor.execute(
                """UPDATE feedback 
                   SET feedback_choice = ?, feedback_text = ?, created_at = ? 
                   WHERE log_id = ?""",
                (feedback_choice, feedback_text, datetime.now().isoformat(), log_id)
            )
        else:
            # Insert new feedback
            cursor.execute(
                "INSERT INTO feedback (log_id, feedback_choice, feedback_text, created_at) VALUES (?, ?, ?, ?)",
                (log_id, feedback_choice, feedback_text, datetime.now().isoformat())
            )
        
        conn.commit()
    except Exception as e:
        print(f"Error inserting feedback: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


def fetch_logs(limit: int = 10):
    """
    Fetch recent logs joined with feedback (if any).
    Returns tuples:
    (id, created_at, error_message, analysis, feedback_choice, feedback_text)
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT
                l.id,
                l.created_at,
                l.error_message,
                l.analysis,
                f.feedback_choice,
                f.feedback_text
            FROM logs l
            LEFT JOIN feedback f ON f.log_id = l.id
            ORDER BY l.created_at DESC
            LIMIT ?
        """, (limit,))
        
        rows = cursor.fetchall()
        return rows
    except Exception as e:
        print(f"Error fetching logs: {e}")
        return []
    finally:
        conn.close()


def delete_log(log_id: int):
    """Delete a log and its associated feedback."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    try:
        # Delete feedback first (if not using CASCADE)
        cursor.execute("DELETE FROM feedback WHERE log_id = ?", (log_id,))
        # Delete log
        cursor.execute("DELETE FROM logs WHERE id = ?", (log_id,))
        conn.commit()
    except Exception as e:
        print(f"Error deleting log: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


def get_log_by_id(log_id: int):
    """Fetch a single log by its ID."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT
                l.id,
                l.created_at,
                l.error_message,
                l.analysis,
                f.feedback_choice,
                f.feedback_text
            FROM logs l
            LEFT JOIN feedback f ON f.log_id = l.id
            WHERE l.id = ?
        """, (log_id,))
        
        return cursor.fetchone()
    except Exception as e:
        print(f"Error fetching log by id: {e}")
        return None
    finally:
        conn.close()