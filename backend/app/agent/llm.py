"""Groq LLM clients + a strict JSON call helper.

Two models, deliberately:

* `primary_model`  = gemma2-9b-it            — mandated by the assignment. Does
  every extraction / reasoning job through JSON-only prompting, because gemma2
  has no native tool-calling support on Groq.
* `router_model`   = llama-3.3-70b-versatile — supports Groq native tool calling,
  so it powers the LangGraph router node that picks which of the three mandatory
  tools to run.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


class LLMUnavailable(RuntimeError):
    """Raised when no Groq key is configured, or Groq cannot be reached."""


def _build(model: str, **kwargs: Any):
    if not settings.llm_enabled:
        raise LLMUnavailable("GROQ_API_KEY is not set")
    from langchain_groq import ChatGroq

    return ChatGroq(
        model=model,
        api_key=settings.groq_api_key,
        temperature=kwargs.pop("temperature", settings.llm_temperature),
        max_retries=settings.llm_max_retries,
        **kwargs,
    )


def primary_llm(**kwargs: Any):
    return _build(settings.primary_model, **kwargs)


def router_llm(**kwargs: Any):
    return _build(settings.router_model, temperature=0.0, **kwargs)


def extract_json(text: str) -> dict[str, Any]:
    """Pull a JSON object out of a model response.

    gemma2 occasionally wraps JSON in prose or a ```json fence even when told not
    to, so parse defensively rather than trusting the happy path.
    """
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = _JSON_BLOCK.search(text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Model did not return valid JSON: {text[:400]}") from exc
    raise ValueError(f"Model did not return valid JSON: {text[:400]}")


def json_call(system: str, user: str, *, model: str | None = None) -> dict[str, Any]:
    """One-shot JSON completion against Groq.

    Uses Groq's JSON mode where the model supports it, and still parses
    defensively.
    """
    kwargs: dict[str, Any] = {}
    target = model or settings.primary_model
    # Groq JSON mode is available on both configured models.
    kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}

    llm = _build(target, **kwargs)
    response = llm.invoke(
        [
            ("system", system),
            ("human", user),
        ]
    )
    content = response.content
    if isinstance(content, list):  # some providers return content parts
        content = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    return extract_json(str(content))
