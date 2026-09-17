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


def search_emails(
    sender: str | None = None,
    recipient: str | None = None,
    subject: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    with_attachments_only: bool = False,
    limit: int = 20,
    offset: int = 0,
):
    """Structured (non-semantic) filtering on email metadata."""
    clauses, params = [], []
    if sender:
        clauses.append("e.sender LIKE ?")
        params.append(f"%{sender}%")
    if recipient:
        clauses.append("(e.recipients LIKE ? OR e.cc LIKE ?)")
        params += [f"%{recipient}%", f"%{recipient}%"]
    if subject:
        clauses.append("e.subject LIKE ?")
        params.append(f"%{subject}%")
    if date_from:
        clauses.append("e.date >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("e.date <= ?")
        params.append(date_to + "T23:59:59" if len(date_to) == 10 else date_to)
    if with_attachments_only:
        clauses.append("EXISTS (SELECT 1 FROM attachments a WHERE a.email_id = e.id)")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    conn = get_connection()
    total = conn.execute(f"SELECT COUNT(*) FROM emails e {where}", params).fetchone()[0]
    rows = conn.execute(
        f"""
        SELECT e.id, e.sender, e.recipients, e.subject, e.date, e.folder,
               (SELECT GROUP_CONCAT(a.filename, ', ') FROM attachments a WHERE a.email_id = e.id) AS attachments
        FROM emails e {where}
        ORDER BY e.date DESC LIMIT ? OFFSET ?
        """,
        params + [limit, offset],
    ).fetchall()
    conn.close()
    return {"total": total, "emails": [dict(r) for r in rows]}


def get_email(email_id: str):
    conn = get_connection()
    row = conn.execute("SELECT * FROM emails WHERE id = ?", (email_id,)).fetchone()
    if row is None:
        conn.close()
        return None
    email = dict(row)
    email["attachments"] = [
        dict(a)
        for a in conn.execute(
            "SELECT id, filename, extension, LENGTH(text) AS text_length FROM attachments WHERE email_id = ?",
            (email_id,),
        )
    ]
    conn.close()
    return email


def get_overview():
    conn = get_connection()
    overview = {
        "emails": conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0],
        "attachments": conn.execute("SELECT COUNT(*) FROM attachments").fetchone()[0],
        "mailboxes": [r[0] for r in conn.execute("SELECT DISTINCT custodian FROM emails ORDER BY 1")],
        "date_range": dict(conn.execute("SELECT MIN(date) AS first, MAX(date) AS last FROM emails").fetchone()),
        "top_senders": [
            {"sender": r[0], "emails": r[1]}
            for r in conn.execute(
                "SELECT sender, COUNT(*) FROM emails GROUP BY sender ORDER BY 2 DESC LIMIT 10"
            )
        ],
    }
    conn.close()
    return overview
