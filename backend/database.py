"""The 'normal' relational DB — SQLite, holds the raw email records."""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "emails.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS emails (
            id TEXT PRIMARY KEY,
            client_name TEXT NOT NULL,
            client_email TEXT NOT NULL,
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            date TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def insert_email(email: dict):
    conn = get_connection()
    conn.execute(
        """
        INSERT OR REPLACE INTO emails (id, client_name, client_email, subject, body, date)
        VALUES (:id, :client_name, :client_email, :subject, :body, :date)
        """,
        email,
    )
    conn.commit()
    conn.close()


def list_emails():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM emails ORDER BY date DESC").fetchall()
    conn.close()
    return [dict(row) for row in rows]
