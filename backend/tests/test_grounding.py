"""No value enters a regulated record unless the source said it.

Regression cover for the worst bug found in this project: asked to log the message
"i dont have that", the agent returned a complete complaint — customer, product,
batch `AMX500123`, quantity, dates, a defect description — and set the form to
*Ready to Commit*. Every value came from an example inside the prompt's own field
contract. A small model with nothing to extract extracts the instructions.
"""

from __future__ import annotations

import pytest

from app.agent import graph as G
from app.agent import tools as T
from app.config import settings
from app.services import grounding
from app.services.form_schema import NOT_PROVIDED, STATUS_PENDING, flatten

SOURCE = (
    "Apollo Pharmacy reported discolored capsules in Amoxicillin Capsules 500 mg. "
    "Batch number AMX240602. Manufacturing date March 2026."
)


# --- the primitive -----------------------------------------------------------

@pytest.mark.parametrize(
    ("value", "supported"),
    [
        ("Amoxicillin Capsules", True),
        ("AMX240602", True),
        ("500 mg", True),
        ("March 2026", True),
        ("Apollo Pharmacy", True),
        # Reformatting is fine — the substance is present.
        ("Batch AMX240602", True),
        # Placeholders assert nothing.
        ("Not Provided", True),
        ("", True),
        # Invented.
        ("AMX500123", False),
        ("Metformin Hydrochloride API", False),
        ("12 capsules", False),
        ("February 2028", False),
        ("ABC Pharmacy", False),
    ],
)
def test_is_supported(value, supported):
    assert grounding.is_supported(value, SOURCE) is supported


def test_ground_blanks_only_the_unsupported():
    fields = {
        "product_name": "Amoxicillin Capsules",   # in source
        "batch_lot_number": "AMX500123",          # invented
        "affected_quantity": "12 capsules",       # invented
        "customer_name": "Apollo Pharmacy",       # in source
    }
    cleaned, dropped = grounding.ground(fields, SOURCE, inferred=set())

    assert cleaned["product_name"] == "Amoxicillin Capsules"
    assert cleaned["customer_name"] == "Apollo Pharmacy"
    assert cleaned["batch_lot_number"] == "Not Provided"
    assert cleaned["affected_quantity"] == "Not Provided"
    assert len(dropped) == 2


def test_fields_the_prompt_may_infer_are_exempt():
    """The model is explicitly allowed to infer these, and the UI badges them."""
    fields = {"product_name": "Amoxicillin Capsules", "complaint_source": "Pharmacy"}
    cleaned, dropped = grounding.ground(
        fields, SOURCE, inferred={"complaint_source"}
    )
    assert cleaned["complaint_source"] == "Pharmacy"
    assert not dropped


def test_one_identity_field_is_enough_for_a_complaint():
    """A thin complaint is still a complaint: 'Apollo Pharmacy says the capsules
    are discoloured' names no batch and must not be rejected."""
    assert grounding.has_complaint({"customer_name": "Apollo Pharmacy"})
    assert grounding.has_complaint({"batch_lot_number": "AMX240602"})
    assert not grounding.has_complaint(
        {"customer_name": NOT_PROVIDED, "product_name": NOT_PROVIDED}
    )


# --- the tools ---------------------------------------------------------------

def test_log_complaint_refuses_a_contentless_message(monkeypatch):
    """The exact reproduction: a model that returns a full record for 'i dont
    have that' must not reach the form."""
    monkeypatch.setattr(settings, "groq_api_key", "gsk_test")
    monkeypatch.setattr(
        T,
        "json_call",
        lambda *a, **k: {
            "fields": {
                "complaint_source": "Email",
                "customer_name": "ABC Pharmacy",
                "product_name": "Amoxicillin Capsules",
                "product_strength": "500 mg",
                "batch_lot_number": "AMX500123",
                "affected_quantity": "12 capsules",
                "manufacturing_date": "February 2026",
                "expiry_date": "August 2027",
                "complaint_description": "ABC Pharmacy reported 12 discoloured capsules.",
            },
            "risk": {"severity": "Major"},
            "inferred_fields": [],
            "reply": "Complaint parsed successfully.",
        },
    )

    state = T.log_complaint("i dont have that")

    assert state["status"] == STATUS_PENDING, "must not become Ready to Commit"
    populated = {
        k: v
        for k, v in flatten(state["form_sections"]).items()
        if v and v != NOT_PROVIDED
    }
    assert not populated, f"fabricated values reached the form: {populated}"
    assert not state["risk"], "no risk assessment for a complaint that does not exist"
    assert "couldn't find any complaint details" in state["reply"]


def test_log_complaint_keeps_a_real_complaint_intact(monkeypatch):
    """The guard must not cost us the legitimate path."""
    monkeypatch.setattr(settings, "groq_api_key", "gsk_test")
    monkeypatch.setattr(
        T,
        "json_call",
        lambda *a, **k: {
            "fields": {
                "customer_name": "Apollo Pharmacy",
                "product_name": "Amoxicillin Capsules",
                "product_strength": "500 mg",
                "batch_lot_number": "AMX240602",
                "manufacturing_date": "March 2026",
                "complaint_source": "Pharmacy",
                "complaint_description": "Apollo Pharmacy reported discoloured capsules.",
            },
            "risk": {"severity": "Major", "suggested_next_action": "QA investigation"},
            "inferred_fields": ["complaint_source"],
            "reply": "Complaint parsed successfully.",
        },
    )

    fields = flatten(T.log_complaint(SOURCE)["form_sections"])
    assert fields["batch_lot_number"] == "AMX240602"
    assert fields["product_name"] == "Amoxicillin Capsules"
    assert fields["complaint_source"] == "Pharmacy"  # inferred, exempt


def test_edit_cannot_invent_a_batch_number(monkeypatch):
    monkeypatch.setattr(settings, "groq_api_key", "gsk_test")
    sections = T._build_populated(
        {"fields": {"product_name": "Amoxicillin Capsules"}}
    )["form_sections"]
    monkeypatch.setattr(
        T,
        "json_call",
        lambda *a, **k: {
            "patch": {"batch_lot_number": "ZZZ999999"},  # never typed by anyone
            "reply": "Updated.",
        },
    )

    result = T.edit_complaint("please fix the batch number", sections, {})
    assert "batch_lot_number" not in result["patch"]


# --- the router --------------------------------------------------------------

@pytest.mark.parametrize(
    "message",
    ["Hello", "i dont have that", "ok thanks", "yes please", "hmm"],
)
def test_router_never_logs_a_contentless_message(message):
    state = G.initial_state("test")
    state["user_input"] = message
    assert G.router_node(state)["route"] == G.ROUTE_ANSWER


@pytest.mark.parametrize(
    "message",
    [
        "Apollo Pharmacy reported discolored capsules in Amoxicillin 500 mg",
        "we received a damaged shipment",
        "batch AMX240602 has foreign particles",
    ],
)
def test_router_still_logs_a_real_complaint(message):
    state = G.initial_state("test")
    state["user_input"] = message
    assert G.router_node(state)["route"] == G.ROUTE_LOG
