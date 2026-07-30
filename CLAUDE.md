# AIVOA Complaints Module — working notes

Interview deliverable for the **AIVOA Round 1 Full Stack Developer Assessment**
(aivoa.ai). An AI-powered pharmaceutical QMS Customer Complaint intake module for
API and finished dose form (FDF) manufacturing.

Read [README.md](README.md) for setup and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
for design reasoning. [docs/REFERENCE-SPEC.md](docs/REFERENCE-SPEC.md) is a
frame-by-frame extraction of the assessment's demo video — the source of truth for
field names, labels, copy and state transitions.

## The stack is mandated — do not substitute

The brief requires these exactly. Swapping any of them fails the submission.

| Layer | Required |
|-------|----------|
| Frontend | React + **Redux** (Redux Toolkit) |
| Backend | Python + **FastAPI** |
| Agent framework | **LangGraph** |
| LLM | **Groq**, model `gemma2-9b-it` |
| Database | **MySQL or PostgreSQL** |
| Font | **Google Inter** |

`llama-3.3-70b-versatile` is also allowed and is used *only* for the router node,
because `gemma2-9b-it` has no native tool-calling support on Groq. Both are set in
`backend/.env`.

**Groq retired both.** `gemma2-9b-it` was decommissioned 2025-10-08;
`llama-3.3-70b-versatile` shuts down 2026-08-16. `PRIMARY_MODEL` / `ROUTER_MODEL`
still name the assignment's models and are still tried first — do not change them,
that is the point — and `*_MODEL_FALLBACKS` carries the live replacements. Only a
`model_decommissioned` / `model_not_found` error advances the chain. See
`docs/ARCHITECTURE.md` §2 and re-check
<https://console.groq.com/docs/deprecations> before recording the demo.

## Commands

```bash
cd backend && .venv\Scripts\activate && uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend && npm run dev
```

```bash
cd backend && python -m pytest tests -q
```

Tests need no network and no secrets — they run the deterministic path against a
throwaway SQLite DB (see `tests/conftest.py`).

```bash
cd backend && .venv\Scripts\python.exe scripts/verify_llm.py
```

First-contact test for every real-Groq path: probes both model chains, then
replays the demo script from `docs/REFERENCE-SPEC.md` §4 through the three tools
and the four LLM bonus features, diffing against the reference values. Needs
`GROQ_API_KEY`. `--probe` for models only, `--no-bonus` to skip the bonus calls.

```bash
cd backend && .venv\Scripts\python.exe scripts/verify_api.py --base http://127.0.0.1:8001
```

The same demo, driven over HTTP the way the browser drives it — SSE framing,
progress stages, attachment cards, ledger commit, duplicate detection, guard
rails. Needs a running server. It commits real complaints, so start that server
against a scratch `DATABASE_URL` unless you want them in the demo ledger.

```bash
python samples/generate_samples.py
```

Regenerates the three fictional complaint documents (needs `reportlab`).

## The three mandatory AI tools

In `backend/app/agent/tools.py`, dispatched by the graph in `agent/graph.py`:

- `log_complaint` — raw complaint text → full record + AI risk assessment
- `edit_complaint` — natural-language correction → **sparse patch** + refreshed risk
- `extract_document` — PDF/email upload → same shape as `log_complaint`

## Invariants — easy to break, please don't

1. **The agent returns the form *schema*, not just values.** The demo's form changes
   shape after parsing (3 sections → 4; `Product Strength` → `Product
   Strength/Grade` for an API). `formSections` is agent output; React renders
   whatever arrives. Never hardcode a field list in the frontend. Schema lives in
   `app/services/form_schema.py`.

2. **`edit_complaint` must return a sparse patch, never a full record.**
   `apply_patch()` can only touch keys present in the patch, which is what makes
   "preserve all other complaint information" structural rather than a prompt hope.
   Asserted by `test_patches_only_named_fields`.

3. **The left form is read-only.** The brief says the officer must not fill it
   manually. Inputs are `readonly`, driven by Redux. The off-by-default "Allow
   manual edits" checkbox is the deliberate escape hatch.

4. **Values the model infers rather than reads get tagged `AI INFERRED`.** Tools
   return `inferred_fields`; the UI badges them. Do not silently invent data into a
   regulated record.

5. **Both stream endpoints are POST + SSE**, so the client uses `fetch` +
   `ReadableStream`, not `EventSource` (GET-only). Frame parser splits on `\n\n` —
   don't refactor it to read line-by-line, JSON payloads span network chunks.

## Status

Implemented and passing: all three tools, all five bonus AI features, 45 offline
tests, frontend builds clean.

**The real Groq path is verified** as of 2026-07-30 — `scripts/verify_llm.py` runs
73 checks green (the one warning is gemma2-9b-it being decommissioned, expected).
Confirmed working against live Groq: the model chain, the router's native tool
calling, all three tools replaying the demo script, and all four LLM bonus features.
Primary role is served by `llama-3.1-8b-instant`, router by
`llama-3.3-70b-versatile`.

**Still to verify:**

1. **Only SQLite has connected.** Drivers for Postgres and MySQL are installed and
   the models use portable JSON columns, but a real server has not been tested. The
   brief mandates MySQL/Postgres — switch `DATABASE_URL` and confirm.
2. **The UI has never driven the LLM path.** Only the harness has. Run both servers
   and walk the four demo turns through the browser, watching the SSE stages and
   the `AI INFERRED` badges.

## First-contact bugs the LLM path exposed (all fixed)

The prompts were written against no model, so these only appeared on the first real
run. Worth knowing, because the same class will reappear if the prompts are edited:

1. **The model copied instruction text into `reply`.** The JSON shape blocks used
   instructions as placeholder values (`"reply": "Confirm the change, naming each
   field…"`), and an 8B model returns them verbatim. Placeholders must be *example
   values*, with the instruction in prose above the block.
2. **…then it copied the example values instead.** Replacing the instructions with
   realistic examples was worse: the model transcribed the example record and
   dropped `complaint_description` entirely. Examples must be **obviously unrelated
   dummy data** (Nordic Pharma / Ibuprofen / IBU250114) so leakage is visible, and
   `verify_llm.py` greps every field for those values.
3. **Severity would not escalate.** "Foreign matter in an API" buried in a prose
   definition got `Major` because no patient injury was reported. Fixed with an
   ordered stop-at-first-match rule plus "severity describes the hazard, not the
   outcome".
4. **The run-on batch number came back whole** (`CHG 260712Aand affected`) however
   firmly the prompt asked. Now enforced in code — `fb.clean_batch()` via
   `tools._sanitize()`, on the LLM and deterministic paths alike.
5. **The extraction reply double-narrated**, because the wrapper sentence was
   applied unconditionally over a reply that already quoted the reference.
6. **Enum placeholders came back as the option list** — `"category": "Man | Machine
   | Material | …"` in root-cause output. Same fix as (1): one concrete value.

Lesson that generalises: **never put an instruction, or an option list, where a
value belongs in a JSON example.** Small models fill the slot with whatever is
sitting in it.

**Still owed to AIVOA:** public GitHub repo, and a 10–15 minute demo video covering
all AI tools, the frontend workflow, code flow and architecture, the LangGraph
implementation, and key design decisions. `docs/ARCHITECTURE.md` is written to be
that walkthrough script.

## Gotchas already hit

- **pdfplumber flattens a 4-column table so the second key/value pair sits
  mid-row**: `Batch / Lot No. | MFH260712A | Quantity Affected | 25 kg (1 HDPE
  Drum)`. A label matcher anchored to line-start silently misses `Quantity
  Affected`. `_labelled()` in `fallback_extractor.py` allows a label to follow a
  pipe as well as start a line.
- **Sample PDF table cells must be reportlab `Paragraph`s, not bare strings** —
  plain strings overflow the column and get clipped in the PDF itself, which then
  truncates on extraction.
- **Demo prompts contain deliberate typos** (`48 capcules`, `CHG 260712Aand`). Keep
  the user's spelling; fix only run-on spacing. Both are tested.
- `.gitattributes` marks `*.pdf` binary — without it git applies CRLF conversion
  and corrupts the sample PDFs.
