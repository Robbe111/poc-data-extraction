# Verzekeringen prototype

Rough prototype: a normal DB (SQLite) with emails + attachments, a vector DB (Chroma, local) for semantic search over email bodies and PDF attachments, a FastAPI backend, and a simple web UI.

As a stand-in for a broker mailbox we use the [EDRM Enron Email Data Set v2](https://enrondata.readthedocs.io/en/latest/data/edrm-enron-email-datasets/) (XML version, mirrored per custodian on the [Internet Archive](https://archive.org/details/edrm.enron.email.data.set.v2.xml)). The full set is ~80 GB, so we only ingest a few custodians (= mailboxes).

## Setup

```
pip install -r requirements.txt
```

## Load data

```
python backend/ingest_enron.py --list          # all custodians, smallest first, with download size
python backend/ingest_enron.py --reset         # ingest the default subset (meyers-a: 6 MB, ~1.2k emails, 14 PDFs, ~1 min)
python backend/ingest_enron.py -c meyers-a king-j --max-emails 300 --reset
```

Zips are cached in `data/enron/`; the SQLite DB and Chroma store also live in `data/` (gitignored). Without `--reset`, runs add to what's already there (re-ingesting the same emails is idempotent).

Defaults can also be set via env vars (see `backend/config.py`):

| Env var | Default | Meaning |
|---|---|---|
| `ENRON_CUSTODIANS` | `meyers-a` | comma-separated custodians to ingest |
| `ENRON_MAX_EMAILS` | `0` | max emails per custodian (0 = all) |
| `ENRON_ATTACHMENT_EXTENSIONS` | `pdf` | attachment types to index (e.g. `pdf,doc,xls` — non-PDFs use EDRM's pre-extracted text) |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `1000` / `150` | chunking, in characters |

PDFs are parsed with `pypdf`; if that yields no text, EDRM's pre-extracted text is used. Enron mail is from 2000–2002, so PDFs are relatively rare — custodians with a decent number of PDFs among the small ones: `meyers-a`, `king-j`, `townsend-j`, `motley-m`, `solberg-g`, `platter-p`.

## Run

```
uvicorn main:app --reload --app-dir backend
```

Open **http://127.0.0.1:8000** in your browser.

- The page lists the emails from the SQLite DB (paged), with their PDF attachments.
- The search box does a semantic search against the Chroma vector DB, over email bodies, PDFs, or both (e.g. try "western electricity price cap").
