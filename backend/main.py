from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from database import init_db, list_emails
import vector_store

app = FastAPI(title="Verzekeringen prototype")

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


@app.on_event("startup")
def on_startup():
    init_db()


class SearchRequest(BaseModel):
    query: str


@app.get("/api/emails")
def get_emails():
    return list_emails()


@app.post("/api/search")
def search_emails(request: SearchRequest):
    return vector_store.search(request.query)


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
