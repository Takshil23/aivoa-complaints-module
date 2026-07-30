# Demo narration — word for word

Read this aloud while doing the bracketed actions. It runs ~12 minutes at a normal
speaking pace, which lands inside the 10–15 the brief asks for.

Use it as a floor, not a ceiling: anywhere you'd say it differently, say it
differently. The interview is built on this video, so your own phrasing is worth
more than mine. If you fluff a line, pause two seconds and say it again — you can
cut it, or leave it in, because nobody minds.

**Before recording**, run the setup at the bottom of this file. It matters.

---

## 0:00 — Opening

> Hi, I'm Takshil. This is my submission for the AIVOA Round 1 full stack
> assessment — an AI-powered Customer Complaint Management System for
> pharmaceutical manufacturing.
>
> What you're looking at is a complaint intake module for a pharmaceutical Quality
> Management System. When a customer reports a problem with a batch of medicine,
> the manufacturer has to open a formal complaint record. That record is a
> regulated document — an inspector can ask to see it.
>
> On the left is the Log Customer Complaint form. On the right is the AIVOA
> Copilot. The key rule from the brief is that the QA officer never types into the
> form. Everything on the left is filled by the agent.

[Point at `POWERED BY LANGGRAPH` under the composer]

> And that's LangGraph underneath, which I'll come back to.

---

## 0:40 — Tool 1: Log Complaint

> Let's log a complaint. I'll paste in a message the way it might arrive from a
> pharmacy.

[Paste, press Enter]

```
Apollo Pharmacy reported discolored capsules in Amoxicillin Capsules 500 mg. Batch number AMX240602. Manufacturing date March 2026. Expiry date February 2028. Please log this complaint
```

> While that runs — those progress stages are real. The backend streams them as
> the work actually happens, rather than animating a progress bar for a fixed
> number of seconds.

[Form fills]

> So the form is populated. Product name, strength, batch number, manufacturing
> and expiry dates — those were all read out of the message.
>
> Underneath is the AI risk assessment. Severity Major, a suggested next action,
> and a one-line initial assessment. That's the model reasoning about the
> complaint — it's not a lookup table or a rules engine.

[Point at an `AI INFERRED` badge]

> Now this is the first design decision I want to call out. These badges mark
> values the model inferred rather than read.
>
> In the reference demo, the agent silently invents an affected quantity that was
> never in the input. I decided not to copy that. In a regulated record, quietly
> inventing data is the worst thing this system could do. So the tools return a
> list of which fields were inferred, and the UI marks them. Where nothing can be
> read or reasonably inferred, the field says "Not Provided" instead of a guess.

---

## 2:20 — Tool 2: Edit Complaint

> The officer made a mistake, and corrects it in natural language.

[Paste, press Enter]

```
ah sorry the batch number is BMX240602 and affected quantity is 48 capcules
```

[Wait for the update]

> Two things there. The batch number and the quantity changed, and nothing else
> moved — the product, the dates, the description are all untouched.
>
> That's not luck. The edit tool returns a sparse patch: only the fields the
> officer actually named. The merge function can only write keys that are present
> in that patch. So "preserve all other complaint information" is structural — the
> code physically cannot overwrite a field the officer didn't mention.
>
> The second thing: I typed "capcules", misspelled, and it kept my spelling. This
> is a regulated record, so the officer's words are the record. The agent isn't
> allowed to tidy them up.

---

## 3:30 — Tool 3: Document Extraction

> Third tool. Same agent, different way in — a complaint that arrives as a PDF.

[Drag `samples/Fictional_Pharma_Customer_Complaint_API.pdf` onto the copilot]

> This one is about an API — an Active Pharmaceutical Ingredient. That's the raw
> drug substance, sold to another manufacturer who formulates it into a finished
> medicine. So it's a different kind of complaint to the capsules.

[Wait for the form to repopulate]

> Three things just happened that I want to slow down on.
>
> First — look at this label. It said "Product Strength" for the capsules. It now
> says "Product Strength / Grade", because an API doesn't have a strength like
> "500 milligrams", it has a pharmacopoeial grade — here, IP/BP.
>
> That's because the agent returns the form *schema*, not just the values. The
> sections, the field labels, the whole shape of the form is agent output, and
> React renders whatever arrives. There is no hardcoded field list in the
> frontend. That costs more tokens per call, but the demo shows the form changing
> shape, so the schema has to come from the agent.
>
> Second — the customer name is ABC Formulations. The document itself belongs to
> Zenith Life Sciences, whose name is all over the header, because they're the
> manufacturer *receiving* the complaint. Getting those two backwards is the
> obvious failure mode here, so the prompt calls it out explicitly and I have a
> check for it.
>
> Third — severity is Critical. The capsule complaint was Major. Foreign matter in
> an API propagates into every downstream batch made from that ingredient, so it's
> a more serious finding. The model reasons that out; I didn't hardcode it.

---

## 5:30 — Editing after extraction

> And I can still correct it in natural language after extraction.

[Paste, press Enter]

```
ah sorry the batch number is CHG 260712Aand affected quantity is 50 kg (2 HDPE Drum)
```

> Notice there's no space in "260712Aand" — the batch number runs straight into
> the word "and". It still comes out clean as "CHG 260712A".
>
> I want to be honest about how. The prompt asks the model to split that, and on
> the first real run against Groq, it ignored the instruction completely — the
> whole phrase went into the batch field. So I stopped asking. There's a function
> that does the split in code, applied on both the AI path and the deterministic
> fallback path. The lesson I took: if a rule actually matters, don't leave it to
> a prompt.

---

## 6:20 — Bonus AI features

> The brief lists optional extra AI features. I implemented all of them.

[Click Completeness Checker]

> Completeness scores the record against what a reviewer needs to actually open an
> investigation, and flags anything blocking.

[Click Root Cause Recommendation]

> Root cause gives ranked hypotheses across fishbone categories — Man, Machine,
> Material, Method — each with the evidence pointing at it and the test that would
> confirm or rule it out.

[Click CAPA Recommendation]

> CAPA drafts immediate containment, an investigation plan, and corrective and
> preventive actions.

[Click Complaint Summary]

> Summary is the management line for a daily complaint log, plus whether it's
> potentially reportable to a health authority.

[Click Duplicate Detection]

> And duplicate detection is the one that is deliberately *not* an LLM call. It's a
> database query on the batch number. "Has anyone complained about this batch
> before" is a factual question with an exact answer, and a language model is the
> wrong tool for it.
>
> Risk classification is the sixth feature — it's built into all three tools
> rather than being a separate button, because a complaint should never exist
> without one.

[Click Commit to QMS Ledger]

> Commit writes it to the ledger with a complaint number and resets the form for
> the next intake, like a real intake queue.

---

## 8:00 — Code flow and architecture

[Switch to the editor — `app/api/chat.py`]

> Let me walk one request end to end.
>
> The officer sends a message. That's a POST that streams back Server-Sent Events.
> It has to be a POST, which means the browser reads it with fetch and a
> ReadableStream — the standard EventSource API only does GET.
>
> The endpoint saves the message, streams progress stages while the agent works on
> a separate thread, then sends one result frame containing the form sections, the
> risk, the status, and the patch.

[Open `app/services/session_service.py`]

> This is the seam between the web layer and the agent. It loads state from
> Postgres, invokes the graph, writes back what changed, and returns the shape the
> client needs. The API layer knows nothing about LangGraph, and the agent knows
> nothing about HTTP.

[Open `frontend/src/store/complaintSlice.js`]

> On the frontend, Redux Toolkit. One slice holds the complaint record, another
> holds the chat transcript and streaming state. The form component just renders
> the sections array out of Redux — which is exactly why an agent that changes the
> schema changes the screen with no frontend change at all.

---

## 9:30 — LangGraph implementation

[Open `app/agent/graph.py` — the diagram at the top]

> Here's the graph. A router node, one node per tool, and a finalize node that
> appends the turn to the transcript using LangGraph's add_messages reducer.
> Conditional edges from the router pick the branch.
>
> The router is the only node that has to *choose*, and choosing is exactly what
> native tool calling is for. So it binds the three tools and reads back which one
> the model selected.
>
> That's also why there are two models. The assignment mandates gemma2-9b-it,
> which has no tool-calling support on Groq, and it also allows llama-3.3-70b for
> context. So the router runs on llama, and everything else runs on the mandated
> model through strict JSON prompting. Each model does what it's actually good at.
>
> One routing rule worth mentioning: a correction-shaped message when the form is
> *empty* is treated as a new complaint, not an edit. Without that, opening the app
> and pasting "sorry, the batch number is X" tries to patch a record that doesn't
> exist. It's enforced in both the model path and the fallback, and there's a test
> for it.
>
> And there are three ordered fallbacks. If a document is attached, it routes
> straight to extraction with no model call at all, because the intent is
> unambiguous and a round trip would be wasted. Otherwise the router model picks.
> And if that's unavailable, a heuristic does. The graph always produces a turn.

---

## 11:00 — Key design decisions

> Finally, the decisions I'd defend.
>
> The first two I've shown you — the agent returns the schema rather than just
> values, and edits are sparse patches so field preservation is structural rather
> than something I asked a model to be careful about.
>
> Third.

[Switch to the browser, point at the model line in the copilot header]

> The brief mandates gemma2-9b-it. Groq decommissioned that model in October 2025,
> after the assignment was written. So a literal implementation of the brief can't
> make a single successful API call today.
>
> I had three options. Silently swap in another model, which hides it from you.
> Keep it and let every request fail, which is faithful and useless. Or request the
> mandated model first and fall through to a live one.
>
> I did the third. The config still names gemma2-9b-it, the startup log says out
> loud that it's gone, and the UI names the model that actually answered. Only a
> "model is gone" error advances the chain — a rate limit or a bad response is
> raised normally, so one temporary failure can't quietly burn through every model.
>
> Fourth, and this is the one I learned the most from.

[Optional: switch to a terminal and run `python scripts/verify_llm.py`]

> Everything was built against a deterministic fallback extractor, so the prompts
> had never actually met a model. The first time I put a real Groq key in, six
> things broke at once. The model returned my own prompt instructions as the reply
> to the officer. When I replaced those instructions with realistic examples, it
> got worse — it started transcribing my example record into live complaints.
>
> The worst one I found by clicking around in the UI. I typed "I don't have that"
> into an empty form, and got back a complete complaint — a customer, a product, an
> invented batch number, dates, a defect description — and the form went to Ready
> to Commit. Every one of those values traced back to an example inside my own
> prompt. A small model with nothing to extract will extract the instructions.
>
> Fabricated data in a regulated record is worse than a crash, because it looks
> plausible. So the fix isn't a better prompt. There's now a grounding check: any
> field the model claims to have *read* has to be traceable back to the source
> text, or it becomes "Not Provided". If nothing survives, there's no complaint,
> and the agent says so instead of inventing one.

[Type "i dont have that" into the copilot and show the empty form]

> So this is what it does now.
>
> That's also why there are three verification scripts in the repo — one replays
> this whole demo through the tools, one drives it over HTTP the way the browser
> does, and one proves the schema on a real PostgreSQL server. Plus 73 tests that
> run with no API key.

---

## 12:30 — Close

> If I had more time: I'd chunk long documents, because a complaint report can
> exceed the model's context window; and I'd add authentication and an audit
> trail, because a real QMS record needs to know who committed it and when.
>
> The code's on GitHub, the README covers setup, and I'm happy to go deeper on any
> of it. Thanks for watching.

---

## Recording setup — do this first

**1. Kill every Python process and start clean.** Do not trust `--reload`; it left
an orphan holding the port and served ten-hour-old code.

```powershell
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force
& "C:\Users\taksh\postgres\pgsql\bin\pg_ctl.exe" -D "C:\Users\taksh\postgres\data" -l "C:\Users\taksh\postgres\server.log" start
cd "d:\Project AIVOA\backend"; .venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

Frontend in a second terminal: `cd frontend; npm run dev`

**2. Sanity-check before you hit record.** Load `http://localhost:5173`, confirm
the copilot header shows the model line, and send one real complaint. If the
"no GROQ_API_KEY" banner appears, the backend isn't the one you just started.

**3. Recorder.** Windows has one built in — **Win + G**, then the record button.
OBS is better if you have it. Record the whole screen at 1080p or higher; the form
labels are small.

**4. Audio.** Test thirty seconds first and play it back. Bad audio sinks a good
demo faster than anything else on screen.

**5. Close** anything with your Groq key, your email, or personal tabs in it. Your
bookmarks bar is visible in the browser — consider hiding it with **Ctrl+Shift+B**.

**6. Rate limits.** Groq's free tier limits requests per minute, and this demo
makes a lot of them. If a bonus feature returns a "rate limit" message, wait ten
seconds and click it again — the app handles it cleanly, and you can cut the pause.

**7. Upload** to Google Drive or YouTube unlisted, then **set sharing to "anyone
with the link"** and open it in a private window to confirm. A permission-gated
video is the most common way these submissions fail.
