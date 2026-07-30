"""Groq LLM clients + a strict JSON call helper.

Two roles, deliberately:

* `primary` = gemma2-9b-it            — mandated by the assignment. Does every
  extraction / reasoning job through JSON-only prompting, because gemma2 has no
  native tool-calling support on Groq.
* `router`  = llama-3.3-70b-versatile — supports Groq native tool calling, so it
  powers the LangGraph router node that picks which of the three mandatory tools
  to run.

Both are *requested* first and both are on Groq's deprecation list — gemma2-9b-it
was decommissioned on 2025-10-08 and llama-3.3-70b-versatile shuts down on
2026-08-16. So each role is a **chain**: the assignment's model is attempted, and
if Groq answers `model_decommissioned` / `model_not_found` the next live model in
`settings.model_chain()` takes over. A dead model is remembered per-process, so
the 404 is paid once, not once per request. `active_model()` reports what actually
served the traffic.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from typing import Any, Callable, TypeVar

from app.config import settings

logger = logging.getLogger(__name__)

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)

# Groq's wording for "this model id is gone". Matched against the exception text
# because langchain wraps the provider error rather than re-raising it typed.
_MODEL_GONE = re.compile(
    r"model_decommissioned|model_not_found|does not exist|has been deprecated|"
    r"no longer supported|decommissioned",
    re.IGNORECASE,
)
_JSON_MODE_UNSUPPORTED = re.compile(
    r"response_format|json_object|json_validate_failed", re.IGNORECASE
)

T = TypeVar("T")

_lock = threading.Lock()
_dead: set[str] = set()
_active: dict[str, str] = {}


class LLMUnavailable(RuntimeError):
    """Raised when no Groq key is configured, or Groq cannot be reached."""


def active_model(kind: str = "primary") -> str:
    """The model that last served this role, or the one we would try next."""
    if kind in _active:
        return _active[kind]
    chain = settings.model_chain(kind)
    return next((m for m in chain if m not in _dead), chain[0])


def mark_dead(model: str) -> None:
    """Record a model as gone. Used by the probe in scripts/verify_llm.py, which
    calls models directly rather than through the chain."""
    with _lock:
        _dead.add(model)


def resolve_chains() -> dict[str, str]:
    """Settle which model serves each role, once, at startup.

    Without this the first officer's message pays a wasted round trip to a
    decommissioned model before the chain moves on, and `GET /api/session` would
    report the requested model as active until someone had sent a message. One
    single-token call per role at boot buys an honest answer and a faster first
    complaint. Never fatal: if Groq is unreachable the chain resolves lazily as
    before.
    """
    if not settings.llm_enabled:
        return {}

    resolved: dict[str, str] = {}
    for kind in ("primary", "router"):
        try:
            _with_fallback(kind, lambda model: _build(model).invoke([("human", "ok")]))
            resolved[kind] = active_model(kind)
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not resolve the %s model chain at startup: %s",
                           kind, exc)
    return resolved


def reset_model_cache() -> None:
    """Forget which models are dead. Used by tests and the verify script."""
    with _lock:
        _dead.clear()
        _active.clear()


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


def _with_fallback(kind: str, run: Callable[[str], T]) -> T:
    """Run `run(model)` down the chain for `kind` until a live model answers.

    Only a "model is gone" error advances the chain. Anything else (bad JSON,
    rate limit, auth failure) is raised so the caller's own fallback handles it.
    """
    if not settings.llm_enabled:
        raise LLMUnavailable("GROQ_API_KEY is not set")

    chain = settings.model_chain(kind)
    # Keep a known-good model at the front so we do not re-pay a dead 404.
    live = [m for m in chain if m not in _dead]
    if not live:
        raise LLMUnavailable(
            f"No usable Groq model for '{kind}'. Tried: {', '.join(chain)}. "
            "Check console.groq.com/docs/deprecations and update the model chain."
        )
    preferred = _active.get(kind)
    if preferred in live:
        live.remove(preferred)
        live.insert(0, preferred)

    last: Exception | None = None
    for model in live:
        try:
            result = run(model)
        except Exception as exc:  # noqa: BLE001 - classified below
            if not _MODEL_GONE.search(str(exc)):
                raise
            logger.warning(
                "Groq model %r is unavailable for %s (%s); trying next in chain",
                model,
                kind,
                str(exc)[:200],
            )
            with _lock:
                _dead.add(model)
            last = exc
            continue
        if _active.get(kind) != model:
            logger.info("%s role now served by %r", kind, model)
            with _lock:
                _active[kind] = model
        return result

    raise LLMUnavailable(
        f"Every Groq model for '{kind}' is decommissioned ({', '.join(chain)}): {last}"
    )


def primary_llm(**kwargs: Any):
    return _build(active_model("primary"), **kwargs)


def router_llm(**kwargs: Any):
    return _build(active_model("router"), temperature=0.0, **kwargs)


def chat_call(messages: list[tuple[str, str]], *, kind: str = "primary") -> str:
    """Plain (non-JSON) completion, with model fallback. Returns the text."""

    def run(model: str) -> str:
        response = _build(model).invoke(messages)
        return _content_text(response.content)

    return _with_fallback(kind, run)


def tool_call(messages: list[tuple[str, str]], tools: list[Any]) -> Any:
    """Native tool-calling completion on the router chain. Returns the message."""

    def run(model: str) -> Any:
        return _build(model, temperature=0.0).bind_tools(tools).invoke(messages)

    return _with_fallback("router", run)


def _content_text(content: Any) -> str:
    if isinstance(content, list):  # some providers return content parts
        return "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    return str(content)


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


def json_call(system: str, user: str, *, kind: str = "primary") -> dict[str, Any]:
    """One-shot JSON completion against Groq, with model fallback.

    Asks for Groq's JSON mode, drops back to plain prompting for models that
    reject `response_format`, and parses defensively either way.
    """
    messages = [("system", system), ("human", user)]

    def run(model: str) -> dict[str, Any]:
        try:
            response = _build(
                model, model_kwargs={"response_format": {"type": "json_object"}}
            ).invoke(messages)
        except Exception as exc:  # noqa: BLE001
            if _MODEL_GONE.search(str(exc)) or not _JSON_MODE_UNSUPPORTED.search(
                str(exc)
            ):
                raise
            logger.warning(
                "%r rejected JSON mode (%s); retrying as plain completion",
                model,
                str(exc)[:200],
            )
            response = _build(model).invoke(messages)
        return extract_json(_content_text(response.content))

    return _with_fallback(kind, run)
