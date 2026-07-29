"""Session state, ledger commit, and the bonus AI feature endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as OrmSession

from app.agent import tools as T
from app.agent.llm import LLMUnavailable
from app.config import settings
from app.db.session import get_db
from app.services import session_service as svc
from app.services.form_schema import flatten

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["complaints"])


class SessionQuery(BaseModel):
    session_id: str | None = Field(default=None, alias="sessionId")
    model_config = {"populate_by_name": True}


@router.post("/session")
def open_session(payload: SessionQuery, db: OrmSession = Depends(get_db)) -> dict:
    """Create or resume a session. Returns the full state the UI needs to render."""
    record = svc.get_or_create_session(db, payload.session_id)
    messages = svc.load_messages(db, record.id)
    data = svc.serialize_session(record, messages)
    data["llmEnabled"] = settings.llm_enabled
    data["models"] = {
        "primary": settings.primary_model,
        "router": settings.router_model,
    }
    return data


@router.post("/session/reset")
def reset_session(payload: SessionQuery, db: OrmSession = Depends(get_db)) -> dict:
    """Clear the form and transcript, keeping the same session id."""
    from app.services.form_schema import STATUS_PENDING, empty_schema

    record = svc.get_or_create_session(db, payload.session_id)
    for message in svc.load_messages(db, record.id):
        db.delete(message)
    record.form_sections = empty_schema()
    record.risk = {}
    record.status = STATUS_PENDING
    db.add(record)
    db.commit()

    svc.add_message(
        db, record.id, "assistant", svc.GREETING, meta={"icon": "spark"}
    )
    db.refresh(record)
    return svc.serialize_session(record, svc.load_messages(db, record.id))


@router.post("/complaints/commit")
def commit(payload: SessionQuery, db: OrmSession = Depends(get_db)) -> dict:
    record = svc.get_or_create_session(db, payload.session_id)
    values = flatten(record.form_sections or [])

    blocking = [
        label
        for key, label in (
            ("product_name", "Product Name"),
            ("batch_lot_number", "Batch / Lot Number"),
            ("complaint_description", "Complaint Description"),
        )
        if not (values.get(key) or "").strip()
        or (values.get(key) or "").strip().lower() == "not provided"
    ]
    if blocking:
        raise HTTPException(
            status_code=422,
            detail=(
                "Cannot commit to the QMS ledger — missing required field(s): "
                + ", ".join(blocking)
            ),
        )

    complaint = svc.commit_complaint(db, record)
    db.refresh(record)
    return {
        "complaint": svc.serialize_complaint(complaint),
        "session": svc.serialize_session(record, svc.load_messages(db, record.id)),
    }


@router.get("/complaints")
def ledger(limit: int = 50, db: OrmSession = Depends(get_db)) -> dict:
    return {
        "complaints": [
            svc.serialize_complaint(c) for c in svc.list_complaints(db, limit)
        ]
    }


# --- Bonus AI features --------------------------------------------------------

_BONUS = {
    "completeness": T.completeness_check,
    "capa": T.capa_recommendation,
    "root-cause": T.root_cause_analysis,
    "summary": T.complaint_summary,
}


@router.post("/ai/{feature}")
def bonus_feature(
    feature: str, payload: SessionQuery, db: OrmSession = Depends(get_db)
) -> dict:
    record = svc.get_or_create_session(db, payload.session_id)

    if feature == "duplicates":
        matches = svc.find_duplicates(db, record)
        return {
            "feature": "duplicates",
            "result": {
                "count": len(matches),
                "matches": [svc.serialize_complaint(c) for c in matches],
                "summary": (
                    f"{len(matches)} existing complaint(s) share this batch number."
                    if matches
                    else "No existing complaint in the ledger shares this batch number."
                ),
            },
        }

    handler = _BONUS.get(feature)
    if not handler:
        raise HTTPException(status_code=404, detail=f"Unknown AI feature '{feature}'")

    if not flatten(record.form_sections or []).get("product_name"):
        raise HTTPException(
            status_code=422,
            detail="Log a complaint first — there is nothing to analyse yet.",
        )

    try:
        return {
            "feature": feature,
            "result": handler(record.form_sections, record.risk),
        }
    except LLMUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=502, detail=f"The model returned malformed output: {exc}"
        ) from exc
