from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from database import get_attachment, get_email, init_db, list_emails
import demo_dataset
import enron_dataset
import vector_store

app = FastAPI(title="Verzekeringen prototype")

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


@app.on_event("startup")
def on_startup():
    init_db()


class SearchRequest(BaseModel):
    query: str
    n_results: int = 10
    source_type: str | None = None  # "email", "pdf", ... or None for everything


@app.get("/api/emails")
def get_emails(limit: int = 50, offset: int = 0):
    return list_emails(limit=limit, offset=offset)


@app.get("/api/emails/{email_id}")
def get_email_detail(email_id: str):
    email = get_email(email_id)
    if email is None:
        raise HTTPException(404, "Email not found")
    return email


@app.post("/api/search")
def search_emails(request: SearchRequest):
    return vector_store.search(request.query, request.n_results, request.source_type)


MEDIA_TYPES = {"pdf": "application/pdf"}


@app.get("/api/attachments/{attachment_id}")
def open_attachment(attachment_id: str):
    attachment = get_attachment(attachment_id)
    if not attachment or not attachment["native_path"]:
        raise HTTPException(404, "Attachment not found")
    try:
        if attachment["zip_name"]:
            content = enron_dataset.read_native(attachment["zip_name"], attachment["native_path"])
        else:
            content = demo_dataset.read_native(attachment["native_path"])
    except (FileNotFoundError, KeyError):
        raise HTTPException(404, "Original file not in the local dataset cache")
    filename = attachment["filename"].replace('"', "")
    return Response(
        content,
        media_type=MEDIA_TYPES.get(attachment["extension"], "application/octet-stream"),
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@app.get("/api/attachments/{attachment_id}/info")
def attachment_info(attachment_id: str):
    """Metadata for the document viewer: the attachment plus the email it came with."""
    attachment = get_attachment(attachment_id)
    if not attachment:
        raise HTTPException(404, "Attachment not found")
    email = get_email(attachment["email_id"])
    return {
        "id": attachment_id,
        "filename": attachment["filename"],
        "extension": attachment["extension"],
        "has_original": bool(attachment["native_path"]),
        "text": attachment["text"],  # fallback when the original can't be rendered
        "email": {k: email[k] for k in ("id", "subject", "sender", "date")} if email else None,
    }


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
