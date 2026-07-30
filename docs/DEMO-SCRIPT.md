# Demo video script — 13 minutes

The brief asks for 10–15 minutes covering five things: **all implemented AI tools,
the frontend workflow, code flow and architecture, the LangGraph implementation,
and key design decisions.** This script covers them in that order, with timings
that leave slack.

It is written to be *spoken*, not read out. The bracketed lines are what to do on
screen; the quoted lines are the point to make, in your own words. The interview
is built on this video, so the parts where you disagree with a decision, or would
do it differently, are worth saying out loud.

---

## Before you hit record

```bash
# 1. Backend, with the key in backend/.env
cd backend && .venv\Scripts\activate && uvicorn app.main:app --reload --port 8000

# 2. Frontend
cd frontend && npm run dev
```

- Watch the backend boot log — it prints which model is really serving. Have that
  terminal visible for §5.
- Clear the ledger if you want a clean duplicate-detection demo, or leave one
  complaint in it so the check has something to find. **Leaving one in is better.**
- Have `samples/Fictional_Pharma_Customer_Complaint_API.pdf` in an easy-to-reach
  folder.
- Close anything with your Groq key on screen.
- Record at 1080p or better; the form labels are small.

---

## 0:00 – 0:45 — What this is

[Show the app, both panes visible, form empty]

> "This is a Customer Complaint intake module for a pharmaceutical QMS — the
> regulated record a manufacturer opens when a customer reports a problem with a
> batch. Left is the complaint form; right is the copilot. The rule from the brief
> is that the officer never types into the form: the agent fills it. So everything
> you see on the left is agent output."

Point at the `POWERED BY LANGGRAPH` line under the composer.

---

## 0:45 – 3:30 — Tool 1 and Tool 2: log and edit

[Paste demo prompt 1]

```
Apollo Pharmacy reported discolored capsules in Amoxicillin Capsules 500 mg. Batch number AMX240602. Manufacturing date March 2026. Expiry date February 2028. Please log this complaint
```

While it streams:

> "The stages you're seeing are real — analysing, extracting fields, generating
> the risk assessment — not a fixed-length progress bar."

[Form fills. Walk the fields.]

> "Product, strength, batch, dates — those were read from the message. The risk
> assessment underneath is LLM reasoning, not a lookup table: severity Major,
> a suggested next action, and a one-line initial assessment."

**Make the `AI INFERRED` point** — this is your first design decision:

> "These badges mark values the model *inferred* rather than read. The reference
> demo silently invents things like an affected quantity that was never stated. In
> a regulated record that's the worst possible behaviour, so I made the tools
> return a list of inferred keys and the UI badges them. Where the source says
> nothing and nothing can be inferred, the field reads 'Not Provided' rather than
> being guessed."

[Now the edit, typo included]

```
ah sorry the batch number is BMX240602 and affected quantity is 48 capcules
```

> "Two things to notice. The batch and quantity changed; nothing else moved. And
> it kept my typo — 'capcules' — because this is a regulated record and the
> officer's words are the record. The agent isn't allowed to tidy them."

---

## 3:30 – 6:00 — Tool 3: document extraction

[Drag the API complaint PDF onto the copilot]

> "Same agent, different entry point. This is a complaint report from a customer
> about an API — an active ingredient, sold to another manufacturer, not to a
> patient."

While it streams, call out the OCR stage label.

[When the form repopulates — this is the strongest 30 seconds in the video]

> "Three things just happened that are worth pausing on.
>
> First, the form *changed shape*. 'Product Strength' is now 'Product
> Strength/Grade', because a pharmacopoeial grade is what an API has instead of a
> strength. The agent returns the form **schema**, not just values — so the
> sections and labels are agent output too, and the React side renders whatever
> arrives. There's no hardcoded field list in the frontend.
>
> Second, the complainant is ABC Formulations. The document is *owned* by Zenith
> Life Sciences — they're the manufacturer receiving the complaint, and their name
> is all over the header. Getting that backwards is the obvious failure here, so
> the prompt calls it out and there's a check for it.
>
> Third, severity escalated to Critical, where the capsule case was Major. Foreign
> matter in an API propagates into every downstream batch made from it. The model
> reasons that out; it isn't a rule I hardcoded."

[Now edit after extraction]

```
ah sorry the batch number is CHG 260712Aand affected quantity is 50 kg (2 HDPE Drum)
```

> "Note there's no space in '260712Aand' — the batch runs straight into the word
> 'and'. It still comes out as 'CHG 260712A'."

**Be honest about how** (this is a good interview moment):

> "The prompt asks the model to split that, and on the first real run it ignored
> it — the whole phrase went into the batch field. So I stopped asking. There's a
> `clean_batch` function that does it in code, on both the LLM path and the
> deterministic path. If a rule matters, don't leave it to a prompt."

---

## 6:00 – 7:30 — The bonus AI features

[Run Completeness Checker, then Root Cause, then Duplicate Detection]

> "The brief lists optional extra AI features; I did all of them."

- **Completeness Checker** — "scores the record against what a reviewer needs to
  open an investigation, and flags blocking gaps."
- **Root Cause** — "ranked hypotheses across fishbone categories, each with the
  evidence pointing at it and the test that would confirm it."
- **CAPA** — "immediate containment, investigation plan, corrective and preventive
  actions."
- **Summary** — "the management line for a daily complaint log, plus whether it's
  potentially reportable to a health authority."
- **Duplicate Detection** — "the one that isn't an LLM call. It's a database query
  on the batch number, because 'has this batch been complained about before' is a
  factual question and a model is the wrong tool for it."

> "Risk classification is the sixth — it's built into all three tools rather than
> being a separate button, because a complaint should never exist without one."

[Commit to QMS Ledger]

> "Commit writes it to the ledger with a complaint number and resets the form for
> the next intake, like a real queue."

---

## 7:30 – 9:30 — Code flow and architecture

[Open `docs/ARCHITECTURE.md` §1, or the code itself]

Walk one request end to end:

> "The officer sends a message. It's a POST that streams back Server-Sent Events —
> POST, not GET, so the client reads it with `fetch` and a ReadableStream rather
> than `EventSource`, which is GET-only. The endpoint persists the message,
> streams stage updates while the agent works on a thread, then emits one result
> frame with the form sections, the risk, the status and the patch."

[Show `app/api/chat.py`, then `app/services/session_service.py`, then the agent]

> "`session_service.run_agent` is the seam: it loads state from the database,
> invokes the graph, writes back what changed, and returns the shape the client
> needs. The API layer knows nothing about LangGraph and the agent knows nothing
> about HTTP."

[Show Redux]

> "On the frontend, `complaintSlice` holds the record and `chatSlice` holds the
> transcript and streaming state. The form component just renders
> `state.complaint.sections` — which is why an agent that changes the schema
> changes the screen with no frontend change."

---

## 9:30 – 11:30 — The LangGraph implementation

[Open `app/agent/graph.py` — the ASCII diagram at the top is your visual]

> "One router node, one node per tool, and a finalize node that appends the turn
> to the transcript through the `add_messages` reducer. Conditional edges from the
> router pick the branch."

**The two-model split:**

> "The router is the only node that has to *choose*, and choosing is what native
> tool calling is for — so it binds the three tools and reads back
> `response.tool_calls[0]`. The mandated model has no tool-calling support on
> Groq, which is why the assignment also allows llama-3.3-70b 'for context'. Each
> model does what it's actually good at."

**The routing rule worth mentioning:**

> "A correction-shaped message with an *empty* form is a new complaint, not an
> edit. Without that, opening the app and pasting 'sorry, the batch number is X'
> tries to patch a record that doesn't exist. It's enforced in both the LLM path
> and the heuristic fallback, and there's a test for it."

**Degradation:**

> "Three ordered fallbacks: a document attached routes straight to extraction with
> no model call at all, because the intent is unambiguous and a round trip would
> be waste; otherwise the router model picks; and if that's unavailable, a
> heuristic does. The graph always produces a turn."

---

## 11:30 – 13:00 — Key design decisions

Pick these four. They are the ones with a real trade-off behind them.

**1. The agent returns the schema, not just values.**
> "Costs more tokens per call. Buys a form that reshapes itself for an API versus
> a finished dose form, with no frontend change. The demo shows the form changing
> shape, so the schema has to be agent output."

**2. Edits are sparse patches.**
> "The tool returns only the fields the officer named, and `apply_patch` can only
> touch keys present in the patch. So 'preserve all other complaint information'
> is structural — the code physically cannot clobber an unmentioned field — rather
> than something I asked a model to be careful about. There's a test asserting the
> patch names only those fields."

**3. The mandated model no longer exists.**
[Switch to the backend terminal, show the boot log; point at the copilot header]
> "The brief mandates `gemma2-9b-it`. Groq decommissioned it in October 2025,
> after the assignment was written — so a literal implementation can't make a
> single successful call today.
>
> I had three options: silently swap the model, which hides it from you; keep it
> and let every request 404, which is faithful and useless; or request the
> mandated model first and fall through to a live one. I did the third. The config
> still names `gemma2-9b-it`, the boot log says it's gone, and the UI says which
> model is actually answering. Only a 'model is gone' error advances the chain — a
> rate limit or bad JSON is raised instead, so one hiccup can't quietly burn
> through every model."

**4. Verification, because none of this had ever run.**
[Optionally run `python scripts/verify_llm.py` and let it scroll]
> "Everything was built against a deterministic fallback extractor, so the first
> time a real key went in, six things broke — the model returned my prompt
> instructions as the officer-facing reply, then transcribed my example values
> into a live record, severity wouldn't escalate, and so on. So there are three
> verification scripts: one replays this whole demo through the tools and diffs
> against the reference, one drives it over HTTP the way the browser does, and one
> proves the schema on a real Postgres. Plus 45 offline tests that need no key."

**Close:**
> "If I had more time: chunk long documents, since a complaint report can exceed
> the context window; and add a real auth and audit trail, because a QMS record
> needs to know who committed it."

---

## Things to avoid

- Don't read the field list aloud. Show it, talk about the two or three that
  matter.
- Don't apologise for the model substitution. It's a correct engineering call,
  and delivered flatly it reads as judgment rather than an excuse.
- Don't skip the `AI INFERRED` badges or the sparse patch. They are the two places
  where your build is *better* than the reference demo, and they are the parts an
  interviewer can push on.
- If something breaks on camera, say what you'd check. That's a better watch than
  a re-record.
