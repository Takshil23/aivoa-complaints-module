"""API-level tests: session lifecycle, streaming, commit guards, ledger."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app

PROMPT = (
    "Apollo Pharmacy reported discolored capsules in Amoxicillin Capsules 500 mg. "
    "Batch number AMX240602. Manufacturing date March 2026. Expiry date "
    "February 2028. Please log this complaint"
)


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def sse_events(response) -> list[dict]:
    events = []
    for line in response.iter_lines():
        if isinstance(line, bytes):
            line = line.decode()
        if line.startswith("data:"):
            events.append(json.loads(line[5:].strip()))
    return events


def result_of(events: list[dict]) -> dict:
    return next(e for e in events if e["type"] == "result")


def values_of(event: dict) -> dict:
    return {f["key"]: f["value"] for s in event["formSections"] for f in s["fields"]}


def new_session(client) -> str:
    return client.post("/api/session", json={}).json()["sessionId"]


class TestHealth:
    def test_reports_configured_models(self, client):
        body = client.get("/api/health").json()
        assert body["status"] == "ok"
        assert body["primaryModel"] == "gemma2-9b-it"
        assert body["routerModel"] == "llama-3.3-70b-versatile"


class TestSession:
    def test_opens_with_empty_schema_and_greeting(self, client):
        body = client.post("/api/session", json={}).json()
        assert body["status"] == "pending_triage"
        assert [s["title"] for s in body["formSections"]] == [
            "PRODUCT & BATCH IDENTIFICATION",
            "FACILITY & MATERIAL IMPACT",
            "DEFECT ANALYSIS",
        ]
        assert len(body["messages"]) == 1
        assert body["messages"][0]["role"] == "assistant"

    def test_resumes_the_same_session(self, client):
        first = new_session(client)
        again = client.post("/api/session", json={"sessionId": first}).json()
        assert again["sessionId"] == first

    def test_reset_clears_the_form(self, client):
        sid = new_session(client)
        with client.stream(
            "POST", "/api/chat/stream", json={"sessionId": sid, "message": PROMPT}
        ) as r:
            sse_events(r)

        body = client.post("/api/session/reset", json={"sessionId": sid}).json()
        assert body["status"] == "pending_triage"
        assert len(body["formSections"]) == 3
        assert len(body["messages"]) == 1


class TestChatStream:
    def test_emits_user_message_status_and_result(self, client):
        sid = new_session(client)
        with client.stream(
            "POST", "/api/chat/stream", json={"sessionId": sid, "message": PROMPT}
        ) as r:
            assert r.status_code == 200
            events = sse_events(r)

        kinds = [e["type"] for e in events]
        assert "user_message" in kinds
        assert "status" in kinds
        assert "result" in kinds
        assert kinds[-1] == "done"

        result = result_of(events)
        assert result["status"] == "ready_to_commit"
        assert values_of(result)["batch_lot_number"] == "AMX240602"

    def test_rejects_an_empty_message(self, client):
        sid = new_session(client)
        r = client.post("/api/chat/stream", json={"sessionId": sid, "message": "   "})
        assert r.status_code == 422

    def test_transcript_persists_across_requests(self, client):
        sid = new_session(client)
        with client.stream(
            "POST", "/api/chat/stream", json={"sessionId": sid, "message": PROMPT}
        ) as r:
            sse_events(r)

        body = client.post("/api/session", json={"sessionId": sid}).json()
        roles = [m["role"] for m in body["messages"]]
        assert roles == ["assistant", "user", "assistant"]


class TestDocumentStream:
    def test_extracts_a_text_document(self, client):
        sid = new_session(client)
        doc = (
            "ZENITH LIFE SCIENCES LIMITED\n"
            "Complaint No: CC-2026-00154\n"
            "Complainant: ABC Formulations Ltd.\n"
            "Product Name: Metformin Hydrochloride API\n"
            "Grade: IP/BP\n"
            "Batch / Lot No.: MFH260712A\n"
            "Quantity Affected: 25 kg (1 HDPE Drum)\n"
            "Manufacturing Date: 25 June 2026\n"
            "Dark foreign particles found inside one sealed HDPE drum.\n"
        )
        with client.stream(
            "POST",
            "/api/documents/stream",
            files={"file": ("complaint.txt", doc, "text/plain")},
            data={"sessionId": sid},
        ) as r:
            assert r.status_code == 200
            events = sse_events(r)

        assert any(
            e["type"] == "status" and "OCR" in e["label"] for e in events
        ), "the OCR stage label should be streamed"

        result = result_of(events)
        assert result["toolUsed"] == "extract_document"
        assert values_of(result)["batch_lot_number"] == "MFH260712A"
        assert result["risk"]["severity"] == "Critical"

    def test_attachment_renders_as_a_file_message(self, client):
        sid = new_session(client)
        with client.stream(
            "POST",
            "/api/documents/stream",
            files={"file": ("report.txt", "Batch number ABC123456", "text/plain")},
            data={"sessionId": sid},
        ) as r:
            events = sse_events(r)

        attachment = next(e for e in events if e["type"] == "user_message")["message"]
        assert attachment["kind"] == "file"
        assert attachment["meta"]["filename"] == "report.txt"

    def test_rejects_an_empty_file(self, client):
        sid = new_session(client)
        r = client.post(
            "/api/documents/stream",
            files={"file": ("empty.txt", b"", "text/plain")},
            data={"sessionId": sid},
        )
        assert r.status_code == 422

    def test_reports_an_unreadable_pdf_honestly(self, client):
        sid = new_session(client)
        with client.stream(
            "POST",
            "/api/documents/stream",
            files={"file": ("scan.pdf", b"%PDF-1.4 not really a pdf", "application/pdf")},
            data={"sessionId": sid},
        ) as r:
            events = sse_events(r)
        result = result_of(events)
        assert "could not read" in result["message"]["content"].lower()


class TestCommit:
    def test_blocks_commit_on_an_empty_form(self, client):
        sid = new_session(client)
        r = client.post("/api/complaints/commit", json={"sessionId": sid})
        assert r.status_code == 422
        assert "missing required field" in r.json()["detail"].lower()

    def test_commits_and_resets(self, client):
        sid = new_session(client)
        with client.stream(
            "POST", "/api/chat/stream", json={"sessionId": sid, "message": PROMPT}
        ) as r:
            sse_events(r)

        body = client.post("/api/complaints/commit", json={"sessionId": sid}).json()
        complaint = body["complaint"]
        assert complaint["complaintNumber"].startswith("CC-")
        assert complaint["batchLotNumber"] == "AMX240602"
        # the session is cleared so the officer can log the next complaint
        assert body["session"]["status"] == "pending_triage"
        assert len(body["session"]["formSections"]) == 3

    def test_ledger_lists_committed_complaints(self, client):
        sid = new_session(client)
        with client.stream(
            "POST", "/api/chat/stream", json={"sessionId": sid, "message": PROMPT}
        ) as r:
            sse_events(r)
        client.post("/api/complaints/commit", json={"sessionId": sid})

        complaints = client.get("/api/complaints").json()["complaints"]
        assert any(c["batchLotNumber"] == "AMX240602" for c in complaints)


class TestBonusFeatures:
    def test_duplicate_detection_finds_a_shared_batch(self, client):
        sid = new_session(client)
        with client.stream(
            "POST", "/api/chat/stream", json={"sessionId": sid, "message": PROMPT}
        ) as r:
            sse_events(r)
        client.post("/api/complaints/commit", json={"sessionId": sid})

        # log the same batch again
        with client.stream(
            "POST", "/api/chat/stream", json={"sessionId": sid, "message": PROMPT}
        ) as r:
            sse_events(r)

        body = client.post("/api/ai/duplicates", json={"sessionId": sid}).json()
        assert body["result"]["count"] >= 1

    def test_unknown_feature_is_404(self, client):
        sid = new_session(client)
        r = client.post("/api/ai/not-a-feature", json={"sessionId": sid})
        assert r.status_code == 404

    def test_llm_features_need_a_complaint(self, client):
        sid = new_session(client)
        r = client.post("/api/ai/capa", json={"sessionId": sid})
        assert r.status_code == 422
