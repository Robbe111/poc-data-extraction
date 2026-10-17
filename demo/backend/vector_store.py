"""The vector DB — Chroma, running embedded/local with its built-in local
embedding model (no cloud embedding API, no separate server process).

Emails and attachments are split into overlapping chunks: the default embedding model
only looks at the first ~256 tokens of a text, so embedding a whole PDF would make
most of it unsearchable."""
import re

import chromadb

from config import CHUNK_OVERLAP, CHUNK_SIZE, DATA_DIR

CHROMA_PATH = DATA_DIR / "chroma_data"
COLLECTION = "chunks"

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def _extract_emails(raw: str) -> list[str]:
    """All plain addresses found in a From/To/CC field (order-preserving, deduped).
    Falls back to the whole lowercased string when nothing looks like an address, so
    legacy/malformed entries still get some identifier to filter on."""
    found, seen = [], set()
    for match in EMAIL_RE.findall(raw or ""):
        addr = match.lower()
        if addr not in seen:
            seen.add(addr)
            found.append(addr)
    if found:
        return found
    return [raw.strip().lower()] if raw and raw.strip() else []


def _participants(email: dict) -> list[str]:
    """Everyone involved in an email — sender plus every To/CC recipient — so a
    single address can be used to find mail both sent and received by that person."""
    people, seen = [], set()
    for field in (email["sender"], email["recipients"], email["cc"]):
        for addr in _extract_emails(field):
            if addr not in seen:
                seen.add(addr)
                people.append(addr)
    return people


_client = chromadb.PersistentClient(path=str(CHROMA_PATH))
_collection = _client.get_or_create_collection(name=COLLECTION)


def reset():
    global _collection
    _client.delete_collection(COLLECTION)
    _collection = _client.get_or_create_collection(name=COLLECTION)


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split on paragraph/line/word boundaries where possible, falling back to hard cuts."""
    text = text.strip()
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            for sep in ("\n\n", "\n", ". ", " "):
                cut = text.rfind(sep, start + size // 2, end)
                if cut != -1:
                    end = cut + len(sep)
                    break
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def add_emails(emails: list[dict]) -> int:
    """Chunk + embed a batch of emails in one upsert (much faster than one call per email)."""
    ids, documents, metadatas = [], [], []
    for email in emails:
        for chunk_id, document, metadata in _chunks_for_email(email):
            ids.append(chunk_id)
            documents.append(document)
            metadatas.append(metadata)
    if ids:
        _collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
    return len(ids)


def _chunks_for_email(email: dict):
    base = {
        "email_id": email["id"],
        "custodian": email["custodian"],
        "sender": email["sender"],
        "recipients": email["recipients"],
        "subject": email["subject"],
        "date": email["date"],
    }
    # One copy of each chunk per participant (sender + every To/CC), tagged with their address,
    # so filtering by one person's email finds mail they sent as well as mail they received.
    participants = _participants(email) or [""]

    # Subject is prepended to every body chunk so short replies still carry their topic.
    for i, chunk in enumerate(chunk_text(email["body"]) or [""]):
        document = f"{email['subject']}\n\n{chunk}".strip()
        meta = {**base, "source_type": "email", "attachment_id": "", "attachment_name": "", "chunk_index": i}
        for p, addr in enumerate(participants):
            yield (f"{email['id']}#body#{i}#{p}", document, {**meta, "email": addr})

    for attachment in email["attachments"]:
        for i, chunk in enumerate(chunk_text(attachment["text"])):
            meta = {
                **base,
                "source_type": attachment["extension"],
                "attachment_id": attachment["id"],
                "attachment_name": attachment["filename"],
                "chunk_index": i,
            }
            for p, addr in enumerate(participants):
                yield (f"{attachment['id']}#{i}#{p}", chunk, {**meta, "email": addr})


def search(query: str, n_results: int = 10, source_type: str | None = None, email: str | None = None):
    """email: restrict to mail sent OR received (To/CC) by this exact address (case-insensitive)."""
    conditions = []
    if source_type:
        conditions.append({"source_type": source_type})
    if email:
        conditions.append({"email": email.strip().lower()})
    where = {"$and": conditions} if len(conditions) > 1 else (conditions[0] if conditions else None)

    results = _collection.query(query_texts=[query], n_results=n_results, where=where)
    return [
        {"id": id_, "document": doc, "metadata": meta, "distance": dist}
        for id_, doc, meta, dist in zip(
            results["ids"][0], results["documents"][0], results["metadatas"][0], results["distances"][0]
        )
    ]
