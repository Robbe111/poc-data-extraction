"""Renders the fictional special conditions (bijzondere voorwaarden) of the demo mailbox as PDFs.

General conditions are public and downloaded from the insurers (demo_dataset/documents.yaml), but the
special conditions carry personal data, so no real ones exist to use. These are made up and
described in demo_dataset/policies.yaml: policyholder, insured vehicle or home, guarantees and premiums,
clauses. This module turns one entry into a PDF that looks roughly like what an insurer sends.

Every page says in its footer that the document is fictional.
"""
from datetime import date

from fpdf import FPDF

INSURERS = {
    "axa": {
        "name": "AXA Belgium",
        "legal": "AXA Belgium nv - Troonplein 1, 1000 Brussel - verzekeringsonderneming toegelaten onder code 0039",
        "city": "Brussel",
    },
    "ag": {
        "name": "AG Insurance",
        "legal": "AG Insurance nv - E. Jacqmainlaan 53, 1000 Brussel - verzekeringsonderneming toegelaten onder code 0079",
        "city": "Brussel",
    },
    "pv": {
        "name": "P&V Verzekeringen",
        "legal": "P&V Verzekeringen cv - Koningsstraat 151, 1210 Brussel - verzekeringsonderneming toegelaten onder code 0058",
        "city": "Brussel",
    },
}

BROKER = [
    "Verzekeringskantoor Hoflandt bv",
    "Mechelsesteenweg 118, 2500 Lier",
    "FSMA 0766.412.305 - tel. 03 480 12 12",
    "info@hoflandt.be",
]

# Taxes and contributions on top of the net premium, per kind of guarantee. Premiums in
# policies.yaml include them (that is what the broker quotes to clients); the PDF shows the split.
TAX_RATES = {
    "ba_auto": 0.371,  # 27.1% tax + contributions (RIZIV, Waarborgfonds)
    "standard": 0.0925,
    "woning": 0.1025,  # 9.25% + contribution to the fire brigade fund
}

FOOTER = "Fictief demodocument - alle personen, adressen, voertuigen en polisnummers zijn verzonnen."

# Built-in PDF fonts only cover Latin-1.
_REPLACE = str.maketrans({"€": "EUR", "Š": "S", "š": "s", "’": "'", "‘": "'", "“": '"', "”": '"',
                          "–": "-", "—": "-", "…": "...", "≤": "<=", "≥": ">="})


def _t(value) -> str:
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    return str(value).translate(_REPLACE).encode("latin-1", "replace").decode("latin-1")


def _eur(amount: float) -> str:
    whole, cents = f"{amount:,.2f}".split(".")
    return f"{whole.replace(',', '.')},{cents} EUR"


class _Pdf(FPDF):
    def __init__(self, insurer: dict, doc: dict):
        super().__init__(format="A4")
        self.insurer = insurer
        self.doc = doc
        self.set_margins(18, 16, 18)
        self.set_auto_page_break(True, margin=22)

    def header(self):
        self.set_font("Helvetica", "B", 15)
        self.cell(90, 8, _t(self.insurer["name"]))
        self.set_font("Helvetica", "B", 11)
        self.cell(0, 8, _t(self.doc["doc"]), align="R", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 9)
        self.cell(90, 5, _t(self.doc["product"]))
        self.cell(0, 5, _t(f"Polisnummer {self.doc['policy']}"), align="R", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(0, 0, 120)
        self.set_line_width(0.6)
        self.line(18, self.get_y() + 2, 192, self.get_y() + 2)
        self.ln(6)

    def footer(self):
        self.set_y(-18)
        self.set_font("Helvetica", "", 7)
        self.set_text_color(90)
        self.cell(0, 4, _t(self.insurer["legal"]), align="C", new_x="LMARGIN", new_y="NEXT")
        self.cell(0, 4, _t(f"{FOOTER}   Pagina {self.page_no()}/{{nb}}"), align="C")
        self.set_text_color(0)


def render(doc: dict) -> bytes:
    """One entry of demo_dataset/policies.yaml -> PDF bytes."""
    insurer = INSURERS[doc["insurer"]]
    pdf = _Pdf(insurer, doc)
    pdf.add_page()

    _key_values(pdf, {
        "Datum van uitgifte": doc["issued"],
        "Reden van uitgifte": doc.get("reason", ""),
        "Ingangsdatum van dit document": doc.get("effective", ""),
    })
    pdf.ln(2)
    _parties(pdf, doc["holder"])

    for title, rows in (doc.get("sections") or {}).items():
        _heading(pdf, title)
        _key_values(pdf, rows)

    if doc.get("guarantees"):
        _heading(pdf, "Waarborgen en premie")
        _guarantees(pdf, doc["guarantees"], doc.get("payment"))

    if doc.get("clauses"):
        _heading(pdf, "Bijzondere bepalingen")
        for i, clause in enumerate(doc["clauses"], start=1):
            _paragraph(pdf, f"{i}. {clause}")

    if doc.get("text"):
        _paragraph(pdf, doc["text"])

    if doc.get("conditions"):
        _heading(pdf, "Toepasselijke algemene voorwaarden")
        _paragraph(pdf, "Dit contract bestaat uit deze bijzondere voorwaarden en de volgende algemene voorwaarden. "
                        "Bij tegenstrijdigheid hebben de bijzondere voorwaarden voorrang.")
        for name in _flatten(doc["conditions"]):
            _paragraph(pdf, f"- {name}")

    pdf.ln(4)
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(0, 5, _t(f"Opgemaakt te {insurer['city']} op {_t(doc['issued'])}, voor {insurer['name']}. "
                            "De verzekeringnemer verklaart een exemplaar van de algemene voorwaarden en van het "
                            "informatiedocument (IPID) ontvangen te hebben."))
    return bytes(pdf.output())


def doc_policy(pdf: "_Pdf") -> str:
    return f"policy {pdf.doc['policy']}"


def _flatten(items: list) -> list[str]:
    """YAML aliases put shared lists inside lists: [[a, b], c] -> [a, b, c]."""
    flat = []
    for item in items:
        flat.extend(_flatten(item) if isinstance(item, list) else [item])
    return flat


def _heading(pdf: FPDF, title: str):
    if pdf.get_y() > 250:
        pdf.add_page()
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(230, 233, 245)
    pdf.cell(0, 6, _t(title), fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)


def _key_values(pdf: FPDF, rows: dict):
    for label, value in rows.items():
        if value in ("", None):
            continue
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(58, 5, _t(label))
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(0, 5, _t(value), align="L", new_x="LMARGIN", new_y="NEXT")


def _paragraph(pdf: FPDF, text: str):
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(0, 4.6, _t(text.strip()), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)


def _parties(pdf: FPDF, holder: dict):
    top = pdf.get_y()
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(87, 5, "Verzekeringnemer", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    for label, value in holder.items():
        pdf.cell(87, 4.6, _t(value if label in ("Naam", "Adres") else f"{label}: {_t(value)}"),
                 new_x="LMARGIN", new_y="NEXT")
    bottom = pdf.get_y()

    pdf.set_xy(108, top)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 5, "Uw verzekeringsmakelaar", new_x="LEFT", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    for line in BROKER:
        pdf.cell(0, 4.6, _t(line), new_x="LEFT", new_y="NEXT")
    pdf.set_xy(18, max(bottom, pdf.get_y()))


def _guarantees(pdf: FPDF, rows: list, payment: str | None):
    widths = (64, 50, 30, 30)
    pdf.set_font("Helvetica", "B", 8.5)
    for width, title in zip(widths, ("Waarborg", "Verzekerd bedrag / grens", "Vrijstelling", "Jaarpremie*")):
        pdf.cell(width, 6, title, border="B")
    pdf.ln()

    net = total = 0.0
    pdf.set_font("Helvetica", "", 8.5)
    for row in rows:
        if len(row) not in (4, 5):
            raise ValueError(f"{doc_policy(pdf)}: guarantee row needs 4 or 5 fields, got {row}")
        name, limit, deductible, premium = row[:4]
        rate = TAX_RATES[row[4] if len(row) > 4 else "standard"]
        if isinstance(premium, (int, float)):
            total += premium
            net += premium / (1 + rate)
            premium = _eur(premium)
        # Rows can wrap: draw each cell as a multi_cell and continue from the tallest one.
        top, height = pdf.get_y(), 0.0
        x = pdf.l_margin
        for width, text in zip(widths, (name, limit, deductible, premium)):
            pdf.set_xy(x, top)
            pdf.multi_cell(width, 4.6, _t(text), align="L")
            height = max(height, pdf.get_y() - top)
            x += width
        pdf.set_xy(pdf.l_margin, top + height)
        pdf.set_draw_color(200)
        pdf.set_line_width(0.2)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + sum(widths), pdf.get_y())

    pdf.ln(2)
    _key_values(pdf, {
        "Nettopremie": _eur(net),
        "Taksen en bijdragen": _eur(total - net),
        "Totale jaarpremie": _eur(total),
        "Betaling": payment or "jaarlijks, via domiciliering",
    })
    pdf.set_font("Helvetica", "I", 7.5)
    pdf.cell(0, 4, "* jaarpremie inclusief taksen en bijdragen", new_x="LMARGIN", new_y="NEXT")
