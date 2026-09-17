"""Source adapter for the EDRM Enron Email Data Set v2 (XML version).

The dataset is split per custodian (= one person's mailbox) into zip files. Each zip holds
an XML load file with the email metadata and attachment relationships, a native_xxx/
folder with the original .eml files and attachments, and a text_xxx/ folder with
pre-extracted text for every item.

This module only downloads and parses; it yields plain dicts so the rest of the pipeline
doesn't care whether emails come from Enron or (later) Microsoft Graph.
"""
import io
import logging
import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Iterator

import requests
from pypdf import PdfReader

import config

# pypdf logs a warning per odd font in these old PDFs; text still extracts fine.
logging.getLogger("pypdf").setLevel(logging.ERROR)

ARCHIVE_ITEM = "edrm.enron.email.data.set.v2.xml"
METADATA_URL = f"https://archive.org/metadata/{ARCHIVE_ITEM}"
ZIP_NAME_RE = re.compile(r"^edrm-enron-v2_(?P<custodian>.+?)_xml(?:_\d+of\d+)?\.zip$")

# Every text file ends with this licence notice; strip it so it doesn't pollute search.
EDRM_FOOTER_RE = re.compile(r"\*{5,}\s*EDRM Enron Email Data Set has been produced.*?\*{5,}", re.S)


def list_custodians() -> dict[str, dict]:
    """custodian -> {"files": [zip names], "size": total bytes}"""
    files = requests.get(METADATA_URL, timeout=60).json()["files"]
    custodians: dict[str, dict] = {}
    for f in files:
        m = ZIP_NAME_RE.match(f["name"])
        if not m:
            continue
        entry = custodians.setdefault(m["custodian"], {"files": [], "size": 0})
        entry["files"].append(f["name"])
        entry["size"] += int(f.get("size") or 0)
    for entry in custodians.values():
        entry["files"].sort()
    return custodians


def download(zip_name: str) -> Path:
    config.ENRON_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    target = config.ENRON_CACHE_DIR / zip_name
    if target.exists():
        return target
    partial = target.with_suffix(".part")
    with requests.get(f"{config.ENRON_BASE_URL}/{zip_name}", stream=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        done = 0
        with open(partial, "wb") as out:
            for block in r.iter_content(1 << 20):
                out.write(block)
                done += len(block)
                if total:
                    print(f"\r  downloading {zip_name}: {done / total:.0%}", end="", flush=True)
    print()
    partial.rename(target)
    return target


def iter_emails(custodian: str, zip_names: list[str], max_emails: int = 0) -> Iterator[dict]:
    """Yield emails (with their attachments) for one custodian."""
    count = 0
    for zip_name in zip_names:
        with zipfile.ZipFile(download(zip_name)) as zf:
            for xml_name in sorted(n for n in zf.namelist() if n.endswith(".xml") and "/" not in n):
                for email in _parse_load_file(zf, xml_name, custodian):
                    yield email
                    count += 1
                    if max_emails and count >= max_emails:
                        return


def _parse_load_file(zf: zipfile.ZipFile, xml_name: str, custodian: str) -> Iterator[dict]:
    root = ET.parse(zf.open(xml_name)).getroot()
    docs = {d.get("DocID"): d for d in root.iter("Document")}

    children: dict[str, list[str]] = {}
    for rel in root.iter("Relationship"):
        if rel.get("Type") == "Attachment":
            children.setdefault(rel.get("ParentDocId"), []).append(rel.get("ChildDocId"))

    for doc_id, doc in docs.items():
        if doc.get("DocType") != "Message":
            continue
        tags = _tags(doc)
        attachments = []
        for child_id in children.get(doc_id, []):
            child = docs.get(child_id)
            if child is None:
                continue
            attachment = _parse_attachment(zf, child)
            if attachment:
                attachments.append(attachment)

        yield {
            "id": doc_id,
            "custodian": custodian,
            "sender": tags.get("#From", ""),
            "recipients": tags.get("#To", ""),
            "cc": tags.get("#CC", ""),
            "subject": tags.get("#Subject", "") or "(no subject)",
            "body": _strip_headers(_read_text(zf, doc)),
            "date": _normalize_date(tags.get("#DateSent", "")),
            "folder": doc.findtext("Locations/Location/LocationURI", default=""),
            "attachments": attachments,
        }


def _parse_attachment(zf: zipfile.ZipFile, doc: ET.Element) -> dict | None:
    tags = _tags(doc)
    extension = tags.get("#FileExtension", "").lower()
    if extension not in config.ENRON_ATTACHMENT_EXTENSIONS:
        return None

    native_ref = doc.find("Files/File[@FileType='Native']/ExternalFile")
    text = ""
    if extension == "pdf":
        # Parse the PDF ourselves, like we'll have to for real mailbox attachments.
        # Fall back to EDRM's pre-extracted text if that yields nothing.
        native = _read_file(zf, doc, "Native")
        if native:
            text = extract_pdf_text(native)
    if not text.strip():
        text = _read_text(zf, doc)
    text = _clean(text)
    if not text:
        return None

    return {
        "id": doc.get("DocID"),
        "filename": tags.get("#FileName", doc.get("DocID")),
        "extension": extension,
        "text": text,
        # Where the original file sits, so the UI can open it later.
        "zip_name": Path(zf.filename).name,
        "native_path": f"{native_ref.get('FilePath')}/{native_ref.get('FileName')}" if native_ref is not None else "",
    }


def read_native(zip_name: str, native_path: str) -> bytes:
    with zipfile.ZipFile(config.ENRON_CACHE_DIR / zip_name) as zf:
        return zf.read(native_path)


def extract_pdf_text(data: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(data))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:  # malformed / encrypted PDFs are common in old mail
        print(f"  could not parse PDF: {exc}")
        return ""


def _tags(doc: ET.Element) -> dict[str, str]:
    return {t.get("TagName"): t.get("TagValue", "") for t in doc.iter("Tag")}


def _read_file(zf: zipfile.ZipFile, doc: ET.Element, file_type: str) -> bytes | None:
    ext = doc.find(f"Files/File[@FileType='{file_type}']/ExternalFile")
    if ext is None:
        return None
    try:
        return zf.read(f"{ext.get('FilePath')}/{ext.get('FileName')}")
    except KeyError:
        return None


def _read_text(zf: zipfile.ZipFile, doc: ET.Element) -> str:
    raw = _read_file(zf, doc, "Text")
    if raw is None:
        return ""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")
    return _clean(text)


def _clean(text: str) -> str:
    text = EDRM_FOOTER_RE.sub("", text)
    return re.sub(r"\n{3,}", "\n\n", text.replace("\r\n", "\n")).strip()


def _strip_headers(text: str) -> str:
    """Email text files start with a Date/To/From/X-... header block; drop it."""
    head, sep, body = text.partition("\n\n")
    if sep and re.match(r"^(Date|From|To|Subject):", head):
        return body.strip()
    return text


def _normalize_date(value: str) -> str:
    try:
        return datetime.fromisoformat(value).isoformat()
    except ValueError:
        return value
