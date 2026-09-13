"""The vector DB — Chroma, running embedded/local with its built-in local
embedding model (no cloud embedding API, no separate server process)."""
from pathlib import Path

import chromadb

CHROMA_PATH = Path(__file__).parent / "chroma_data"

_client = chromadb.PersistentClient(path=str(CHROMA_PATH))
_collection = _client.get_or_create_collection(name="emails")


def add_email(email: dict):
    _collection.upsert(
        ids=[email["id"]],
        documents=[f"{email['subject']}\n\n{email['body']}"],
        metadatas=[
            {
                "client_name": email["client_name"],
                "client_email": email["client_email"],
                "subject": email["subject"],
                "date": email["date"],
            }
        ],
    )


def search(query: str, n_results: int = 5):
    results = _collection.query(query_texts=[query], n_results=n_results)
    matches = []
    ids = results["ids"][0]
    documents = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]
    for i in range(len(ids)):
        matches.append(
            {
                "id": ids[i],
                "document": documents[i],
                "metadata": metadatas[i],
                "distance": distances[i],
            }
        )
    return matches
