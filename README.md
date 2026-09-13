# Verzekeringen prototype

Rough prototype: a normal DB (SQLite) with sample emails, a vector DB (Chroma, local) for semantic search over them, a FastAPI backend, and a simple web UI.

## Setup

```
pip install -r requirements.txt
```

## Seed the databases

Generates a couple of sample emails and stores them in both DBs (only needed once, or run again to add more):

```
python backend/seed_data.py
```

## Run

```
uvicorn main:app --reload --app-dir backend
```

Open **http://127.0.0.1:8000** in your browser.

- The page lists all emails from the SQLite DB.
- The search box does a semantic search against the Chroma vector DB (e.g. try "schade aan mijn wagen").
