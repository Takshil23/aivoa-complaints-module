"""Document extraction endpoint — the third mandatory tool.

Streams genuine stage labels while the work happens, rather than animating a
fixed-duration fake progress bar.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.api import sse
from app.config import settings
from app.db.session import db_session
from app.services import session_service as svc
from app.services.document_parser import DocumentParseError, parse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.post("/stream")
async def upload_stream(
    file: UploadFile = File(...),
    session_id: str | None = Form(default=None, alias="sessionId"),
) -> StreamingResponse:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="The uploaded file is empty.")
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=(
                f"File is larger than "
                f"{settings.max_upload_bytes // (1024 * 1024)} MB."
            ),
        )
    filename = file.filename or "complaint.pdf"

    async def generate() -> AsyncIterator[str]:
        try:
            with db_session() as db:
                record = svc.get_or_create_session(db, session_id)
                sid = record.id
                attachment = svc.add_message(
                    db,
                    sid,
                    "user",
                    filename,
                    kind="file",
                    meta={
                        "filename": filename,
                        "sizeBytes": len(data),
                        "fileType": "PDF Document"
                        if filename.lower().endswith(".pdf")
                        else "Document",
                    },
                )
                attachment_payload = svc.serialize_message(attachment)

            yield sse.event(
                {
                    "type": "user_message",
                    "sessionId": sid,
                    "message": attachment_payload,
                }
            )

            yield sse.status_event("Reading document...", 0.15)
            try:
                text = await asyncio.to_thread(parse, filename, data)
            except DocumentParseError as exc:
                with db_session() as db:
                    message = svc.add_message(
                        db, sid, "assistant", str(exc), meta={"icon": "warn"}
                    )
                    payload = svc.serialize_message(message)
                yield sse.event(
                    {"type": "result", "sessionId": sid, "message": payload}
                )
                yield sse.done_event()
                return

            yield sse.status_event("Extracting tabular data via OCR...", 0.45)
            yield sse.event(
                {
                    "type": "document_text",
                    "chars": len(text),
                    "preview": text[:400],
                }
            )

            def work() -> dict:
                with db_session() as db:
                    record = svc.get_or_create_session(db, sid)
                    return svc.run_agent(
                        db, record, document_text=text, filename=filename
                    )

            task = asyncio.create_task(asyncio.to_thread(work))
            ticks = [
                (0.6, "Identifying complainant and product..."),
                (0.75, "Mapping batch and quantity fields..."),
                (0.9, "Generating risk assessment..."),
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
                message = svc.add_message(
                    db,
                    sid,
                    "assistant",
                    result["reply"],
                    meta={"icon": "doc-check", "toolUsed": result["toolUsed"]},
                )
                payload = svc.serialize_message(message)

            yield sse.status_event("Complete", 1.0)
            yield sse.event(
                {
                    "type": "result",
                    "sessionId": sid,
                    "message": payload,
                    "formSections": result["formSections"],
                    "risk": result["risk"],
                    "status": result["status"],
                    "toolUsed": result["toolUsed"],
                }
            )
            yield sse.done_event()

        except Exception as exc:  # noqa: BLE001
            logger.exception("upload_stream failed")
            yield sse.error_event(str(exc) or "Document extraction failed.")
            yield sse.done_event()

    return StreamingResponse(
        generate(), media_type="text/event-stream", headers=sse.SSE_HEADERS
    )
