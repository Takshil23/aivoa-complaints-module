"""Drive the whole demo through the HTTP API, exactly as the browser does.

`verify_llm.py` calls the tools in-process, so it never touches FastAPI, the SSE
framing, or persistence. This does: it replays the four demo turns over
POST + Server-Sent Events, then exercises the five bonus features, the ledger
commit and duplicate detection.

Start the server first, then:

    cd backend
    .venv\\Scripts\\python.exe -m uvicorn app.main:app --port 8000
    .venv\\Scripts\\python.exe scripts/verify_api.py [--base http://127.0.0.1:8000]

Every assertion mirrors something the React client depends on, so a failure here
means a broken screen, not just a broken payload.

This writes real complaints to whatever database the server is using — it has to,
since it commits to the ledger and then checks duplicate detection against it. To
keep the demo ledger clean, point the server at a scratch DB for the run:

    set DATABASE_URL=sqlite+pysqlite:///./verify.db
    .venv\\Scripts\\python.exe -m uvicorn app.main:app --port 8001
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Iterator

import httpx

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT.parent / "samples"

PASS, FAIL, WARN = "PASS", "FAIL", "WARN"
results: list[tuple[str, str, str]] = []


def record(status: str, name: str, detail: str = "") -> None:
    results.append((status, name, detail))
    mark = {PASS: "[ok]  ", FAIL: "[FAIL]", WARN: "[warn]"}[status]
    print(f"{mark} {name}" + (f" - {detail}" if detail else ""))


def require(ok: bool, label: str, detail: str = "") -> bool:
    record(PASS if ok else FAIL, label, detail)
    return ok


def head(title: str) -> None:
    print(f"\n{'=' * 74}\n{title}\n{'=' * 74}")


def frames(response: httpx.Response) -> Iterator[dict[str, Any]]:
    """Parse an SSE body into events.

    Deliberately buffers and splits on the blank-line frame separator rather than
    reading line by line: a JSON payload routinely spans several network chunks,
    which is the bug the frontend parser was written to avoid.
    """
    buffer = ""
    for chunk in response.iter_text():
        buffer += chunk
        while "\n\n" in buffer:
            raw, buffer = buffer.split("\n\n", 1)
            for line in raw.splitlines():
                if line.startswith("data: "):
                    yield json.loads(line[6:])


def stream(client: httpx.Client, url: str, **kwargs: Any) -> list[dict[str, Any]]:
    with client.stream("POST", url, timeout=180, **kwargs) as response:
        response.raise_for_status()
        ctype = response.headers.get("content-type", "")
        require(
            ctype.startswith("text/event-stream"),
            f"{url}: content-type is an event stream",
            ctype,
        )
        return list(frames(response))


def result_of(events: list[dict[str, Any]], label: str) -> dict[str, Any]:
    kinds = [e.get("type") for e in events]
    require("done" in kinds, f"{label}: stream terminated with a done event")
    errors = [e for e in events if e.get("type") == "error"]
    require(not errors, f"{label}: no error frame", json.dumps(errors)[:200])
    statuses = [e for e in events if e.get("type") == "status"]
    require(bool(statuses), f"{label}: progress stages streamed", f"{len(statuses)} stages")
    monotonic = all(
        a["progress"] <= b["progress"] for a, b in zip(statuses, statuses[1:])
    )
    require(monotonic, f"{label}: progress never goes backwards")

    final = [e for e in events if e.get("type") == "result"]
    require(bool(final), f"{label}: result frame present")
    return final[-1] if final else {}


def field_map(form_sections: list[dict[str, Any]]) -> dict[str, str]:
    return {
        f["key"]: f.get("value", "")
        for section in form_sections
        for f in section["fields"]
    }


def label_of(form_sections: list[dict[str, Any]], key: str) -> str:
    for section in form_sections:
        for f in section["fields"]:
            if f["key"] == key:
                return f.get("label", "")
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    base = args.base.rstrip("/")

    client = httpx.Client(base_url=base, timeout=60)

    head("1. Session bootstrap")
    try:
        session = client.post("/api/session", json={}).raise_for_status().json()
    except Exception as exc:  # noqa: BLE001
        print(f"Cannot reach {base}: {exc}\n\nStart the server first:")
        print("  .venv\\Scripts\\python.exe -m uvicorn app.main:app --port 8000")
        return 2

    sid = session["sessionId"]
    print(f"  session {sid}")
    print(f"  models  {json.dumps(session.get('models', {}))}")
    require(session.get("llmEnabled") is True, "LLM is enabled server-side")
    require(bool(session["formSections"]), "empty form schema returned")
    require(
        len(session["messages"]) == 1
        and session["messages"][0]["role"] == "assistant",
        "greeting message present",
    )
    require(
        session["status"] == "pending_triage",
        "status starts at pending_triage",
        session["status"],
    )
    active = (session.get("models") or {}).get("activePrimary")
    require(
        bool(active),
        "session reports the model actually serving",
        f"requested {(session.get('models') or {}).get('primary')}, active {active}",
    )

    head("2. Turn 1 - log complaint over SSE")
    events = stream(
        client,
        "/api/chat/stream",
        json={
            "sessionId": sid,
            "message": (
                "Apollo Pharmacy reported discolored capsules in Amoxicillin "
                "Capsules 500 mg. Batch number AMX240602. Manufacturing date "
                "March 2026. Expiry date February 2028. Please log this complaint"
            ),
        },
    )
    require(
        any(e.get("type") == "user_message" for e in events),
        "user message echoed before the model runs",
    )
    turn1 = result_of(events, "log")
    fields = field_map(turn1["formSections"])
    print(f"  reply: {turn1['message']['content']}")
    require(turn1["toolUsed"] == "log_complaint", "routed to log_complaint",
            turn1.get("toolUsed", ""))
    require(fields.get("batch_lot_number") == "AMX240602", "batch on the form",
            fields.get("batch_lot_number", ""))
    require(turn1["status"] == "ready_to_commit", "status flipped to ready_to_commit",
            turn1["status"])
    require(bool(turn1["risk"].get("severity")), "risk assessment rendered",
            turn1["risk"].get("severity", ""))

    head("3. Turn 2 - edit over SSE (sparse patch)")
    events = stream(
        client,
        "/api/chat/stream",
        json={
            "sessionId": sid,
            "message": (
                "ah sorry the batch number is BMX240602 and affected quantity "
                "is 48 capcules"
            ),
        },
    )
    turn2 = result_of(events, "edit")
    after = field_map(turn2["formSections"])
    print(f"  reply: {turn2['message']['content']}")
    require(turn2["toolUsed"] == "edit_complaint", "routed to edit_complaint",
            turn2.get("toolUsed", ""))
    require(
        set(turn2["patch"]) <= {"batch_lot_number", "affected_quantity"},
        "patch names only the two fields the officer changed",
        ", ".join(sorted(turn2["patch"])),
    )
    require(after.get("batch_lot_number") == "BMX240602", "batch updated",
            after.get("batch_lot_number", ""))
    require(
        after.get("product_name") == fields.get("product_name"),
        "untouched fields survived the edit",
    )
    require(
        turn2["message"]["meta"].get("patch") == turn2["patch"],
        "patch echoed on the message so the UI can highlight the changed rows",
    )

    head("4. Turn 3 - PDF upload over SSE")
    pdf = SAMPLES / "Fictional_Pharma_Customer_Complaint_API.pdf"
    started = time.time()
    with pdf.open("rb") as handle:
        events = stream(
            client,
            "/api/documents/stream",
            files={"file": (pdf.name, handle, "application/pdf")},
            data={"sessionId": sid},
        )
    turn3 = result_of(events, "upload")
    extracted = field_map(turn3["formSections"])
    print(f"  {time.time() - started:.1f}s")
    print(f"  reply: {turn3['message']['content']}")
    attachment = [
        e for e in events
        if e.get("type") == "user_message" and e["message"]["kind"] == "file"
    ]
    require(bool(attachment), "attachment card frame emitted for the UI")
    require(
        any(e.get("type") == "document_text" for e in events),
        "document_text preview frame emitted",
    )
    stages = [e["label"] for e in events if e.get("type") == "status"]
    require(
        "Extracting tabular data via OCR..." in stages,
        "demo's OCR stage label streamed",
        " | ".join(stages),
    )
    require(
        extracted.get("product_name") == "Metformin Hydrochloride API",
        "API product extracted", extracted.get("product_name", ""),
    )
    require(
        extracted.get("customer_name") == "ABC Formulations Ltd.",
        "complainant, not the receiving manufacturer",
        extracted.get("customer_name", ""),
    )
    require(
        label_of(turn3["formSections"], "product_strength") == "Product Strength/Grade",
        "form schema re-shaped for an API",
        label_of(turn3["formSections"], "product_strength"),
    )
    require(
        turn3["risk"].get("severity") == "Critical",
        "severity escalated for foreign matter in an API",
        turn3["risk"].get("severity", ""),
    )
    inferred = [
        f["key"]
        for section in turn3["formSections"]
        for f in section["fields"]
        if f.get("inferred")
    ]
    record(
        PASS if inferred else WARN,
        "AI INFERRED badges carried to the client",
        ", ".join(inferred) or "none flagged",
    )

    head("5. Turn 4 - edit after extraction")
    events = stream(
        client,
        "/api/chat/stream",
        json={
            "sessionId": sid,
            "message": (
                "ah sorry the batch number is CHG 260712Aand affected quantity "
                "is 50 kg (2 HDPE Drum)"
            ),
        },
    )
    turn4 = result_of(events, "edit-after-extract")
    final = field_map(turn4["formSections"])
    print(f"  reply: {turn4['message']['content']}")
    require(
        final.get("batch_lot_number") == "CHG 260712A",
        "run-on batch split before it reached the form",
        final.get("batch_lot_number", ""),
    )
    require(
        final.get("affected_quantity") == "50 kg (2 HDPE Drum)",
        "quantity updated",
        final.get("affected_quantity", ""),
    )
    require(
        final.get("product_name") == "Metformin Hydrochloride API",
        "extraction survived the edit",
    )

    head("6. Bonus AI features over HTTP")
    for feature in ("completeness", "capa", "root-cause", "summary", "duplicates"):
        started = time.time()
        response = client.post(f"/api/ai/{feature}", json={"sessionId": sid},
                               timeout=120)
        if response.status_code == 429:
            # Free-tier quota, not a defect — but assert it degraded cleanly.
            detail = response.json().get("detail", "")
            record(WARN, f"/api/ai/{feature}", f"rate limited: {detail}")
            require(
                "org_" not in detail and "{" not in detail,
                f"/api/ai/{feature}: rate limit shown as a clean sentence",
                detail[:120],
            )
            continue
        if response.status_code != 200:
            record(FAIL, f"/api/ai/{feature}",
                   f"HTTP {response.status_code}: {response.text[:160]}")
            continue
        payload = response.json()["result"]
        require(bool(payload), f"/api/ai/{feature} returned a result",
                f"{time.time() - started:.1f}s")
        print(f"      {json.dumps(payload)[:220]}")

    head("7. Ledger commit + duplicate detection")
    committed = client.post("/api/complaints/commit", json={"sessionId": sid})
    if committed.status_code != 200:
        record(FAIL, "commit to ledger",
               f"HTTP {committed.status_code}: {committed.text[:200]}")
    else:
        body = committed.json()
        number = body["complaint"]["complaintNumber"]
        require(number.startswith("CC-"), "complaint number issued", number)
        require(
            body["complaint"]["severity"] == "Critical",
            "risk assessment persisted to the ledger",
            body["complaint"]["severity"],
        )
        require(
            body["session"]["status"] == "pending_triage",
            "form reset for the next complaint",
            body["session"]["status"],
        )
        ledger = client.get("/api/complaints").json()["complaints"]
        require(
            any(c["complaintNumber"] == number for c in ledger),
            "complaint readable back from the ledger",
        )

        # Re-log the same batch, then the duplicate check must see the committed one.
        stream(
            client,
            "/api/chat/stream",
            json={
                "sessionId": sid,
                "message": (
                    "ABC Formulations Ltd. reported foreign particles in "
                    "Metformin Hydrochloride API, batch CHG 260712A, 25 kg drum."
                ),
            },
        )
        dupes = client.post("/api/ai/duplicates", json={"sessionId": sid}).json()
        require(
            dupes["result"]["count"] >= 1,
            "duplicate detection finds the committed batch",
            dupes["result"]["summary"],
        )

    head("8. Guard rails")
    empty = client.post("/api/chat/stream", json={"sessionId": sid, "message": "  "})
    require(empty.status_code == 422, "empty message rejected", str(empty.status_code))
    unknown = client.post("/api/ai/does-not-exist", json={"sessionId": sid})
    require(unknown.status_code == 404, "unknown AI feature is a 404",
            str(unknown.status_code))
    client.post("/api/session/reset", json={"sessionId": sid})
    fresh = client.post("/api/session", json={"sessionId": sid}).json()
    require(
        len(fresh["messages"]) == 1 and fresh["status"] == "pending_triage",
        "reset clears the transcript and the form",
    )
    blocked = client.post("/api/complaints/commit", json={"sessionId": sid})
    require(
        blocked.status_code == 422,
        "an empty form cannot be committed to the QMS ledger",
        str(blocked.status_code),
    )

    counts = {PASS: 0, FAIL: 0, WARN: 0}
    for status, _, _ in results:
        counts[status] += 1
    head("Summary")
    print(f"  {counts[PASS]} passed, {counts[WARN]} warnings, {counts[FAIL]} failed")
    if counts[FAIL]:
        print("\n  FAILURES:")
        for status, name, detail in results:
            if status == FAIL:
                print(f"    - {name}: {detail}")
    return 1 if counts[FAIL] else 0


if __name__ == "__main__":
    raise SystemExit(main())
