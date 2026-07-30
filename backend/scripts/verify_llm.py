"""Exercise every real-Groq code path and report what actually happened.

Everything in this project was built and tested against the deterministic
fallback extractor, so this script is the first-contact test for the LLM paths:
the model chain, the router's native tool calling, the three mandatory tools and
the four LLM-backed bonus features. It replays the exact demo script in
docs/REFERENCE-SPEC.md §4 and diffs the result against the reference values.

    cd backend
    .venv\\Scripts\\python.exe scripts/verify_llm.py            # all checks
    .venv\\Scripts\\python.exe scripts/verify_llm.py --probe    # models only
    .venv\\Scripts\\python.exe scripts/verify_llm.py --no-bonus

Needs GROQ_API_KEY in backend/.env. Writes nothing to the database used by the
app — it drives the tools and the graph directly.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agent import graph as G  # noqa: E402
from app.agent import llm, tools as T  # noqa: E402
from app.config import settings  # noqa: E402
from app.services.document_parser import parse  # noqa: E402
from app.services.form_schema import flatten  # noqa: E402

SAMPLES = ROOT.parent / "samples"

PASS, FAIL, WARN = "PASS", "FAIL", "WARN"
results: list[tuple[str, str, str]] = []


# --- reporting ---------------------------------------------------------------

def record(status: str, name: str, detail: str = "") -> None:
    results.append((status, name, detail))
    mark = {PASS: "[ok]  ", FAIL: "[FAIL]", WARN: "[warn]"}[status]
    print(f"{mark} {name}" + (f" - {detail}" if detail else ""))


def head(title: str) -> None:
    print(f"\n{'=' * 74}\n{title}\n{'=' * 74}")


def show_block(label: str, payload: dict[str, Any]) -> None:
    print(f"  {label}:")
    for key, value in payload.items():
        print(f"      {key}: {value}")


def show_fields(fields: dict[str, str]) -> None:
    width = max(len(k) for k in fields)
    for key, value in fields.items():
        print(f"    {key.ljust(width)}  {value}")


def diff_fields(
    label: str, actual: dict[str, str], expected: dict[str, str]
) -> None:
    """Compare against the reference demo. Differences are WARN, not FAIL — the
    model is free to word things differently; what matters is that the values it
    *read from the source* are right."""
    for key, want in expected.items():
        got = (actual.get(key) or "").strip()
        if got.lower() == want.lower():
            record(PASS, f"{label}: {key}", got)
        else:
            record(WARN, f"{label}: {key}", f"expected {want!r}, got {got!r}")


def require(status_ok: bool, label: str, detail: str = "") -> bool:
    record(PASS if status_ok else FAIL, label, detail)
    return status_ok


# Phrases lifted straight out of the prompts. If one shows up in a reply, the model
# copied the instruction instead of composing prose — which the QA officer then
# reads in the chat panel.
_ECHOES = (
    "confirm the change",
    "confirm extraction",
    "naming each field",
    "one or two sentences",
    "never copy this instruction",
    "do not carry any of them over",
)

# Values that appear ONLY in the prompts' worked examples. Any of them landing in a
# record means the model transcribed the example instead of reading the source — the
# worst failure mode available, because the output looks plausible.
_EXAMPLE_LEAKS = (
    "Nordic Pharma",
    "Ibuprofen",
    "IBU250114",
    "blister strip",
    "Blister Foil",
    "CC-2025-00087",
    "sealing-station",
    "sealing station",
    "label reel",
    "print station",
)

_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def check_no_example_leak(label: str, blob: str) -> None:
    leaked = [value for value in _EXAMPLE_LEAKS if value.lower() in blob.lower()]
    require(
        not leaked,
        f"{label}: no prompt-example values leaked into the record",
        f"leaked {leaked}" if leaked else "",
    )


def check_reply(label: str, reply: str) -> None:
    text = (reply or "").strip()
    require(bool(text), f"{label}: reply is non-empty")
    echoed = [phrase for phrase in _ECHOES if phrase in text.lower()]
    require(
        not echoed,
        f"{label}: reply is composed prose, not the prompt echoed back",
        f"echoed {echoed}" if echoed else "",
    )
    # Abbreviations like "Ltd." split badly, so only weigh real sentences.
    sentences = [s.strip() for s in _SENTENCE.split(text) if len(s.strip()) >= 25]
    repeated = [s for s in set(sentences) if sentences.count(s) > 1]
    require(
        not repeated,
        f"{label}: no duplicated sentence",
        f"repeated {repeated}" if repeated else "",
    )


# --- checks ------------------------------------------------------------------

def probe_models() -> bool:
    """Call every model in both chains so we know exactly which ones are live."""
    head("1. Model probe")
    print(f"  primary chain: {settings.model_chain('primary')}")
    print(f"  router chain:  {settings.model_chain('router')}\n")

    ok = True
    for kind in ("primary", "router"):
        for model in settings.model_chain(kind):
            started = time.time()
            try:
                response = llm._build(model).invoke(
                    [("human", "Reply with the single word: ready")]
                )
                took = time.time() - started
                text = llm._content_text(response.content).strip()[:40]
                record(PASS, f"{kind}/{model}", f"{took:.1f}s - {text!r}")
            except Exception as exc:  # noqa: BLE001
                gone = bool(llm._MODEL_GONE.search(str(exc)))
                record(
                    WARN if gone else FAIL,
                    f"{kind}/{model}",
                    ("decommissioned" if gone else str(exc)[:160]),
                )
                if gone:
                    # The probe calls models directly, so tell the chain what we
                    # learned — otherwise the rest of the run re-pays this 404.
                    llm.mark_dead(model)
                else:
                    ok = False

    # A chain is only healthy if at least one model in it answered.
    for kind in ("primary", "router"):
        live = [
            m for m in settings.model_chain(kind) if m not in llm._dead
        ]
        ok &= require(
            bool(live), f"{kind} chain has a live model", ", ".join(live) or "none"
        )
    return ok


def check_json_mode() -> bool:
    head("2. Strict JSON contract")
    try:
        payload = llm.json_call(
            'Return JSON only, exactly: {"ok": true, "n": 3}',
            "Go.",
        )
    except Exception as exc:  # noqa: BLE001
        return require(False, "json_call returns a dict", str(exc)[:200])
    ok = require(isinstance(payload, dict), "json_call returns a dict", str(payload))
    return ok and require(
        payload.get("ok") is True, "model honours the JSON shape", json.dumps(payload)
    )


def check_router() -> bool:
    """The router must pick the right tool via native tool calling — the whole
    reason llama-3.3-70b is in the stack alongside the mandated model."""
    head("3. Router (native tool calling)")
    empty = G.initial_state("verify")
    cases = [
        ("Apollo Pharmacy reported discolored capsules in Amoxicillin 500 mg.",
         False, G.ROUTE_LOG),
        ("ah sorry the batch number is BMX240602", True, G.ROUTE_EDIT),
        ("what is the severity of this complaint?", True, G.ROUTE_ANSWER),
        # A correction-shaped message with nothing on the form is still a new log.
        ("ah sorry the batch number is BMX240602", False, G.ROUTE_LOG),
    ]

    # A minimally-populated form, enough for _has_complaint() to be true.
    from app.services.form_schema import populated_schema

    filled = populated_schema(
        {
            "product_name": "Amoxicillin Capsules",
            "batch_lot_number": "AMX240602",
            "customer_name": "Apollo Pharmacy",
            "complaint_description": "Discoloured capsules reported.",
        }
    )

    ok = True
    for text, loaded, expected in cases:
        state = dict(empty)
        state["user_input"] = text
        state["form_sections"] = filled if loaded else empty["form_sections"]
        route = G.router_node(state).get("route")
        ok &= require(
            route == expected,
            f"route({'loaded' if loaded else 'empty'}): {text[:38]!r}",
            f"-> {route} (want {expected})",
        )
    return ok


def check_log_complaint() -> dict[str, Any]:
    head("4. Tool 1 - log_complaint (demo turn 1, FDF case)")
    prompt = (
        "Apollo Pharmacy reported discolored capsules in Amoxicillin Capsules "
        "500 mg. Batch number AMX240602. Manufacturing date March 2026. Expiry "
        "date February 2028. Please log this complaint"
    )
    started = time.time()
    state = T.log_complaint(prompt)
    print(f"  {time.time() - started:.1f}s on {llm.active_model('primary')}\n")

    fields = flatten(state["form_sections"])
    show_fields(fields)
    print(f"\n  reply: {state['reply']}")
    show_block("risk", state["risk"])

    check_reply("log", state["reply"])
    check_no_example_leak("log", json.dumps(fields) + state["reply"])
    diff_fields(
        "log",
        fields,
        {
            "customer_name": "Apollo Pharmacy",
            "product_name": "Amoxicillin Capsules",
            "product_strength": "500 mg",
            "batch_lot_number": "AMX240602",
            "manufacturing_date": "March 2026",
            "expiry_date": "February 2028",
            "complaint_source": "Pharmacy",
            "originating_site_block": "Manufacturing",
        },
    )
    risk = state["risk"]
    require(
        risk.get("severity") in {"Critical", "Major", "Minor"},
        "severity is one of Critical/Major/Minor",
        str(risk.get("severity")),
    )
    for key in ("suggested_next_action", "initial_risk_assessment"):
        require(bool((risk.get(key) or "").strip()), f"risk.{key} populated")

    inferred = [
        f["key"]
        for section in state["form_sections"]
        for f in section["fields"]
        if f.get("inferred")
    ]
    record(
        PASS if inferred else WARN,
        "inferred fields tagged AI INFERRED",
        ", ".join(inferred) or "none returned by the model",
    )
    return state


def check_edit_complaint(state: dict[str, Any]) -> dict[str, Any]:
    head("5. Tool 2 - edit_complaint (demo turn 2, sparse patch + typo kept)")
    instruction = "ah sorry the batch number is BMX240602 and affected quantity is 48 capcules"
    before = flatten(state["form_sections"])

    started = time.time()
    result = T.edit_complaint(instruction, state["form_sections"], state["risk"])
    print(f"  {time.time() - started:.1f}s on {llm.active_model('primary')}\n")

    patch = result["patch"]
    after = flatten(result["form_sections"])
    show_block("patch", patch)
    print(f"  reply: {result['reply']}")

    check_reply("edit", result["reply"])
    check_no_example_leak("edit", json.dumps(patch) + result["reply"])
    require(bool(patch), "patch is non-empty")
    require(
        set(patch) <= {"batch_lot_number", "affected_quantity"},
        "patch touches ONLY the two named fields",
        ", ".join(sorted(patch)) or "empty",
    )
    require(
        after.get("batch_lot_number") == "BMX240602",
        "batch updated",
        str(after.get("batch_lot_number")),
    )
    record(
        PASS if after.get("affected_quantity") == "48 capcules" else WARN,
        "officer's typo 'capcules' preserved verbatim",
        str(after.get("affected_quantity")),
    )

    untouched = [
        k
        for k, v in before.items()
        if k not in patch and after.get(k) != v
    ]
    require(
        not untouched,
        "every other field preserved",
        "changed: " + ", ".join(untouched) if untouched else "",
    )
    require(
        bool(result["risk"].get("severity")),
        "risk re-assessed after the edit",
        str(result["risk"].get("severity")),
    )
    return result


def check_extract_document() -> dict[str, Any]:
    head("6. Tool 3 - extract_document (demo turn 3, API case, real PDF)")
    pdf = SAMPLES / "Fictional_Pharma_Customer_Complaint_API.pdf"
    if not pdf.exists():
        record(FAIL, "sample PDF present", str(pdf))
        return {}
    text = parse(pdf.name, pdf.read_bytes())
    record(PASS, "PDF parsed", f"{len(text)} chars")

    started = time.time()
    state = T.extract_document(text, pdf.name)
    print(f"  {time.time() - started:.1f}s on {llm.active_model('primary')}\n")

    fields = flatten(state["form_sections"])
    show_fields(fields)
    print(f"\n  reply: {state['reply']}")
    show_block("risk", state["risk"])

    diff_fields(
        "extract",
        fields,
        {
            "customer_name": "ABC Formulations Ltd.",
            "product_name": "Metformin Hydrochloride API",
            "batch_lot_number": "MFH260712A",
            "affected_quantity": "25 kg (1 HDPE Drum)",
            "manufacturing_date": "25 June 2026",
            "complaint_category": "Foreign Matter Contamination",
            "impacted_npm": "HDPE Drum",
        },
    )
    # The complainant / manufacturer distinction is the one thing the model must
    # not get wrong: Zenith Life Sciences owns the report, ABC filed it.
    require(
        "zenith" not in (fields.get("customer_name") or "").lower(),
        "complainant not confused with the receiving manufacturer",
        str(fields.get("customer_name")),
    )
    require(
        "CC-2026-00154" in state["reply"],
        "complaint reference quoted in the reply",
    )
    description = (fields.get("complaint_description") or "").strip()
    require(
        description.lower() not in {"", "not provided"},
        "complaint description extracted, not dropped",
        description[:60] or "empty",
    )
    check_reply("extract", state["reply"])
    check_no_example_leak(
        "extract", json.dumps(fields) + json.dumps(state["risk"]) + state["reply"]
    )
    # An API gets a pharmacopoeial grade, and the label must switch with it.
    labels = {
        f["key"]: f["label"]
        for section in state["form_sections"]
        for f in section["fields"]
    }
    require(
        labels.get("product_strength") == "Product Strength/Grade",
        "strength label switched for an API",
        str(labels.get("product_strength")),
    )
    require(
        state["risk"].get("severity") == "Critical",
        "foreign matter in an API escalates to Critical",
        str(state["risk"].get("severity")),
    )
    return state


def check_edit_after_extract(state: dict[str, Any]) -> None:
    head("7. Demo turn 4 - edit after extraction (run-on batch number)")
    instruction = (
        "ah sorry the batch number is CHG 260712Aand affected quantity is "
        "50 kg (2 HDPE Drum)"
    )
    result = T.edit_complaint(instruction, state["form_sections"], state["risk"])
    after = flatten(result["form_sections"])
    print(f"  patch: {json.dumps(result['patch'])}")
    print(f"  reply: {result['reply']}")
    check_reply("edit-after-extract", result["reply"])
    require(
        after.get("batch_lot_number") == "CHG 260712A",
        "run-on 'CHG 260712Aand' split correctly",
        str(after.get("batch_lot_number")),
    )
    require(
        after.get("affected_quantity") == "50 kg (2 HDPE Drum)",
        "quantity updated",
        str(after.get("affected_quantity")),
    )


def check_bonus(state: dict[str, Any]) -> None:
    head("8. Bonus AI features (never executed before)")
    sections, risk = state["form_sections"], state["risk"]
    expectations = {
        "completeness": (T.completeness_check, ("score", "verdict", "summary")),
        "capa": (T.capa_recommendation, ("immediate_actions", "capa_required")),
        "root-cause": (T.root_cause_analysis, ("hypotheses", "most_likely")),
        "summary": (T.complaint_summary, ("headline", "regulatory_reportable")),
    }
    for name, (fn, keys) in expectations.items():
        try:
            started = time.time()
            payload = fn(sections, risk)
        except Exception as exc:  # noqa: BLE001
            record(FAIL, f"{name}", str(exc)[:200])
            continue
        if name == "root-cause":
            categories = {"Man", "Machine", "Material", "Method", "Measurement",
                          "Environment"}
            bad = [
                h.get("category")
                for h in payload.get("hypotheses") or []
                if h.get("category") not in categories
            ]
            require(
                not bad,
                "root-cause: category resolved to one fishbone value",
                f"got {bad}" if bad else "",
            )
        check_no_example_leak(name, json.dumps(payload))
        missing = [k for k in keys if k not in payload]
        require(
            not missing,
            f"{name} returns its contract keys",
            f"{time.time() - started:.1f}s"
            + (f" - missing {missing}" if missing else ""),
        )
        print(f"      {json.dumps(payload)[:300]}")


def check_full_graph() -> None:
    head("9. Full LangGraph invocation (router -> tool -> finalize)")
    state = G.initial_state("verify-graph")
    state["user_input"] = (
        "Apollo Pharmacy reported discolored capsules in Amoxicillin Capsules "
        "500 mg. Batch number AMX240602. Please log this complaint"
    )
    result = G.GRAPH.invoke(state)
    require(
        result.get("tool_used") == "log_complaint",
        "graph dispatched to log_complaint",
        str(result.get("tool_used")),
    )
    require(
        len(result.get("messages") or []) == 2,
        "transcript got the human + AI turn",
        str(len(result.get("messages") or [])),
    )
    require(
        bool(flatten(result["form_sections"]).get("batch_lot_number")),
        "form populated through the graph",
    )


# --- main --------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", action="store_true", help="model probe only")
    parser.add_argument("--no-bonus", action="store_true", help="skip bonus features")
    args = parser.parse_args()

    if not settings.llm_enabled:
        print(
            "GROQ_API_KEY is not set.\n\n"
            "  1. Create a key at https://console.groq.com/keys\n"
            "  2. cp backend/.env.example backend/.env\n"
            "  3. Put the key in GROQ_API_KEY=\n"
        )
        return 2

    print(f"key: ...{settings.groq_api_key[-4:]}   db: {settings.database_url}")
    llm.reset_model_cache()

    if not probe_models():
        print("\nModel probe failed - fix the chain before running the rest.")
        return 1
    if args.probe:
        return summarize()

    check_json_mode()
    check_router()
    logged = check_log_complaint()
    check_edit_complaint(logged)
    extracted = check_extract_document()
    if extracted:
        check_edit_after_extract(extracted)
        if not args.no_bonus:
            check_bonus(extracted)
    check_full_graph()
    return summarize()


def summarize() -> int:
    counts = {PASS: 0, FAIL: 0, WARN: 0}
    for status, _, _ in results:
        counts[status] += 1
    head("Summary")
    print(f"  {counts[PASS]} passed, {counts[WARN]} warnings, {counts[FAIL]} failed")
    print(f"  primary served by: {llm.active_model('primary')}")
    print(f"  router  served by: {llm.active_model('router')}")
    if counts[FAIL]:
        print("\n  FAILURES:")
        for status, name, detail in results:
            if status == FAIL:
                print(f"    - {name}: {detail}")
    if counts[WARN]:
        print("\n  WARNINGS (model wording/inference differs from the demo):")
        for status, name, detail in results:
            if status == WARN:
                print(f"    - {name}: {detail}")
    return 1 if counts[FAIL] else 0


if __name__ == "__main__":
    raise SystemExit(main())
