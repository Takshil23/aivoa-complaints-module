"""The LangGraph agent.

    START
      │
      ▼
  ┌────────┐   document_text present?  ──yes──►  extract_document ──┐
  │ router │                                                        │
  └────────┘   ──log_complaint──►  log_complaint  ──────────────────┤
      │                                                             │
      ├────────  ──edit_complaint──►  edit_complaint  ──────────────┤
      │                                                             │
      └────────  ──answer_question──►  answer_question  ────────────┤
                                                                    ▼
                                                              ┌───────────┐
                                                              │ finalize  │ → END
                                                              └───────────┘

The router uses llama-3.3-70b-versatile with native tool calling (gemma2-9b-it has
no tool-calling support on Groq), and falls back to a deterministic heuristic if
tool calling is unavailable. Every tool node runs on the mandated gemma2-9b-it.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, START, StateGraph

from app.agent import tools as T
from app.agent.llm import LLMUnavailable, chat_call, tool_call
from app.agent.state import AgentState
from app.config import settings
from app.services.form_schema import (
    STATUS_PENDING,
    empty_schema,
    flatten,
)

logger = logging.getLogger(__name__)

ROUTE_LOG = "log_complaint"
ROUTE_EDIT = "edit_complaint"
ROUTE_EXTRACT = "extract_document"
ROUTE_ANSWER = "answer_question"

_EDIT_HINTS = re.compile(
    r"\b(sorry|correction|actually|instead|change|update|amend|revise|"
    r"should be|not\s+\w+\s+it'?s|make it|set)\b",
    re.IGNORECASE,
)
_QUESTION_HINTS = re.compile(
    r"^\s*(what|why|how|who|when|which|is|are|can|could|does|do|explain|tell me)\b",
    re.IGNORECASE,
)


def _has_complaint(state: AgentState) -> bool:
    sections = state.get("form_sections") or []
    values = [v for v in flatten(sections).values() if v and v.strip()]
    return len(values) >= 3


# --- nodes -------------------------------------------------------------------

def router_node(state: AgentState) -> dict[str, Any]:
    if state.get("document_text"):
        return {"route": ROUTE_EXTRACT}

    text = (state.get("user_input") or "").strip()
    if not text:
        return {"route": ROUTE_ANSWER}

    loaded = _has_complaint(state)

    # Preferred path: let the router model pick a tool.
    if settings.llm_enabled:
        try:
            context = (
                "A complaint is currently loaded on the form."
                if loaded
                else "The form is currently EMPTY."
            )
            response = tool_call(
                [
                    ("system", T.prompts.ROUTER_SYSTEM),
                    ("human", f"{context}\n\nOfficer's message:\n{text}"),
                ],
                T.ROUTER_TOOLS,
            )
            calls = getattr(response, "tool_calls", None) or []
            if calls:
                name = calls[0].get("name")
                if name in {ROUTE_LOG, ROUTE_EDIT, ROUTE_ANSWER}:
                    route = name
                    if route == ROUTE_EDIT and not loaded:
                        route = ROUTE_LOG
                    logger.info("router(llm) -> %s", route)
                    return {"route": route}
        except (LLMUnavailable, Exception) as exc:  # noqa: BLE001
            logger.warning("router LLM path failed (%s); using heuristic", exc)

    # Heuristic fallback.
    if loaded and _EDIT_HINTS.search(text) and len(text) < 400:
        route = ROUTE_EDIT
    elif _QUESTION_HINTS.search(text) and not loaded:
        route = ROUTE_ANSWER
    elif loaded and _QUESTION_HINTS.search(text):
        route = ROUTE_ANSWER
    else:
        route = ROUTE_LOG
    logger.info("router(heuristic) -> %s", route)
    return {"route": route}


def log_complaint_node(state: AgentState) -> dict[str, Any]:
    return T.log_complaint(state.get("user_input", ""))


def edit_complaint_node(state: AgentState) -> dict[str, Any]:
    return T.edit_complaint(
        state.get("user_input", ""),
        state.get("form_sections") or empty_schema(),
        state.get("risk"),
    )


def extract_document_node(state: AgentState) -> dict[str, Any]:
    return T.extract_document(
        state.get("document_text", ""), state.get("filename", "")
    )


def answer_question_node(state: AgentState) -> dict[str, Any]:
    question = state.get("user_input", "")
    sections = state.get("form_sections") or []

    if not settings.llm_enabled:
        if not _has_complaint(state):
            reply = (
                "No complaint is loaded yet. Paste the customer's message or upload "
                "a complaint PDF and I'll extract it."
            )
        else:
            reply = (
                "The complaint on the left is ready to commit. Ask me to change any "
                "field, or press Commit to QMS Ledger."
            )
        return {"reply": reply, "tool_used": ROUTE_ANSWER}

    try:
        record = T._record_text(sections, state.get("risk"))
        reply = chat_call(
            [
                (
                    "system",
                    "You are AIVOA Copilot, a pharmaceutical QMS assistant. Answer "
                    "the QA officer concisely (max 3 sentences) using the complaint "
                    "record below. Do not invent data that is not present.",
                ),
                ("human", f"Current record:\n{record}\n\nQuestion: {question}"),
            ]
        )
        return {"reply": reply, "tool_used": ROUTE_ANSWER}
    except Exception as exc:  # noqa: BLE001
        logger.warning("answer_question failed: %s", exc)
        return {
            "reply": "I couldn't process that just now. Please try again.",
            "tool_used": ROUTE_ANSWER,
        }


def finalize_node(state: AgentState) -> dict[str, Any]:
    """Append this turn to the transcript."""
    new_messages: list[Any] = []
    if state.get("user_input"):
        new_messages.append(HumanMessage(content=state["user_input"]))
    elif state.get("filename"):
        new_messages.append(HumanMessage(content=f"[uploaded {state['filename']}]"))
    if state.get("reply"):
        new_messages.append(AIMessage(content=state["reply"]))
    return {"messages": new_messages}


# --- graph -------------------------------------------------------------------

def _select(state: AgentState) -> str:
    return state.get("route") or ROUTE_ANSWER


def build_graph():
    builder = StateGraph(AgentState)

    builder.add_node("router", router_node)
    builder.add_node(ROUTE_LOG, log_complaint_node)
    builder.add_node(ROUTE_EDIT, edit_complaint_node)
    builder.add_node(ROUTE_EXTRACT, extract_document_node)
    builder.add_node(ROUTE_ANSWER, answer_question_node)
    builder.add_node("finalize", finalize_node)

    builder.add_edge(START, "router")
    builder.add_conditional_edges(
        "router",
        _select,
        {
            ROUTE_LOG: ROUTE_LOG,
            ROUTE_EDIT: ROUTE_EDIT,
            ROUTE_EXTRACT: ROUTE_EXTRACT,
            ROUTE_ANSWER: ROUTE_ANSWER,
        },
    )
    for node in (ROUTE_LOG, ROUTE_EDIT, ROUTE_EXTRACT, ROUTE_ANSWER):
        builder.add_edge(node, "finalize")
    builder.add_edge("finalize", END)

    return builder.compile()


GRAPH = build_graph()


def initial_state(session_id: str) -> AgentState:
    return {
        "session_id": session_id,
        "messages": [],
        "form_sections": empty_schema(),
        "risk": {},
        "status": STATUS_PENDING,
    }
