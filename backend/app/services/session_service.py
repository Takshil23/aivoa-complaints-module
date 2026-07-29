"""Session + complaint persistence, and the bridge into the LangGraph agent."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.agent.graph import GRAPH
from app.db.models import ChatMessage, Complaint, Session
from app.services.form_schema import (
    STATUS_COMMITTED,
    STATUS_PENDING,
    empty_schema,
    flatten,
)

logger = logging.getLogger(__name__)

GREETING = (
    "Ready to process new complaints. You can paste the raw email from the "
    "customer, or upload a PDF of the complaint report. I will extract the data "
    "and run the initial risk assessment."
)


# --- sessions -----------------------------------------------------------------

def get_or_create_session(db: OrmSession, session_id: str | None) -> Session:
    if session_id:
        found = db.get(Session, session_id)
        if found:
            return found

    record = Session(
        form_sections=empty_schema(),
        risk={},
        status=STATUS_PENDING,
    )
    if session_id:
        record.id = session_id
    db.add(record)
    db.flush()
    db.add(
        ChatMessage(
            session_id=record.id,
            role="assistant",
            kind="text",
            content=GREETING,
            meta={"icon": "spark"},
        )
    )
    db.commit()
    db.refresh(record)
    logger.info("created session %s", record.id)
    return record


def serialize_session(record: Session, messages: list[ChatMessage]) -> dict[str, Any]:
    return {
        "sessionId": record.id,
        "formSections": record.form_sections or [],
        "risk": record.risk or {},
        "status": record.status,
        "messages": [serialize_message(m) for m in messages],
    }


def serialize_message(message: ChatMessage) -> dict[str, Any]:
    return {
        "id": message.id,
        "role": message.role,
        "kind": message.kind,
        "content": message.content,
        "meta": message.meta or {},
        "createdAt": (message.created_at or datetime.now(timezone.utc)).isoformat(),
    }


def load_messages(db: OrmSession, session_id: str) -> list[ChatMessage]:
    return list(
        db.scalars(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.id)
        )
    )


def add_message(
    db: OrmSession,
    session_id: str,
    role: str,
    content: str,
    *,
    kind: str = "text",
    meta: dict | None = None,
) -> ChatMessage:
    message = ChatMessage(
        session_id=session_id,
        role=role,
        kind=kind,
        content=content,
        meta=meta or {},
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


# --- agent invocation ---------------------------------------------------------

def run_agent(
    db: OrmSession,
    record: Session,
    *,
    user_input: str = "",
    document_text: str = "",
    filename: str = "",
) -> dict[str, Any]:
    """Invoke the graph for one turn and persist the resulting state."""
    state: dict[str, Any] = {
        "session_id": record.id,
        "form_sections": record.form_sections or empty_schema(),
        "risk": record.risk or {},
        "status": record.status,
        "user_input": user_input,
        "document_text": document_text,
        "filename": filename,
    }

    result = GRAPH.invoke(state)

    changed = False
    if result.get("form_sections") is not None:
        record.form_sections = result["form_sections"]
        changed = True
    if result.get("risk"):
        record.risk = result["risk"]
        changed = True
    if result.get("status"):
        record.status = result["status"]
        changed = True
    if changed:
        db.add(record)
        db.commit()
        db.refresh(record)

    return {
        "reply": result.get("reply") or "",
        "toolUsed": result.get("tool_used") or result.get("route") or "",
        "patch": result.get("patch") or {},
        "formSections": record.form_sections or [],
        "risk": record.risk or {},
        "status": record.status,
    }


# --- ledger -------------------------------------------------------------------

def next_complaint_number(db: OrmSession) -> str:
    """CC-<year>-<5-digit sequence>, matching the CC-2026-00154 style in the demo PDF."""
    year = datetime.now(timezone.utc).year
    prefix = f"CC-{year}-"
    count = db.scalar(
        select(func.count(Complaint.id)).where(
            Complaint.complaint_number.like(f"{prefix}%")
        )
    )
    return f"{prefix}{(count or 0) + 1:05d}"


def commit_complaint(db: OrmSession, record: Session) -> Complaint:
    values = flatten(record.form_sections or [])
    risk = record.risk or {}

    complaint = Complaint(
        complaint_number=next_complaint_number(db),
        session_id=record.id,
        severity=risk.get("severity", ""),
        suggested_next_action=risk.get("suggested_next_action", ""),
        initial_risk_assessment=risk.get("initial_risk_assessment", ""),
        form_snapshot=record.form_sections or [],
    )
    for field in Complaint.LEDGER_FIELDS:
        setattr(complaint, field, values.get(field, "") or "")

    db.add(complaint)

    # Reset the session so the officer can log the next complaint, exactly like a
    # real intake queue.
    record.form_sections = empty_schema()
    record.risk = {}
    record.status = STATUS_PENDING
    db.add(record)
    db.commit()
    db.refresh(complaint)
    logger.info("committed complaint %s", complaint.complaint_number)
    return complaint


def serialize_complaint(complaint: Complaint) -> dict[str, Any]:
    return {
        "id": complaint.id,
        "complaintNumber": complaint.complaint_number,
        "customerName": complaint.customer_name,
        "productName": complaint.product_name,
        "batchLotNumber": complaint.batch_lot_number,
        "complaintCategory": complaint.complaint_category,
        "severity": complaint.severity,
        "suggestedNextAction": complaint.suggested_next_action,
        "initialRiskAssessment": complaint.initial_risk_assessment,
        "createdAt": (
            complaint.created_at or datetime.now(timezone.utc)
        ).isoformat(),
    }


def list_complaints(db: OrmSession, limit: int = 50) -> list[Complaint]:
    return list(
        db.scalars(
            select(Complaint).order_by(Complaint.created_at.desc()).limit(limit)
        )
    )


def find_duplicates(db: OrmSession, record: Session) -> list[Complaint]:
    """Bonus feature: same batch already in the ledger."""
    values = flatten(record.form_sections or [])
    batch = (values.get("batch_lot_number") or "").strip()
    if not batch or batch.lower() in {"", "not provided"}:
        return []
    normalized = batch.replace(" ", "").lower()
    candidates = db.scalars(select(Complaint).limit(500))
    return [
        c
        for c in candidates
        if c.batch_lot_number
        and c.batch_lot_number.replace(" ", "").lower() == normalized
    ]
