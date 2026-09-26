"""Source adapter for the synthetic demo mailbox of a (fictional) Belgian insurance broker.

The emails are hand-written in demo/mailbox/*.yaml, the people in them in demo/contacts.yaml.
Attachments are real, public general conditions of AXA Belgium and KBC (demo/documents.yaml),
downloaded into data/demo/ on first use rather than committed.

Yields the same dicts as enron_dataset, so the rest of the pipeline doesn't care where
emails come from.
"""
import re
from datetime import datetime
from pathlib import Path
from typing import Iterator
from zoneinfo import ZoneInfo

import requests
import yaml

import config
from enron_dataset import extract_pdf_text

MAILBOX = "hoflandt"
BROKER_DOMAIN = "@hoflandt.be"
TZ = ZoneInfo("Europe/Brussels")
# Some insurer CDNs refuse requests without a browser-like user agent.
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

ADDRESS_RE = re.compile(r"^\s*(?P<name>.*?)\s*<(?P<email>[^>]+)>\s*$")


def load_contacts() -> dict:
    with open(config.DEMO_DIR / "contacts.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_documents() -> dict[str, dict]:
    with open(config.DEMO_DIR / "documents.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def download(key: str, document: dict) -> Path:
    config.DEMO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    target = config.DEMO_CACHE_DIR / f"{key}.pdf"
    if target.exists():
        return target
    print(f"  downloading {document['filename']}")
    try:
        r = requests.get(document["url"], headers={"User-Agent": USER_AGENT}, timeout=60)
        r.raise_for_status()
    except requests.RequestException as exc:
        raise SystemExit(
            f"Could not download {document['url']} ({exc}).\n"
            f"Download it by hand and save it as {target}, then run this again."
        )
    if not r.content.startswith(b"%PDF"):
        raise SystemExit(f"{document['url']} did not return a PDF; save the file by hand as {target}.")
    target.write_bytes(r.content)
    return target


def iter_emails() -> Iterator[dict]:
    names = _address_book(load_contacts())
    documents = load_documents()
    texts: dict[str, str] = {}  # the same PDF is attached to several emails; parse it once

    for path in sorted((config.DEMO_DIR / "mailbox").glob("*.yaml")):
        with open(path, encoding="utf-8") as f:
            emails = yaml.safe_load(f) or []
        for email in emails:
            sender = _address(email["from"], names)
            attachments = []
            for i, key in enumerate(email.get("attachments") or [], start=1):
                if key not in documents:
                    raise SystemExit(f"{path.name}: {email['id']} attaches unknown document {key!r}")
                if key not in texts:
                    texts[key] = _clean(extract_pdf_text(download(key, documents[key]).read_bytes()))
                attachments.append({
                    "id": f"{email['id']}.{i}",
                    "filename": documents[key]["filename"],
                    "extension": "pdf",
                    "text": texts[key],
                    "zip_name": "",  # not from a zip: native_path is relative to DATA_DIR
                    "native_path": f"{config.DEMO_CACHE_DIR.name}/{key}.pdf",
                })
            yield {
                "id": email["id"],
                "custodian": MAILBOX,
                "sender": sender,
                "recipients": _addresses(email["to"], names),
                "cc": _addresses(email.get("cc"), names),
                "subject": email["subject"],
                "body": email["body"].strip(),
                "date": _normalize_date(email["date"]),
                "folder": f"{MAILBOX}\\{'Sent Items' if BROKER_DOMAIN in sender.lower() else 'Inbox'}",
                "attachments": attachments,
            }


def read_native(native_path: str) -> bytes:
    return (config.DATA_DIR / native_path).read_bytes()


def _address_book(contacts: dict) -> dict[str, str]:
    """email address -> display name, for everyone in contacts.yaml."""
    names = {}
    entries = list(contacts["broker"]) + [c for client in contacts["clients"] for c in client["contacts"]]
    for entry in entries:
        m = ADDRESS_RE.match(entry)
        names[m["email"].lower()] = m["name"]
    return names


def _address(value: str, names: dict[str, str]) -> str:
    """Emails in the YAML only give the address; add the display name like a mail client would."""
    if "<" in value:
        return value
    name = names.get(value.lower())
    return f"{name} <{value}>" if name else value


def _addresses(value: str | list[str] | None, names: dict[str, str]) -> str:
    if not value:
        return ""
    values = [value] if isinstance(value, str) else value
    return ", ".join(_address(v, names) for v in values)


def _normalize_date(value) -> str:
    """YAML dates are Brussels local time, e.g. 2026-07-08 08:47."""
    if not isinstance(value, datetime):
        value = datetime.fromisoformat(str(value))
    if value.tzinfo is None:
        value = value.replace(tzinfo=TZ)
    return value.isoformat()


def _clean(text: str) -> str:
    text = text.replace("\t", " ").replace(" ", " ")
    return re.sub(r"\n{3,}", "\n\n", text).strip()
