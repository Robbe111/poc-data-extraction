"""The 'normal' relational DB — SQLite, holds the raw email and attachment records."""
import sqlite3

from config import DATA_DIR

DB_PATH = DATA_DIR / "emails.db"


def get_connection():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS emails (
            id TEXT PRIMARY KEY,
            custodian TEXT NOT NULL,
            sender TEXT NOT NULL,
            recipients TEXT NOT NULL,
            cc TEXT NOT NULL,
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            date TEXT NOT NULL,
            folder TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS attachments (
            id TEXT PRIMARY KEY,
            email_id TEXT NOT NULL REFERENCES emails(id),
            filename TEXT NOT NULL,
            extension TEXT NOT NULL,
            text TEXT NOT NULL,
            zip_name TEXT NOT NULL,
            native_path TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_attachments_email ON attachments(email_id);
        """
    )
    conn.commit()
    conn.close()


def reset_db():
    conn = get_connection()
    conn.executescript("DROP TABLE IF EXISTS attachments; DROP TABLE IF EXISTS emails;")
    conn.close()
    init_db()


def insert_email(email: dict):
    conn = get_connection()
    conn.execute(
        """
        INSERT OR REPLACE INTO emails (id, custodian, sender, recipients, cc, subject, body, date, folder)
        VALUES (:id, :custodian, :sender, :recipients, :cc, :subject, :body, :date, :folder)
        """,
        email,
    )
    conn.executemany(
        """
        INSERT OR REPLACE INTO attachments (id, email_id, filename, extension, text, zip_name, native_path)
        VALUES (:id, :email_id, :filename, :extension, :text, :zip_name, :native_path)
        """,
        [{**a, "email_id": email["id"]} for a in email["attachments"]],
    )
    conn.commit()
    conn.close()


def list_emails(limit: int = 100, offset: int = 0):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM emails ORDER BY date DESC LIMIT ? OFFSET ?", (limit, offset)
    ).fetchall()
    emails = [dict(row) for row in rows]
    for email in emails:
        email["attachments"] = [
            dict(a)
            for a in conn.execute(
                "SELECT id, filename, extension FROM attachments WHERE email_id = ?", (email["id"],)
            )
        ]
    total = conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
    conn.close()
    return {"total": total, "emails": emails}


def get_attachment(attachment_id: str):
    conn = get_connection()
    row = conn.execute("SELECT * FROM attachments WHERE id = ?", (attachment_id,)).fetchone()
    conn.close()
    return dict(row) if row else None
