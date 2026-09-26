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

## Demo mailbox: Belgian broker

For demos to brokers there is also a synthetic mailbox of a fictional Flemish brokerage ("Verzekeringskantoor Hoflandt"): 99 Dutch emails between the broker and ~29 clients (claims, coverage questions, quotes, a newsletter, internal mail), from Dec 2025 to Sep 2026. 37 of them carry real, public general conditions from AXA Belgium and KBC as PDF attachments, and the emails reference those documents (e.g. "glasbreuk is gedekt volgens artikel 1.4.2").

```
python backend/ingest_demo.py            # add the demo mailbox next to what's loaded
python backend/ingest_demo.py --reset    # demo mailbox only (wipes the Enron data)
```

- `demo/contacts.yaml`: broker staff and the client list (id, name, email addresses, policies), usable later for client matching
- `demo/documents.yaml`: the 14 AXA/KBC PDFs and their source URLs. They're downloaded into `data/demo/` on first run (not committed). If a URL stops working, save the PDF there by hand as `<key>.pdf`.
- `demo/mailbox/*.yaml`: the emails, one thread after another. Edit or add emails there and re-run the ingest (idempotent).

All people, addresses and policy numbers are made up. Edge cases for later client matching: one household with two addresses (K-1013), a newsletter sent to 14 clients, and internal mail between broker staff.

Demo prompts (Claude via MCP):

- "Jan Peeters heeft een barst in zijn voorruit. Is dat gedekt en krijgt hij een vervangwagen? Geef het artikel uit de voorwaarden."
- "Welke klanten hadden het voorbije jaar schade aan hun woning, en wat werd er uitbetaald?"
- "Waarom is de kapotte turbo van Tom Willems niet gedekt?"
- "Wat is het verschil tussen de familiale van KBC en AXA voor geleende spullen?"
- "Hoeveel mag KBC terugvorderen van de zoon van Patrick Martens, en op basis van welk artikel?"

## Run

```
uvicorn main:app --reload --app-dir backend
```

Open **http://127.0.0.1:8000** in your browser.

- The page lists the emails from the SQLite DB (paged), with their PDF attachments.
- The search box does a semantic search against the Chroma vector DB, over email bodies, PDFs, or both (e.g. try "western electricity price cap").

## Use it from Claude (MCP)

`backend/mcp_server.py` is an MCP server that gives Claude read access to the archive, so you can ask questions about it straight from Claude Desktop or Claude Code. Claude does the chatting; the server only searches and fetches documents. It runs locally: Claude starts it in the background when it opens. You never start it yourself.

Tools Claude gets:

| Tool | What it does |
|---|---|
| `get_dataset_overview` | number of emails/PDFs, mailboxes, date range, top senders |
| `search_documents` | semantic search over email bodies and/or PDF text |
| `list_emails` | filter by sender, recipient, subject, date range, has attachment |
| `get_email` | full email incl. body and attachment list |
| `get_pdf_text` | full text of a PDF + link to open the original |

### Prerequisites

1. Dependencies installed in `.venv` (`pip install -r requirements.txt`, includes `mcp`).
2. Data loaded: `python backend/ingest_enron.py --reset`.
3. Optional but nice for the demo: run the web app (`uvicorn main:app --app-dir backend`) so the PDF links Claude gives (`http://127.0.0.1:8000/api/attachments/...`) open the original PDF.

### Claude Desktop

1. Open the config file. Easiest: Claude Desktop → **Settings → Developer → Edit Config**. It lives at
   - Microsoft Store install: `%LOCALAPPDATA%\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude_desktop_config.json`
   - regular installer: `%APPDATA%\Claude\claude_desktop_config.json`
2. Add an `mcpServers` block at the top level, next to what's already there (keep the existing `preferences` etc.). Use **absolute paths**, with forward slashes (a single `\` is invalid JSON):

   ```json
   {
     "mcpServers": {
       "broker-mailbox": {
         "command": "C:/Users/verme/poc-data-extraction/.venv/Scripts/python.exe",
         "args": ["C:/Users/verme/poc-data-extraction/backend/mcp_server.py"]
       }
     },
     "preferences": { "...": "existing content stays as is" }
   }
   ```
3. **Fully quit** Claude Desktop (system tray icon → Quit, closing the window is not enough) and start it again.
4. Check: in a new chat, open the tools/connectors menu (the sliders or "+" icon in the message box). `broker-mailbox` should be listed with its 5 tools. **Settings → Developer** also shows the server status.
5. Ask a question, e.g. the demo prompts below. Claude asks permission the first time it uses a tool; choose "Always allow" to keep the demo smooth.

### Claude Code

The repo contains `.mcp.json`, so Claude Code picks the server up automatically when opened in this folder (it asks once to approve it). Check with `/mcp`. Outside this folder: `claude mcp add broker-mailbox -- C:\path\to\.venv\Scripts\python.exe C:\path\to\backend\mcp_server.py`.

### Demo prompts

- "What's in the mailbox archive?"
- "Find the PDF newsletters about the Western power price cap. What did FERC staff conclude? Give me the link to the PDF."
- "Which emails with attachments were sent in January 2002? Summarise each in one line."
- "What changed in the real-time trading schedule for February, and who sent it?"
- "Show me the W-4 form that was sent around. What is it for?"

### Troubleshooting

- **Server doesn't show up / "failed"**: check the log `mcp-server-broker-mailbox.log` in the `logs` folder next to `claude_desktop_config.json`. Usual causes: a wrong path, or invalid JSON (missing comma).
- **Test the server without Claude**: `.venv\Scripts\python backend\mcp_server.py` should start and then wait silently (it's waiting for Claude on stdin). Ctrl+C to stop. An import error here means a dependency is missing.
- **No results**: data not loaded yet, run the ingest step.
- **Re-ingested data**: restart Claude Desktop so the server reopens the databases.
- **PDF links don't open**: the web app (uvicorn) isn't running.
