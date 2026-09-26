# Verzekeringen — Broker Document Assistant

## Problem

Belgian insurance brokers run their business on **Brio** (by Portima), the dominant broker management software in Belgium. Brio has an Open API, but:
- Portima charges a very high fee for API access
- Even with that access, pulling out client/document data for external use is impractical

So there is no affordable way to get structured access to a broker's client and policy data directly from Brio.

## Insight / Workaround

Brokers send every client-facing document (policy documents, offers, claims correspondence, etc.) **by email**. The broker's mailbox is therefore a de-facto archive of everything shared with every client — and it's something we *can* access (via the broker's own mail account), without needing Brio at all.

## Solution

1. **Ingest the broker's mailbox** (read-only) via Microsoft Graph API (brokers run Outlook/Microsoft 365).
2. **Reconstruct per-client document history**: the broker maintains a list of clients (name/id + email address). Match each email/attachment to a client by matching sender/recipient address against that list.
3. **Extract and chunk documents** from email bodies and attachments (PDF policy docs, offers, etc.).
4. **Embed and store** the chunks in a vector DB, tagged with client id/metadata.
5. **RAG chatbot**: the broker picks a client (filter), then asks natural-language questions about that client's file — the chatbot retrieves only that client's chunks and answers grounded in the actual documents sent to them.

## Current scope (pilot)

- **Single broker pilot.** Not building multi-tenant SaaS yet — one mailbox, one broker's client list. Keep code reasonably modular so multi-tenancy isn't painful later, but don't over-engineer for it now.
- No GDPR/data-residency constraints for this phase — everything can run locally / with a third-party LLM API key. Revisit if/when this moves toward multiple brokers or production use with real client data at scale.

## Tech stack

- **Backend**: Python, FastAPI
- **Frontend**: simple web frontend (framework TBD as the project develops — keep it lightweight)
- **Email ingestion**: Microsoft Graph API (OAuth2 against the broker's Microsoft 365 / Outlook account)
- **Vector DB**: open-source, self-hosted locally (e.g. Chroma or Qdrant — pick one when ingestion pipeline is built; no cloud vector DB)
- **Embeddings**: open-source, run locally (no cloud embedding API for now). Currently `intfloat/multilingual-e5-large` via fastembed, configurable with `EMBEDDING_MODEL`
- **LLM**: wrapped behind a provider-agnostic interface — see below. Default/current provider is Claude (Anthropic API), using a user-supplied API key.

### LLM wrapper

All LLM calls must go through a single abstraction layer (e.g. `llm_client.py` or similar), not direct SDK calls scattered through the codebase. Goal: swapping the underlying model/provider (Claude → something else) should mean changing one implementation, not hunting through the codebase. Concretely:
- One interface (e.g. `generate(messages, **kwargs)` / `embed(texts)`) that the rest of the app depends on
- Provider-specific code (Claude API, or a future provider) implements that interface
- Model/provider selection driven by config (env var / settings), not hardcoded

## Core data flow

```
Broker mailbox (Graph API)
   → fetch emails + attachments
   → match sender/recipient to client list (name/id ↔ email address)
   → extract documents (email body text, PDF/attachment text)
   → chunk + embed (local embedding model)
   → store in vector DB (chunk tagged with client_id + source metadata)

Chatbot flow:
   user selects client (filter by client_id)
   → user question
   → retrieve top-k chunks scoped to that client_id
   → LLM (via wrapper) answers grounded in retrieved chunks
```

## Key entities

- **Client**: id, name, one or more associated email addresses (the list the broker maintains)
- **Document/chunk**: source email id, attachment name (if any), extracted text chunk, client_id, date, embedding
- **Mailbox connection**: broker's Microsoft 365 account, connected via OAuth (Graph API)

## Open questions / decisions still to make

- Which vector DB specifically (Chroma vs Qdrant vs other) — decide when building the ingestion pipeline
- Which local embedding model to use (now e5-large, best in a small Dutch benchmark, but slow on CPU)
- How to handle emails/attachments that don't clearly match a single client (e.g. broker-internal mail, group mailings)
- Attachment parsing strategy for scanned/image-based PDFs (OCR needed?)
- How to handle re-ingestion / incremental sync (new emails arriving after initial ingest) vs. one-off historical import

## Status

Early prototype. Instead of a real broker mailbox (Graph API not built yet), data comes from a configurable slice of the EDRM Enron email dataset (`backend/enron_dataset.py`, `backend/ingest_enron.py`) → SQLite + Chroma (chunked email bodies and PDF attachments) → FastAPI search endpoint + simple web UI. For broker demos there is also a synthetic Dutch mailbox of a fictional Flemish broker (`demo/`, `backend/demo_dataset.py`, `backend/ingest_demo.py`): hand-written emails with real AXA/KBC general conditions as PDF attachments. A local MCP server (`backend/mcp_server.py`) exposes the same retrieval as tools to Claude Desktop / Claude Code. No client matching, LLM wrapper or chatbot yet. This file documents intent/architecture so implementation stays aligned with the plan above.
