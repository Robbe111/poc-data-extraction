"""Locate a verbatim quote inside an email body or PDF, and build a link that opens the
source with that passage highlighted (frontend/viewer.html).

Matching ignores case, whitespace, punctuation and line-break hyphenation: PDF text
extraction mangles all of those, and pypdf (here) and PDF.js (in the viewer) mangle them
differently. viewer.html uses the same normalisation, so a quote that is found here is
normally found there too.
"""
import io
import unicodedata
from urllib.parse import urlencode

from pypdf import PdfReader

from config import APP_BASE_URL

MIN_QUOTE_CHARS = 8  # normalised; shorter quotes match too much to be meaningful


def normalize(text: str) -> str:
    # NFKD splits ligatures (ﬁ -> fi) and accents off their letters; the accents are then dropped.
    return "".join(c for c in unicodedata.normalize("NFKD", text).lower() if c.isalnum())


def find(quote: str, text: str) -> bool:
    needle = normalize(quote)
    return len(needle) >= MIN_QUOTE_CHARS and needle in normalize(text)


def pdf_page_of(quote: str, pdf_bytes: bytes) -> int | None:
    """1-based page on which the quote starts, or None if it can't be placed."""
    needle = normalize(quote)
    try:
        pages = [normalize(p.extract_text() or "") for p in PdfReader(io.BytesIO(pdf_bytes)).pages]
    except Exception:
        return None
    position = normalize("".join(pages)).find(needle)  # quotes may run across a page break
    if position == -1:
        return None
    for number, page in enumerate(pages, start=1):
        if position < len(page):
            return number
        position -= len(page)
    return None


def viewer_url(quotes: list[str], attachment_id: str | None = None, email_id: str | None = None) -> str:
    params = [("attachment", attachment_id)] if attachment_id else [("email", email_id)]
    params += [("q", q) for q in quotes]
    return f"{APP_BASE_URL}/viewer.html?{urlencode(params)}"
