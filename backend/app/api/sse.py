"""Server-Sent Events helpers.

Both the chat and upload endpoints stream, and both are POSTs, so the frontend
reads them with `fetch` + a ReadableStream rather than `EventSource` (which is
GET-only).
"""

from __future__ import annotations

import json
from typing import Any

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",  # stop nginx buffering the stream
}


def event(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def status_event(label: str, progress: float, *, kind: str = "progress") -> str:
    return event(
        {
            "type": "status",
            "kind": kind,
            "label": label,
            "progress": round(max(0.0, min(1.0, progress)), 3),
        }
    )


def error_event(message: str) -> str:
    return event({"type": "error", "message": message})


def done_event() -> str:
    return event({"type": "done"})
