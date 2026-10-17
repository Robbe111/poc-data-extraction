"""MCP server: exposes the mailbox archive (emails + PDF attachments) as tools for Claude.

Runs locally over stdio — Claude Desktop / Claude Code start this script as a subprocess.
Claude does the conversation and the answering; this server only does retrieval.

    python backend/mcp_server.py          # normally started by Claude, not by hand

Note: with stdio, stdout is the protocol channel. Never print() to stdout in here.
"""
import contextlib
import sys
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).parent))  # Claude starts us from an arbitrary cwd

from mcp.server.mcpserver import MCPServer  # noqa: E402
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402

# Keep any chatter from library imports (Chroma, model loading) off the protocol channel.
with contextlib.redirect_stdout(sys.stderr):
    import citations  # noqa: E402
    import database  # noqa: E402
    import enron_dataset  # noqa: E402
    import vector_store  # noqa: E402
    from config import APP_BASE_URL  # noqa: E402

mcp = MCPServer(
    name="broker-mailbox",
    title="Broker mailbox archive",
    instructions=(
        "Search and read the broker's email archive: email bodies and the PDF attachments sent with them. "
        "Use search_documents for questions about content, list_emails for filtering by sender/date/subject, "
        "get_email and get_pdf_text to read a full item. Always ground answers in the retrieved text and cite "
        "the email subject, sender and date (and PDF filename). "
        "For every fact you take from a document, call cite with the exact sentence(s) you relied on, copied "
        "verbatim from the retrieved text, and put the returned highlight_url next to that fact as a markdown "
        "link (e.g. [p. 3](highlight_url)): it opens the original with the passage highlighted. Group quotes "
        "from the same document into one cite call. Prefer highlight_url over open_url."
    ),
)


def _pdf_url(attachment_id: str) -> str:
    return f"{APP_BASE_URL}/api/attachments/{attachment_id}"


@mcp.tool()
def get_dataset_overview() -> dict:
    """What is in the archive: number of emails and PDFs, mailboxes, date range and most frequent senders.
    Call this first if you don't know what data is available."""
    with contextlib.redirect_stdout(sys.stderr):
        return database.get_overview()


@mcp.tool()
def search_documents(
    query: str,
    source: Literal["all", "email", "pdf"] = "all",
    person_email: str | None = None,
    limit: int = 8,
) -> list[dict]:
    """Semantic search over email bodies and PDF attachment text.

    Args:
        query: natural-language description of what you're looking for (English works best).
        source: search everything, only email bodies, or only PDF attachments.
        person_email: restrict results to mail sent OR received (To/CC) by this exact address
            (e.g. "pete.davis@enron.com"). Omit to search across everyone.
        limit: max number of passages to return (1-25).

    Returns matching text passages with the email they belong to. Lower distance = more relevant.
    """
    limit = max(1, min(limit, 25))
    with contextlib.redirect_stdout(sys.stderr):
        # Over-fetch: the same email/PDF often sits in several mail folders (or, now, once per
        # participant), drop those duplicates.
        raw = vector_store.search(
            query,
            n_results=limit * 3,
            source_type=None if source == "all" else source,
            email=person_email,
        )

    results, seen = [], set()
    for hit in raw:
        if hit["document"] in seen:
            continue
        seen.add(hit["document"])
        m = hit["metadata"]
        result = {
            "text": hit["document"],
            "distance": round(hit["distance"], 3),
            "source": m["source_type"],
            "email_id": m["email_id"],
            "subject": m["subject"],
            "sender": m["sender"],
            "recipients": m["recipients"][:300],
            "date": m["date"],
        }
        if m.get("attachment_id"):
            result |= {
                "pdf_filename": m["attachment_name"],
                "attachment_id": m["attachment_id"],
                "open_url": _pdf_url(m["attachment_id"]),
            }
        results.append(result)
        if len(results) == limit:
            break
    return results


@mcp.tool()
def list_emails(
    sender: str | None = None,
    recipient: str | None = None,
    subject: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    with_attachments_only: bool = False,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """List emails filtered on metadata, newest first. All text filters are case-insensitive 'contains' matches.

    Args:
        sender: part of the sender name or address, e.g. "pete.davis" or "@enron.com".
        recipient: part of a To/CC name or address.
        subject: part of the subject line.
        date_from: ISO date, e.g. "2001-11-01".
        date_to: ISO date, inclusive.
        with_attachments_only: only emails that have a (PDF) attachment.
        limit: page size (max 100).
        offset: for paging.
    """
    with contextlib.redirect_stdout(sys.stderr):
        return database.search_emails(
            sender, recipient, subject, date_from, date_to, with_attachments_only, max(1, min(limit, 100)), offset
        )


@mcp.tool()
def get_email(email_id: str) -> dict:
    """Full email: sender, recipients, CC, date, folder, complete body and its attachments (with links)."""
    with contextlib.redirect_stdout(sys.stderr):
        email = database.get_email(email_id)
    if email is None:
        raise ToolError(f"No email with id {email_id!r}")
    for attachment in email["attachments"]:
        attachment["open_url"] = _pdf_url(attachment["id"])
    return email


@mcp.tool()
def get_pdf_text(attachment_id: str, offset: int = 0, max_chars: int = 20000) -> dict:
    """Full extracted text of a PDF attachment, plus a link to open the original PDF.

    Long PDFs are returned in pieces: if has_more is true, call again with offset=next_offset.
    """
    with contextlib.redirect_stdout(sys.stderr):
        attachment = database.get_attachment(attachment_id)
    if attachment is None:
        raise ToolError(f"No attachment with id {attachment_id!r}")
    text = attachment["text"]
    end = offset + max(1000, min(max_chars, 50000))
    return {
        "filename": attachment["filename"],
        "email_id": attachment["email_id"],
        "open_url": _pdf_url(attachment_id),
        "total_chars": len(text),
        "text": text[offset:end],
        "has_more": end < len(text),
        "next_offset": end if end < len(text) else None,
    }


@mcp.tool()
def cite(quotes: list[str], attachment_id: str | None = None, email_id: str | None = None) -> dict:
    """Get a link that opens a document with the given passages highlighted, so the user can see exactly
    where an answer comes from. Pass attachment_id for a PDF, or email_id for an email body.

    Args:
        quotes: one or more passages copied verbatim from the document's text (a sentence or a few
            lines each; at least a few words). Whitespace, case and punctuation differences are tolerated,
            paraphrases are not.

    Each quote is checked against the document; quotes that don't occur in it are reported back in
    not_found and left out of the link. Fix them (copy the text exactly) or drop the claim.
    """
    if bool(attachment_id) == bool(email_id):
        raise ToolError("Pass exactly one of attachment_id or email_id")
    quotes = [q for q in quotes if q.strip()]
    if not quotes:
        raise ToolError("Pass at least one quote")

    with contextlib.redirect_stdout(sys.stderr):
        if attachment_id:
            source = database.get_attachment(attachment_id)
            if source is None:
                raise ToolError(f"No attachment with id {attachment_id!r}")
            text, label = source["text"], source["filename"]
            try:
                pdf = enron_dataset.read_native(source["zip_name"], source["native_path"])
            except (FileNotFoundError, KeyError):
                pdf = None
        else:
            source = database.get_email(email_id)
            if source is None:
                raise ToolError(f"No email with id {email_id!r}")
            text, label, pdf = f"{source['subject']}\n\n{source['body']}", source["subject"], None

        found, not_found = [], []
        for quote in quotes:
            if not citations.find(quote, text):
                not_found.append(quote)
                continue
            entry = {"quote": quote}
            if pdf and (page := citations.pdf_page_of(quote, pdf)):
                entry["page"] = page
            found.append(entry)

    if not found:
        raise ToolError(
            f"None of the quotes occur in {label!r}. Copy them verbatim from get_pdf_text / get_email / "
            "search_documents output."
        )
    return {
        "source": label,
        "highlight_url": citations.viewer_url(
            [f["quote"] for f in found], attachment_id=attachment_id, email_id=email_id
        ),
        "found": found,
        "not_found": not_found,
    }


if __name__ == "__main__":
    mcp.run("stdio")
