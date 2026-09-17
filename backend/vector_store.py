"""The vector DB — Chroma, running embedded/local with its built-in local
embedding model (no cloud embedding API, no separate server process).

Emails and attachments are split into overlapping chunks: the default embedding model
only looks at the first ~256 tokens of a text, so embedding a whole PDF would make
most of it unsearchable."""
import chromadb

from config import CHUNK_OVERLAP, CHUNK_SIZE, DATA_DIR

CHROMA_PATH = DATA_DIR / "chroma_data"
COLLECTION = "chunks"

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
    # Subject is prepended to every body chunk so short replies still carry their topic.
    for i, chunk in enumerate(chunk_text(email["body"]) or [""]):
        yield (
            f"{email['id']}#body#{i}",
            f"{email['subject']}\n\n{chunk}".strip(),
            {**base, "source_type": "email", "attachment_id": "", "attachment_name": "", "chunk_index": i},
        )

    for attachment in email["attachments"]:
        for i, chunk in enumerate(chunk_text(attachment["text"])):
            yield (
                f"{attachment['id']}#{i}",
                chunk,
                {
                    **base,
                    "source_type": attachment["extension"],
                    "attachment_id": attachment["id"],
                    "attachment_name": attachment["filename"],
                    "chunk_index": i,
                },
            )


def search(query: str, n_results: int = 10, source_type: str | None = None):
    where = {"source_type": source_type} if source_type else None
    results = _collection.query(query_texts=[query], n_results=n_results, where=where)
    return [
        {"id": id_, "document": doc, "metadata": meta, "distance": dist}
        for id_, doc, meta, dist in zip(
            results["ids"][0], results["documents"][0], results["metadatas"][0], results["distances"][0]
        )
    ]
