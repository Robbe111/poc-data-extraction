"""The vector DB — Chroma, running embedded/local, with a local multilingual embedding
model via fastembed (ONNX; no cloud embedding API, no PyTorch, no separate server process).

Emails and attachments are split into overlapping chunks: embedding models only look at
the first few hundred tokens of a text, so embedding a whole PDF would make most of it
unsearchable.

We embed ourselves instead of letting Chroma do it, so identical texts (the same PDF sent
to several clients) are embedded once, and queries and passages can get the different
prefixes that E5 models expect."""
import re

import chromadb
from fastembed import TextEmbedding

from config import CHUNK_OVERLAP, CHUNK_SIZE, DATA_DIR, EMBEDDING_MODEL

CHROMA_PATH = DATA_DIR / "chroma_data"
# One collection per embedding model: vectors of different models can't be mixed.
COLLECTION = "chunks-" + re.sub(r"[^a-zA-Z0-9._-]", "-", EMBEDDING_MODEL.split("/")[-1])
# E5 models are trained with these prefixes; other models get the plain text.
IS_E5 = "e5" in EMBEDDING_MODEL.lower()
QUERY_PREFIX, PASSAGE_PREFIX = ("query: ", "passage: ") if IS_E5 else ("", "")

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
_collection = _client.get_or_create_collection(
    name=COLLECTION, embedding_function=None, configuration={"hnsw": {"space": "cosine"}}
)
_model = None  # loaded on first use: the first run downloads the model (~2 GB for e5-large)


def _embedder() -> TextEmbedding:
    global _model
    if _model is None:
        _model = TextEmbedding(EMBEDDING_MODEL)
    return _model


def _embed(texts: list[str], prefix: str) -> list[list[float]]:
    return [v.tolist() for v in _embedder().embed([prefix + t for t in texts], batch_size=32)]


def reset():
    global _collection
    _client.delete_collection(COLLECTION)
    _collection = _client.get_or_create_collection(
        name=COLLECTION, embedding_function=None, configuration={"hnsw": {"space": "cosine"}}
    )


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


def add_emails(emails: list[dict], batch_size: int = 1000) -> int:
    """Chunk + embed emails and upsert them in batches (much faster than one call per email).

    Batched because Chroma caps the size of one upsert, and so that progress is visible and
    finished batches are stored even if a later one fails."""
    chunks = [chunk for email in emails for chunk in _chunks_for_email(email)]
    batch_size = min(batch_size, _client.get_max_batch_size())
    vectors: dict[str, list[float]] = {}  # identical texts across batches are embedded once
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start:start + batch_size]
        ids, documents, metadatas = map(list, zip(*batch))
        new = [d for d in dict.fromkeys(documents) if d not in vectors]
        vectors.update(zip(new, _embed(new, PASSAGE_PREFIX)))
        _collection.upsert(
            ids=ids, documents=documents, metadatas=metadatas, embeddings=[vectors[d] for d in documents]
        )
        print(f"  {start + len(batch)}/{len(chunks)} chunks stored ({len(vectors)} embedded)", flush=True)
    return len(chunks)


def _chunks_for_email(email: dict):
    base = {
        "email_id": email["id"],
        "custodian": email["custodian"],
        "sender": email["sender"],
        "recipients": email["recipients"],
        "subject": email["subject"],
        "date": email["date"],
    }
    # Everyone involved (sender + every To/CC), so filtering on one address finds mail
    # that person sent as well as mail they received.
    participants = _participants(email)
    if participants:
        base["participants"] = participants

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


def search(query: str, n_results: int = 10, source_type: str | None = None, email: str | None = None):
    """Semantic search; returns up to n_results hits with distinct text.

    email: restrict to mail sent OR received (To/CC) by this exact address (case-insensitive).
    """
    conditions = []
    if source_type:
        conditions.append({"source_type": source_type})
    if email:
        conditions.append({"participants": {"$contains": email.strip().lower()}})
    where = {"$and": conditions} if len(conditions) > 1 else (conditions[0] if conditions else None)

    # Over-fetch: the same text is often stored several times (one PDF sent to several
    # clients, one email in several folders); keep only the best-ranked copy.
    results = _collection.query(
        query_embeddings=_embed([query], QUERY_PREFIX), n_results=n_results * 10, where=where
    )
    hits, seen = [], set()
    for id_, doc, meta, dist in zip(
        results["ids"][0], results["documents"][0], results["metadatas"][0], results["distances"][0]
    ):
        if doc in seen:
            continue
        seen.add(doc)
        hits.append({"id": id_, "document": doc, "metadata": meta, "distance": dist})
        if len(hits) == n_results:
            break
    return hits
