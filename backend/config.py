"""Settings, driven by env vars so the dataset subset can change without code edits."""
import os
from pathlib import Path

BACKEND_DIR = Path(__file__).parent
DATA_DIR = Path(os.getenv("DATA_DIR", BACKEND_DIR.parent / "data"))

# EDRM Enron Email Data Set v2 (XML flavour), mirrored per custodian on the Internet Archive.
ENRON_BASE_URL = os.getenv(
    "ENRON_BASE_URL",
    "https://archive.org/download/edrm.enron.email.data.set.v2.xml",
)
ENRON_CACHE_DIR = DATA_DIR / "enron"

# Which part of the ~80 GB dataset to ingest. Custodians are mailbox owners, e.g.
# "meyers-a" (6 MB, ~1.2k emails, 14 PDFs). Run `python backend/ingest_enron.py --list`
# to see all custodians with their download size.
ENRON_CUSTODIANS = [
    c.strip() for c in os.getenv("ENRON_CUSTODIANS", "meyers-a").split(",") if c.strip()
]
# Max emails per custodian; 0 = no limit.
ENRON_MAX_EMAILS = int(os.getenv("ENRON_MAX_EMAILS", "0"))
# Attachment types to index next to the email bodies.
ENRON_ATTACHMENT_EXTENSIONS = {
    e.strip().lower() for e in os.getenv("ENRON_ATTACHMENT_EXTENSIONS", "pdf").split(",") if e.strip()
}

# Synthetic demo mailbox of a (fictional) Belgian broker: hand-written emails in demo/,
# with real AXA/KBC general conditions as PDF attachments, downloaded into DEMO_CACHE_DIR.
DEMO_DIR = BACKEND_DIR.parent / "demo"
DEMO_CACHE_DIR = DATA_DIR / "demo"

# Local embedding model (fastembed, ONNX: no PyTorch). Must be multilingual: the demo mailbox is
# Dutch. Changing it needs a re-ingest; each model gets its own Chroma collection.
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-large")

CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))  # characters
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "150"))

# Where the web app runs; used by the MCP server to hand out links to original PDFs.
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://127.0.0.1:8000")
