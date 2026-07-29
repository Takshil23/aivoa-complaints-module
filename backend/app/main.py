"""AIVOA — AI-Powered Customer Complaint Management System (FastAPI entrypoint)."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
        logger.info(
            "Groq enabled — primary=%s router=%s",
            settings.primary_model,
            settings.router_model,
        )
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
        "database": settings.database_url.split("://", 1)[0],
    }
