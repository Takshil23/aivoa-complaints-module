"""The three mandatory AI tools, plus the optional bonus tools.

Each tool is a plain callable that takes the current agent state and returns a
partial state update. They are wrapped as LangChain `@tool` objects at the bottom
so the router model can select them by name via native tool calling.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.tools import tool

from app.agent import prompts
from app.agent.llm import LLMUnavailable, json_call
from app.config import settings
from app.services import fallback_extractor as fb
from app.services.form_schema import (
    NOT_PROVIDED,
    STATUS_READY,
    apply_patch,
    flatten,
    label_map,
    populated_schema,
    strength_label_for,
)

logger = logging.getLogger(__name__)


def _record_text(sections: list[dict[str, Any]], risk: dict[str, str] | None) -> str:
    """Serialise the current record for a prompt."""
    payload = {"fields": flatten(sections), "risk": risk or {}}
    return json.dumps(payload, indent=2)


# --- Tool 1: Log Complaint ---------------------------------------------------

def log_complaint(raw_text: str) -> dict[str, Any]:
    """Parse a raw complaint into a structured QMS record + risk assessment."""
    if settings.llm_enabled:
        try:
            result = json_call(prompts.LOG_COMPLAINT_SYSTEM, raw_text)
        except (LLMUnavailable, ValueError) as exc:
            logger.warning("log_complaint LLM path failed (%s); using fallback", exc)
            result = fb.extract(raw_text)
    else:
        result = fb.extract(raw_text)

    return _build_populated(result)


# --- Tool 2: Edit Complaint --------------------------------------------------

def edit_complaint(
    instruction: str,
    sections: list[dict[str, Any]],
    risk: dict[str, str] | None,
) -> dict[str, Any]:
    """Apply a natural-language correction as a *sparse patch*.

    Fields absent from the patch keep their existing values — this is what
    satisfies "preserving all other complaint information".
    """
    labels = label_map(sections)
    patch: dict[str, str] = {}
    new_risk = dict(risk or {})
    reply = ""

    if settings.llm_enabled:
        user = (
            f"Current record:\n{_record_text(sections, risk)}\n\n"
            f"Valid field keys: {sorted(labels)}\n\n"
            f"Officer's instruction:\n{instruction}"
        )
        try:
            result = json_call(prompts.EDIT_COMPLAINT_SYSTEM, user)
            patch = {
                k: str(v)
                for k, v in (result.get("patch") or {}).items()
                if k in labels and str(v).strip()
            }
            if result.get("risk"):
                new_risk.update(
                    {k: str(v) for k, v in result["risk"].items() if str(v).strip()}
                )
            reply = str(result.get("reply") or "")
        except (LLMUnavailable, ValueError) as exc:
            logger.warning("edit_complaint LLM path failed (%s); using fallback", exc)

    if not patch:
        patch = {k: v for k, v in fb.extract_edits(instruction).items() if k in labels}

    if not patch:
        return {
            "reply": (
                "I couldn't tell which field to change. Name the field and the new "
                "value — for example: \"the batch number is BMX240602\"."
            ),
            "tool_used": "edit_complaint",
            "patch": {},
        }

    updated = apply_patch(sections, patch)

    if not reply:
        parts = [f'{labels[k]} to "{v}"' for k, v in patch.items()]
        joined = parts[0] if len(parts) == 1 else (
            ", ".join(parts[:-1]) + " and " + parts[-1]
        )
        reply = f"Got it. I have updated the {joined} in the form."

    return {
        "form_sections": updated,
        "risk": new_risk,
        "status": STATUS_READY,
        "reply": reply,
        "tool_used": "edit_complaint",
        "patch": patch,
    }


# --- Tool 3: Document Extraction ---------------------------------------------

def extract_document(document_text: str, filename: str = "") -> dict[str, Any]:
    """Extract a complaint from document text (PDF / email export)."""
    if settings.llm_enabled:
        try:
            user = f"Filename: {filename}\n\nDocument text:\n{document_text}"
            result = json_call(prompts.EXTRACT_DOCUMENT_SYSTEM, user)
        except (LLMUnavailable, ValueError) as exc:
            logger.warning("extract_document LLM path failed (%s); using fallback", exc)
            result = fb.extract(document_text)
    else:
        result = fb.extract(document_text)

    state = _build_populated(result)
    state["tool_used"] = "extract_document"

    reference = str(result.get("document_reference") or "").strip()
    if reference and reference not in state["reply"]:
        state["reply"] = (
            f"PDF analysis complete. I've successfully extracted complaint report "
            f"({reference}). {state['reply']} Form populated on the left."
        )
    return state


# --- shared -------------------------------------------------------------------

def _build_populated(result: dict[str, Any]) -> dict[str, Any]:
    fields = {k: str(v) for k, v in (result.get("fields") or {}).items()}
    for key in (
        "complaint_source",
        "customer_name",
        "product_name",
        "product_strength",
        "batch_lot_number",
        "affected_quantity",
        "manufacturing_date",
        "expiry_date",
        "originating_site_block",
        "impacted_npm",
        "complaint_category",
        "complaint_description",
    ):
        fields.setdefault(key, NOT_PROVIDED)

    inferred = {str(k) for k in (result.get("inferred_fields") or [])}
    risk = {k: str(v) for k, v in (result.get("risk") or {}).items()}

    return {
        "form_sections": populated_schema(
            fields,
            inferred_keys=inferred,
            strength_label=strength_label_for(fields.get("product_name", "")),
        ),
        "risk": risk,
        "status": STATUS_READY,
        "reply": str(result.get("reply") or "Complaint parsed successfully."),
        "tool_used": "log_complaint",
        "patch": {},
    }


# --- Bonus AI tools -----------------------------------------------------------

def _bonus(system: str, sections: list[dict[str, Any]], risk: dict | None) -> dict:
    if not settings.llm_enabled:
        raise LLMUnavailable(
            "This AI feature needs a Groq API key. Set GROQ_API_KEY in backend/.env."
        )
    return json_call(system, _record_text(sections, risk))


def completeness_check(sections, risk=None) -> dict:
    return _bonus(prompts.COMPLETENESS_SYSTEM, sections, risk)


def capa_recommendation(sections, risk=None) -> dict:
    return _bonus(prompts.CAPA_SYSTEM, sections, risk)


def root_cause_analysis(sections, risk=None) -> dict:
    return _bonus(prompts.ROOT_CAUSE_SYSTEM, sections, risk)


def complaint_summary(sections, risk=None) -> dict:
    return _bonus(prompts.SUMMARY_SYSTEM, sections, risk)


# --- LangChain tool wrappers (used by the router model) -----------------------
# These exist so the router LLM can pick a tool by name through Groq's native
# tool calling. Execution happens in the graph nodes, which hold the state.

@tool("log_complaint")
def log_complaint_tool(complaint_text: str) -> str:
    """Record a NEW customer complaint from raw text, email body, or pasted message.
    Use when the message describes a complaint that is not yet on the form."""
    return "routed"


@tool("edit_complaint")
def edit_complaint_tool(instruction: str) -> str:
    """Correct or amend the complaint already loaded on the form. Use for messages
    like 'sorry, the batch number is X' or 'change the affected quantity to Y'."""
    return "routed"


@tool("answer_question")
def answer_question_tool(question: str) -> str:
    """Answer a question about the current complaint record or the QMS process
    without changing the form."""
    return "routed"


ROUTER_TOOLS = [log_complaint_tool, edit_complaint_tool, answer_question_tool]
