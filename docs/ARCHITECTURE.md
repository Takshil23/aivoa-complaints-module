# Architecture

How the pieces fit, and why they are shaped this way. Written for the interview
walkthrough — every non-obvious choice has its reasoning attached.

---

## 1. Request flow

```
  Browser (React + Redux)
        │
        │  POST /api/chat/stream         { sessionId, message }
        │  POST /api/documents/stream    multipart file
        ▼
  FastAPI route  ──►  session_service.run_agent()
        │                     │
        │                     ├── load session state from the database
        │                     ├── GRAPH.invoke(state)          ← LangGraph
        │                     └── persist the updated record
        │
        └──►  SSE frames back to the browser:
                 user_message → status* → result → done
                       │
                       ▼
              Redux: chatSlice.appendMessage
                     chatSlice.setProgress
                     complaintSlice.applyAgentResult
```

Both streaming endpoints are **POST**, so the client reads them with `fetch` +
`ReadableStream` rather than `EventSource`, which only supports GET. The frame
parser lives in `frontend/src/api/client.js` and splits on the SSE `\n\n`
boundary — a detail worth getting right, because a naive line-by-line reader
breaks the moment a JSON payload is split across two network chunks.

---

## 2. The LangGraph graph

```
                        START
                          │
                          ▼
                    ┌──────────┐
                    │  router  │
                    └──────────┘
                          │
        ┌─────────────┬───┴────────┬──────────────────┐
        ▼             ▼            ▼                  ▼
 log_complaint  edit_complaint  extract_document  answer_question
        └─────────────┴────────────┴──────────────────┘
                          │
                          ▼
                    ┌──────────┐
                    │ finalize │  → END
                    └──────────┘
```

`app/agent/graph.py`. One node per tool, a conditional edge from the router, and a
`finalize` node that appends the turn to the transcript via LangGraph's
`add_messages` reducer.

### The router, and the two-model split

The router is the only node that needs to *choose*, and choosing is what native
tool calling is for. So:

- **Router** — `llama-3.3-70b-versatile` with `bind_tools([log_complaint,
  edit_complaint, answer_question])`. The model emits a tool call; the graph reads
  `response.tool_calls[0].name` and routes.
- **Everything else** — `gemma2-9b-it`, the mandated model, doing extraction and
  reasoning through strict JSON prompting.

**Why not gemma2 for the router too?** `gemma2-9b-it` does not support native tool
calling on Groq. Forcing the routing decision through it would mean parsing an
intent out of free text — strictly worse than a model that returns a structured
tool call. The assignment names `llama-3.3-70b-versatile` as available "for
context", so this uses each model for what it is actually good at, and both are
configurable in `.env`.

### The mandated model no longer exists — and the code says so out loud

Groq decommissioned `gemma2-9b-it` on **2025-10-08** (announced 2025-08-08, in
favour of `llama-3.1-8b-instant`), and deprecated `llama-3.3-70b-versatile` on
2026-06-17 with shutdown on **2026-08-16**. Both dates fall after the assignment
was written, so a literal implementation of the brief cannot make a single
successful API call today.

Three ways to handle that, and the choice is deliberate:

1. Silently swap the model. Fails the brief's "do not substitute" rule, and hides
   the substitution from the reviewer.
2. Keep `gemma2-9b-it` and let every request 404. Faithful and useless.
3. **Request the mandated model first, fall through to a live one.** `PRIMARY_MODEL`
   is still `gemma2-9b-it`; `settings.model_chain()` appends
   `PRIMARY_MODEL_FALLBACKS`. `llm._with_fallback()` advances the chain **only** on
   a "model is gone" error (`model_decommissioned` / `model_not_found`) — a rate
   limit or malformed JSON is raised to the caller instead, so a transient failure
   never silently burns through every model. A dead id is cached per process, so
   the 404 is paid once rather than once per request, and `POST /api/session`
   returns `models.primary` (requested) alongside `models.activePrimary` (serving).

The same chain covers the router role. `tests/test_model_fallback.py` pins the
behaviour without touching the network, and `scripts/verify_llm.py --probe` prints
exactly which ids Groq is still answering on.

Below the chain, three ordered fallbacks keep the graph running when the preferred
path is not available:

1. A document is attached → route straight to `extract_document`. No model call —
   the intent is unambiguous, so spending a round trip on it would be waste.
2. Router model available → native tool call.
3. Otherwise → heuristic (`_EDIT_HINTS` / `_QUESTION_HINTS` regexes plus "is a
   complaint already loaded?").

One rule matters more than it looks: **a correction-shaped message with an empty
form is a new complaint, not an edit.** Without it, opening the app and pasting
"sorry, the batch number is X" tries to patch a record that does not exist. The
router enforces it in both the LLM and heuristic paths, and a test covers it.

### State

`app/agent/state.py`. `AgentState` carries the session id, the transcript, this
turn's inputs (`user_input` / `document_text` / `filename`), the record being
built (`form_sections`, `risk`, `status`), and this turn's outputs (`route`,
`tool_used`, `reply`, `patch`).

Persistence is in the database rather than a LangGraph checkpointer. The state a
complaint session needs is small, structured, and has to be queryable for
duplicate detection and the ledger — a `Session` row with a JSON schema column is
a better fit than an opaque checkpoint blob, and it means the same tables serve
the app and the QMS record.

---

## 3. The form schema is agent output

This is the load-bearing decision.

Watching the demo, the form does not merely *fill in* — it **changes shape**:

| | Before parsing | After parsing |
|---|---|---|
| Sections | 3 | 4 |
| First section | `PRODUCT & BATCH IDENTIFICATION` | `ORIGIN & CUSTOMER DETAILS` |
| Product field | `Product Name (API/FDF)` | `Product Name` |
| Strength field | *(absent)* | `Product Strength` … or `Product Strength/Grade` for an API |

So a hardcoded React form cannot reproduce it. Instead the agent returns:

```json
{
  "sections": [
    {
      "index": 2,
      "title": "PRODUCT & BATCH IDENTIFICATION",
      "fields": [
        {
          "key": "product_strength",
          "label": "Product Strength/Grade",
          "type": "text",
          "value": "IP/BP",
          "options": null,
          "inferred": false,
          "fullWidth": false
        }
      ]
    }
  ]
}
```

`ComplaintForm.jsx` maps over `sections` and `FormField.jsx` switches on `type`.
Neither knows any field name. Adding a field to the QMS record is a change in
`app/services/form_schema.py` and nowhere else.

`strength_label_for()` is what flips the label: APIs are supplied to a
pharmacopoeial **grade** (IP/BP/USP), finished dose forms have a **strength** in mg.
Small touch, but it is the kind of domain detail the brief is asking about when it
says to research how pharmaceutical QMS complaint modules work.

---

## 4. Why edits are sparse patches

The brief requires that an edit updates the named fields "while preserving all
other complaint information". Two ways to do that:

1. Ask the model to return the whole record with two values changed, and hope it
   reproduces the other ten exactly.
2. Ask it for **only** what changed, and merge.

Option 1 fails the way LLMs always fail this: it silently drops a field, reformats
a date, or paraphrases the description. Option 2 makes preservation structural.

```python
# app/services/form_schema.py
def apply_patch(sections, patch):
    out = deepcopy(sections)
    for section in out:
        for field in section["fields"]:
            if field["key"] in patch:
                field["value"] = patch[field["key"]]
    return out
```

Fields absent from `patch` are unreachable by that loop, so they cannot change.
`test_patches_only_named_fields` asserts every unmentioned field is byte-identical
after an edit.

The tool also echoes the field's **display label**, not its key — "I have updated
the *Batch / Lot Number*", not `batch_lot_number` — using `label_map()`. That is
what the demo does, and it is what makes the confirmation checkable by a human.

### Handling the demo's typos

Both correction prompts in the video are malformed, deliberately:

| Input | Correct reading |
|-------|-----------------|
| `48 capcules` | keep the misspelling — it is the officer's own text |
| `CHG 260712Aand affected quantity is…` | batch is `CHG 260712A`; `and` belongs to the sentence |

The prompt tells the model to reproduce spelling verbatim but to fix run-on
spacing, and the deterministic fallback strips a trailing `and` after an
alphanumeric batch code. Both are tested.

---

## 5. Document extraction

`app/services/document_parser.py`.

Production OCR is out of scope per the brief. What actually matters for complaint
reports is **tables** — the batch number, quantity and dates live in a grid, not in
prose. So `pdfplumber` runs both `extract_text()` and `extract_tables()`, and table
rows are flattened to `Cell | Cell | Cell` lines before being handed to the model.

That flattening drove a real bug worth mentioning in the interview. A four-column
table renders as:

```
Batch / Lot No. | MFH260712A | Quantity Affected | 25 kg (1 HDPE Drum)
```

The second key/value pair sits **mid-row**, so a label matcher anchored to the
start of a line finds `Batch / Lot No.` and misses `Quantity Affected` entirely.
The fix — allowing a label to follow a pipe as well as start a line — only surfaced
by generating real PDFs and testing against them, which is why `samples/` exists as
a generator rather than as three checked-in binaries.

Image-only PDFs are detected (no extractable text) and reported plainly rather than
returning an empty record that looks like a successful parse.

---

## 6. Data model

`app/db/models.py`. Three tables, portable across PostgreSQL, MySQL and SQLite —
`JSON` columns map to `jsonb` / `JSON` / `TEXT`, and no server-specific defaults
are used.

| Table | Role |
|-------|------|
| `sessions` | One intake session: the live `form_sections` JSON, `risk` JSON, `status` |
| `chat_messages` | The transcript, including file attachments (`kind='file'`) and the tool used per turn |
| `complaints` | A committed complaint — flat columns for querying **plus** `form_snapshot` |

`complaints` stores both flat columns and the full schema snapshot on purpose. Flat
columns make the record queryable (duplicate detection joins on
`batch_lot_number`); the snapshot means a complaint committed today still renders
exactly as it was captured even after the schema evolves. That is a regulated-record
concern: the QMS entry must not be retroactively reshaped.

`CC-YYYY-NNNNN` numbering follows the `CC-2026-00154` reference in the demo PDF.

---

## 7. Redux layout

Two slices, split by what owns the data rather than by screen:

**`complaintSlice`** — `sessionId`, `sections`, `risk`, `status`,
`recentlyChanged`, commit state, ledger.
**`chatSlice`** — `messages`, `isStreaming`, `progress`, bonus-feature panel.

A single agent turn updates both, so the stream handler dispatches across slices:
`chatSlice.appendMessage` for the bubble, `complaintSlice.applyAgentResult` for the
form. Async thunks (`sendMessage`, `uploadDocument`) own the streaming lifecycle;
the SSE frame handler is shared between them because chat and upload emit the same
frame vocabulary.

`recentlyChanged` holds the field keys from the last `patch` and drives a 1.6s
flash highlight, so when the copilot says it changed two fields you can *see* which
two. It self-clears from `App.jsx`.

---

## 8. Divergences from the reference demo

Deliberate, and each one is a defensible answer to "why doesn't it look identical?"

| # | Demo | Here | Why |
|---|------|------|-----|
| 1 | Invents `12 capsules`, `Primary Packaging (Bottle)` silently | Same inference, tagged **AI INFERRED** with a tooltip | Unmarked invention in a regulated record is a liability. Keeps the speed, adds the audit trail. |
| 2 | Fixed ~10s progress bar, one label | Real stages streamed as work happens | Honest, and it surfaces where time is actually spent. |
| 3 | `Suggested Next Action` / `Initial Risk Assessment` clipped in one-line inputs | Textareas | The assessment is the point; a QA officer has to be able to read it. |
| 4 | `Commit to QMS Ledger` never clicked | Validates, writes `CC-YYYY-NNNNN`, snapshots, resets | The behaviour had to be specified; this is the QMS-plausible one. |
| 5 | Form editability unknown | Read-only, with a visible off-by-default unlock | The brief forbids manual filling; a real officer still needs an override. |
| 6 | Missing data shown as `Not Provided` | Same | Matched deliberately — a blank field is ambiguous, `Not Provided` is a statement. |

---

## 9. What I would do next

- **Chunk long documents.** `gemma2-9b-it` has a modest context window; a
  multi-page complaint dossier should be chunked and map-reduced.
- **A LangGraph checkpointer** if the agent grew multi-turn planning or
  human-in-the-loop interrupts. The current single-turn tool dispatch does not need
  one.
- **Named users and an audit trail** — who logged, who amended, who committed. The
  `chat_messages` table already records the tool used per turn, so the spine is
  there.
- **Confidence per field**, not just a boolean `inferred`, so a reviewer can triage
  which extracted values to double-check.
- **Structured dates.** Everything is a display string today because the demo keeps
  the source's granularity ("March 2026" vs "25 June 2026"). A real QMS wants a
  real date type plus the original text.
