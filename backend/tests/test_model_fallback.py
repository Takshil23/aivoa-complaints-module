"""The model chain — the code must survive Groq retiring an assignment-mandated model.

`gemma2-9b-it` (mandated) was decommissioned by Groq on 2025-10-08 and
`llama-3.3-70b-versatile` (the router) shuts down on 2026-08-16, so this
behaviour is load-bearing, not hypothetical. No network: the Groq client factory
is stubbed.
"""

from __future__ import annotations

import pytest

from app.agent import llm as L
from app.agent import tools as T
from app.config import settings
from app.services.form_schema import flatten

DECOMMISSIONED = (
    "Error code: 400 - {'error': {'message': 'The model `gemma2-9b-it` has been "
    "decommissioned...', 'code': 'model_decommissioned'}}"
)


@pytest.fixture
def with_key(monkeypatch):
    """Pretend a Groq key is configured, and start from a clean model cache."""
    monkeypatch.setattr(settings, "groq_api_key", "gsk_test")
    L.reset_model_cache()
    yield
    L.reset_model_cache()


def test_chain_requests_the_mandated_model_first():
    chain = settings.model_chain("primary")
    assert chain[0] == "gemma2-9b-it"
    assert len(chain) > 1, "a mandated model with no fallback is a single point of failure"
    assert len(chain) == len(set(chain)), "chain must be deduped"


def test_decommissioned_model_advances_to_the_next(with_key):
    tried: list[str] = []

    def run(model: str) -> str:
        tried.append(model)
        if model == "gemma2-9b-it":
            raise RuntimeError(DECOMMISSIONED)
        return "ok"

    assert L._with_fallback("primary", run) == "ok"
    assert tried == ["gemma2-9b-it", "llama-3.1-8b-instant"]
    assert L.active_model("primary") == "llama-3.1-8b-instant"


def test_a_dead_model_is_not_retried(with_key):
    tried: list[str] = []

    def run(model: str) -> str:
        tried.append(model)
        if model == "gemma2-9b-it":
            raise RuntimeError(DECOMMISSIONED)
        return "ok"

    L._with_fallback("primary", run)
    L._with_fallback("primary", run)
    # The 404 is paid once, then skipped: second call goes straight to the winner.
    assert tried == ["gemma2-9b-it", "llama-3.1-8b-instant", "llama-3.1-8b-instant"]


def test_other_errors_do_not_advance_the_chain(with_key):
    """A rate limit or malformed JSON is the caller's problem to handle — burning
    through the chain on it would hide the real failure."""
    tried: list[str] = []

    def run(model: str):
        tried.append(model)
        raise ValueError("Model did not return valid JSON: <html>")

    with pytest.raises(ValueError):
        L._with_fallback("primary", run)
    assert tried == ["gemma2-9b-it"]


def test_all_models_gone_raises_llm_unavailable(with_key):
    def run(model: str):
        raise RuntimeError(DECOMMISSIONED)

    with pytest.raises(L.LLMUnavailable):
        L._with_fallback("primary", run)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("CHG 260712Aand affected", "CHG 260712A"),
        ("CHG 260712Aand affected quantity is 50 kg", "CHG 260712A"),
        ("260712Aand", "260712A"),
        # Untouched: already clean, or no digit would survive the cut.
        ("MFH260712A", "MFH260712A"),
        ("AMX240602", "AMX240602"),
        ("GRAND", "GRAND"),
    ],
)
def test_clean_batch_splits_run_ons(raw, expected):
    """The models copy the officer's run-on batch number however firmly the prompt
    asks them to split it, so the split is enforced in code on both paths."""
    from app.services.fallback_extractor import clean_batch

    assert clean_batch(raw) == expected


def test_model_output_is_sanitized(monkeypatch):
    """A run-on batch coming back from the LLM never reaches the form."""
    monkeypatch.setattr(settings, "groq_api_key", "gsk_test")
    L.reset_model_cache()
    monkeypatch.setattr(
        T,
        "json_call",
        lambda *a, **k: {
            "patch": {"batch_lot_number": "CHG 260712Aand affected"},
            "reply": "Updated.",
        },
    )
    sections = T._build_populated(
        {"fields": {"product_name": "Metformin Hydrochloride API"}}
    )["form_sections"]

    result = T.edit_complaint("ah sorry the batch number is CHG 260712Aand", sections, {})
    assert result["patch"]["batch_lot_number"] == "CHG 260712A"
    L.reset_model_cache()


def test_extract_reply_does_not_double_narrate(monkeypatch):
    """The reference wrapper used to be applied unconditionally, so a model that
    followed the prompt got its sign-off duplicated."""
    monkeypatch.setattr(settings, "groq_api_key", "gsk_test")
    L.reset_model_cache()
    monkeypatch.setattr(
        T,
        "json_call",
        lambda *a, **k: {
            "fields": {"product_name": "Metformin Hydrochloride API"},
            "document_reference": "CC-2026-00154",
            "reply": (
                "I've extracted complaint report CC-2026-00154 from ABC "
                "Formulations Ltd. Form populated on the left."
            ),
        },
    )
    reply = T.extract_document("...", "complaint.pdf")["reply"]
    assert reply.count("Form populated on the left.") == 1
    assert reply.count("CC-2026-00154") == 1
    L.reset_model_cache()


def test_log_complaint_falls_back_when_groq_errors(monkeypatch):
    """Regression: a bad key / rate limit used to escape as a 500 instead of
    degrading to the deterministic extractor."""
    monkeypatch.setattr(settings, "groq_api_key", "gsk_test")
    L.reset_model_cache()

    def boom(*args, **kwargs):
        raise RuntimeError("Error code: 401 - invalid_api_key")

    monkeypatch.setattr(T, "json_call", boom)

    state = T.log_complaint(
        "Apollo Pharmacy reported discolored capsules in Amoxicillin Capsules "
        "500 mg. Batch number AMX240602."
    )
    fields = flatten(state["form_sections"])
    assert fields["batch_lot_number"] == "AMX240602"
    assert state["reply"]
    L.reset_model_cache()
