"""AIVOA — AI-Powered Customer Complaint Management System (FastAPI entrypoint)."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agent import llm
from app.api import chat, complaints, documents
from app.config import settings
from app.db.session import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("aivoa")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    if settings.llm_enabled:
        # Settle the model chains now rather than on the officer's first message.
        # The assignment mandates gemma2-9b-it, which Groq decommissioned on
        # 2025-10-08, so this is where the substitution actually happens — and it
        # is logged loudly, because it is a deviation from the brief.
        resolved = await asyncio.to_thread(llm.resolve_chains)
        for role, requested in (
            ("primary", settings.primary_model),
            ("router", settings.router_model),
        ):
            serving = resolved.get(role)
            if serving and serving != requested:
                logger.warning(
                    "%s role: %s is unavailable on Groq — serving with %s instead",
                    role,
                    requested,
                    serving,
                )
            else:
                logger.info("%s role: %s", role, serving or requested)
    else:
        logger.warning(
            "GROQ_API_KEY is not set. Running on the deterministic fallback "
            "extractor: the app works, but without LLM reasoning. Add a key to "
            "backend/.env to enable the real agent."
        )
    yield


app = FastAPI(
    title="AIVOA Complaints Module",
    description=(
        "AI-powered Customer Complaint Management for pharmaceutical API & FDF "
        "manufacturing. LangGraph agent with three mandatory tools: log_complaint, "
        "edit_complaint, extract_document."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(documents.router)
app.include_router(complaints.router)


@app.get("/api/health", tags=["meta"])
def health() -> dict:
    return {
        "status": "ok",
        "llmEnabled": settings.llm_enabled,
        "primaryModel": settings.primary_model,
        "routerModel": settings.router_model,
        "activePrimaryModel": llm.active_model("primary"),
        "activeRouterModel": llm.active_model("router"),
        "database": settings.database_url.split("://", 1)[0],
    }
