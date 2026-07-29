# AIVOA — AI-Powered Customer Complaint Management System

A pharmaceutical **QMS Customer Complaint** intake module for API and finished dose
form (FDF) manufacturing. The QA officer never types into the form — a LangGraph
agent reads a pasted complaint, an email, or a PDF report, fills the record, and
reasons about the risk.

Built for the **AIVOA Round 1 Full Stack Developer Assessment**.

```
┌──────────────────────────────────────┬──────────────────────────────┐
│  Log Customer Complaint              │  ⚗ AIVOA Copilot         ●   │
│  API & FDF Quality Assurance Module  │  Drop complaint files or     │
│                     [Ready to Commit]│  paste text below.           │
│  1. ORIGIN & CUSTOMER DETAILS        │  ┌────────────────────────┐  │
│  2. PRODUCT & BATCH IDENTIFICATION   │  │  transcript            │  │
│  3. FACILITY & MATERIAL IMPACT       │  │  • log_complaint       │  │
│  4. DEFECT ANALYSIS                  │  │  • edit_complaint      │  │
│  ┌────────────────────────────────┐  │  │  • extract_document    │  │
│  │ 🛡 AI copilot risk assessment  │  │  └────────────────────────┘  │
│  └────────────────────────────────┘  │  [📎 Type a message…    ✓]   │
│  [    Commit to QMS Ledger      ]    │     POWERED BY LANGGRAPH     │
└──────────────────────────────────────┴──────────────────────────────┘
```

---

## 1. Technology stack

Every item below is the one mandated by the assignment.

| Layer | Choice |
|-------|--------|
| Frontend | **React 18** + **Redux Toolkit** (Vite) |
| Backend | **Python** + **FastAPI** |
| AI agent framework | **LangGraph** |
| LLM | **Groq** — `gemma2-9b-it` (primary) · `llama-3.3-70b-versatile` (router) |
| Database | **PostgreSQL / MySQL** via SQLAlchemy (SQLite fallback for local dev) |
| Font | **Google Inter** |

**Why two models.** `gemma2-9b-it` is the mandated model and does all extraction and
reasoning, through strict JSON prompting. It has **no native tool-calling support on
Groq**, so the LangGraph *router* node — the node that decides which of the three
tools a message belongs to — runs on `llama-3.3-70b-versatile`, which does. The
assignment explicitly allows that model "for context". Both are configurable in
`.env`, and the router degrades to a deterministic heuristic if tool calling is
unavailable. Full reasoning in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## 2. The three mandatory AI tools

| Tool | Trigger | Behaviour |
|------|---------|-----------|
| **`log_complaint`** | A new complaint pasted into the chat | Extracts every field, builds the form schema, and reasons out the AI risk assessment (severity · suggested next action · initial risk assessment). |
| **`edit_complaint`** | A natural-language correction | Returns a **sparse patch** — only the fields named — merges it over the record, then re-evaluates the risk. Everything the officer did not mention is preserved. |
| **`extract_document`** | A PDF / email / text upload | Parses the document (prose **and** tables), works out which party is the complainant vs. the manufacturer, populates the form and risk assessment, and quotes the source complaint reference. |

### Bonus AI features (optional in the brief, all implemented)

`Completeness Checker` · `Root Cause Recommendation` · `CAPA Recommendation` ·
`Duplicate Complaint Detection` · `Complaint Summary` · AI Risk Classification
(built into the three core tools).

Duplicate detection is a real database query against committed complaints; the rest
are LLM reasoning over the current record.

---

## 3. Quick start

### Prerequisites
- Python 3.11+
- Node 18+
- A Groq API key — <https://console.groq.com/keys>
- *(optional)* PostgreSQL or MySQL. Without one, SQLite is used automatically.

### Backend

```bash
cd backend
python -m venv .venv
```

```bash
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
```

```bash
pip install -r requirements.txt
cp .env.example .env      # then add your GROQ_API_KEY
uvicorn app.main:app --reload --port 8000
```

API docs at <http://127.0.0.1:8000/docs>.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. Vite proxies `/api` to port 8000.

### Database

Set one line in `backend/.env`:

```bash
DATABASE_URL=postgresql+psycopg://aivoa:aivoa@localhost:5432/aivoa
```

```bash
DATABASE_URL=mysql+pymysql://aivoa:aivoa@localhost:3306/aivoa
```

Tables are created on startup — no migration step needed.

> **Running without a Groq key.** The app still works: it falls back to a
> deterministic regex extractor so the UI, streaming, database and tests are all
> exercisable offline, and the copilot header says so. It is a development
> convenience, not the real implementation — set a key to run the actual agent.

---

## 4. Try it

Paste this into the copilot:

```
Apollo Pharmacy reported discolored capsules in Amoxicillin Capsules 500 mg. Batch number AMX240602. Manufacturing date March 2026. Expiry date February 2028. Please log this complaint
```

Then correct it in plain English — typos and all:

```
ah sorry the batch number is BMX240602 and affected quantity is 48 capcules
```

Then upload `samples/Fictional_Pharma_Customer_Complaint_API.pdf` and correct that too:

```
ah sorry the batch number is CHG 260712A and affected quantity is 50 kg (2 HDPE Drum)
```

### Sample documents

`samples/` ships three fictional pharmaceutical complaints and the script that
builds them:

| File | Case |
|------|------|
| `Fictional_Pharma_Customer_Complaint_API.pdf` | Foreign matter in a Metformin HCl API drum (`CC-2026-00154`) — **Critical** |
| `Fictional_Pharma_Customer_Complaint_FDF.pdf` | Mottling + foil delamination, Cefixime tablets — **Major** |
| `Fictional_Pharma_Customer_Complaint_Email.txt` | Raw email complaint, Ibuprofen BP API |

```bash
pip install reportlab && python samples/generate_samples.py
```

All companies, batches and people are invented.

---

## 5. Tests

```bash
cd backend && python -m pytest tests -q
```

31 tests, no network and no secrets required — they run the deterministic path
against a throwaway SQLite database.

- `test_agent_flow.py` — the LangGraph graph driven with the **exact prompts from
  the demo video**, including both typos (`48 capcules`, `CHG 260712Aand`). Asserts
  that an edit patches only the named fields and clobbers nothing else.
- `test_api.py` — session lifecycle, SSE framing, attachment messages, commit
  guards, ledger, bonus features, and the unreadable-PDF path.

---

## 6. Project structure

```
Project AIVOA/
├── backend/
│   ├── app/
│   │   ├── main.py                    FastAPI app, CORS, lifespan
│   │   ├── config.py                  pydantic-settings
│   │   ├── agent/                     ── the LangGraph layer ──
│   │   │   ├── graph.py               router → tool → finalize state machine
│   │   │   ├── state.py               AgentState TypedDict
│   │   │   ├── tools.py               the 3 mandatory tools + bonus tools
│   │   │   ├── prompts.py             all system prompts + the field contract
│   │   │   └── llm.py                 Groq clients, JSON-mode helper
│   │   ├── api/
│   │   │   ├── chat.py                POST /api/chat/stream        (SSE)
│   │   │   ├── documents.py           POST /api/documents/stream   (SSE)
│   │   │   ├── complaints.py          session, commit, ledger, /ai/*
│   │   │   └── sse.py                 event framing helpers
│   │   ├── db/
│   │   │   ├── models.py              Session · ChatMessage · Complaint
│   │   │   └── session.py             engine / session factory
│   │   └── services/
│   │       ├── form_schema.py         the agent-returned form schema + patching
│   │       ├── document_parser.py     pdfplumber prose + table extraction
│   │       ├── session_service.py     persistence + graph invocation
│   │       └── fallback_extractor.py  deterministic no-key path
│   └── tests/
├── frontend/
│   └── src/
│       ├── store/                     Redux Toolkit slices + thunks
│       ├── api/client.js              fetch + ReadableStream SSE reader
│       └── components/                form, risk panel, copilot, composer
├── samples/                           fictional complaint PDFs + generator
└── docs/
    ├── ARCHITECTURE.md                design decisions and data flow
    └── REFERENCE-SPEC.md              everything extracted from the demo video
```

---

## 7. API

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/health` | Status, configured models, database driver |
| `POST` | `/api/session` | Create or resume a session; returns form + transcript |
| `POST` | `/api/session/reset` | Clear the form and transcript |
| `POST` | `/api/chat/stream` | **SSE** — runs `log_complaint` / `edit_complaint` |
| `POST` | `/api/documents/stream` | **SSE** — runs `extract_document` |
| `POST` | `/api/complaints/commit` | Write to the ledger, assign `CC-YYYY-NNNNN` |
| `GET` | `/api/complaints` | List committed complaints |
| `POST` | `/api/ai/{feature}` | `completeness` · `root-cause` · `capa` · `duplicates` · `summary` |

Both streaming endpoints are POSTs, so the frontend reads them with `fetch` and a
`ReadableStream` rather than `EventSource` (which is GET-only). Event frames:

```
{"type":"user_message", "message":{…}}
{"type":"status", "label":"Extracting tabular data via OCR...", "progress":0.45}
{"type":"result", "message":{…}, "formSections":[…], "risk":{…}, "status":"…", "patch":{…}}
{"type":"done"}
```

---

## 8. Design decisions

**The agent returns the form schema, not just values.** In the demo the form's
*sections and labels* change once a complaint is parsed — three "Awaiting AI
extraction" sections become four, and `Product Strength` becomes `Product
Strength/Grade` for an API. So `formSections` is agent output and React renders
whatever arrives. No field list is hardcoded in the frontend.

**Edits are sparse patches.** `edit_complaint` returns only the fields the officer
named. `apply_patch` merges them over the existing schema, which is what makes
"preserving all other complaint information" a structural guarantee rather than a
prompt instruction the model might forget. A test asserts it.

**Inferred values are marked.** The reference demo silently invents plausible QMS
detail — "12 capsules" and "Primary Packaging (Bottle)" appear in the form though
neither is in the input text. That is genuinely useful, but unmarked invention in a
regulated record is a liability. The tools return an `inferred_fields` list and the
UI tags those fields **AI INFERRED** with a tooltip. Same speed, auditable.

**The form is read-only by default.** The brief says the officer must not fill it
manually, so inputs are `readonly` and driven by Redux. A visible, off-by-default
"Allow manual edits" checkbox is the escape hatch a real QA officer would need.

**Progress is real.** The demo shows a fixed ~10s bar with one label. Here the
stages stream as the work actually happens: reading the document → extracting
tabular data → identifying the complainant → generating the risk assessment.

**Long values are readable.** The demo clips `Suggested Next Action` and `Initial
Risk Assessment` inside single-line inputs. Those are textareas here.

**Commit is specified.** The demo never clicks *Commit to QMS Ledger*, so the
behaviour is defined here: validate the blocking fields, write the complaint with a
`CC-YYYY-NNNNN` number in the style of the demo PDF, snapshot the full schema, show
the assigned number, and reset the session for the next complaint.

---

## 9. Known limitations

- **No authentication.** A real QMS needs named, audited users; the brief scopes a
  single-screen intake module.
- **No production OCR.** Explicitly out of scope in the brief. Text-based PDFs are
  parsed with `pdfplumber` including tables; an image-only scan is detected and
  reported honestly instead of silently returning nothing.
- **`gemma2-9b-it` has a small context window.** Very long documents are passed
  whole rather than chunked; a production build would chunk and map-reduce.
- **Sessions are keyed by `localStorage`,** not by a user account.
- **No ledger browse UI.** `GET /api/complaints` is implemented and used by
  duplicate detection, but there is no list screen — the demo has none.

---

## 10. AI usage disclosure

This project was built with AI assistance (Claude), as the assignment encourages.
The demo video was transcribed and analysed frame by frame to recover the exact
field names, copy, prompts, and state transitions before any code was written —
that reference specification is in
[docs/REFERENCE-SPEC.md](docs/REFERENCE-SPEC.md).

Work that was mine to direct and correct rather than accept: choosing the
agent-returns-schema architecture over a hardcoded form; making `edit_complaint` a
sparse patch so field preservation is structural; the two-model split once
`gemma2-9b-it` turned out to lack Groq tool calling; marking inferred values instead
of copying the reference's silent invention; and fixing the document extractor after
testing against real generated PDFs revealed that table rows put the second
key/value pair mid-row.
