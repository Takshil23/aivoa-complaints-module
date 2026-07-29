"""Chat endpoint — drives the log_complaint / edit_complaint / answer tools."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api import sse
from app.db.session import db_session
from app.services import session_service as svc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    session_id: str | None = Field(default=None, alias="sessionId")
    message: str

    model_config = {"populate_by_name": True}


@router.post("/stream")
async def chat_stream(payload: ChatRequest) -> StreamingResponse:
    message = (payload.message or "").strip()
    if not message:
        raise HTTPException(status_code=422, detail="message must not be empty")

    async def generate() -> AsyncIterator[str]:
        try:
            # Persist the user's message first so it renders immediately.
            with db_session() as db:
                record = svc.get_or_create_session(db, payload.session_id)
                session_id = record.id
                user_message = svc.add_message(db, session_id, "user", message)

            yield sse.event(
                {
                    "type": "user_message",
                    "sessionId": session_id,
                    "message": svc.serialize_message(user_message),
                }
            )
            yield sse.status_event("Analysing complaint...", 0.25)

            def work() -> dict:
                with db_session() as db:
                    record = svc.get_or_create_session(db, session_id)
                    return svc.run_agent(db, record, user_input=message)

            task = asyncio.create_task(asyncio.to_thread(work))

            # Keep the progress indicator alive while the model works.
            ticks = [
                (0.45, "Extracting structured fields..."),
                (0.65, "Mapping batch information..."),
                (0.85, "Generating risk assessment..."),
            ]
            index = 0
            while not task.done():
                await asyncio.sleep(0.9)
                if index < len(ticks) and not task.done():
                    progress, label = ticks[index]
                    yield sse.status_event(label, progress)
                    index += 1

            result = await task

            with db_session() as db:
                assistant_message = svc.add_message(
                    db,
                    session_id,
                    "assistant",
                    result["reply"],
                    meta={
                        "icon": "check",
                        "toolUsed": result["toolUsed"],
                        "patch": result["patch"],
                    },
                )
                assistant_payload = svc.serialize_message(assistant_message)

            yield sse.event(
                {
                    "type": "result",
                    "sessionId": session_id,
                    "message": assistant_payload,
                    "formSections": result["formSections"],
                    "risk": result["risk"],
                    "status": result["status"],
                    "toolUsed": result["toolUsed"],
                    "patch": result["patch"],
                }
            )
            yield sse.done_event()

        except Exception as exc:  # noqa: BLE001
            logger.exception("chat_stream failed")
            yield sse.error_event(str(exc) or "The copilot hit an unexpected error.")
            yield sse.done_event()

    return StreamingResponse(
        generate(), media_type="text/event-stream", headers=sse.SSE_HEADERS
    )
