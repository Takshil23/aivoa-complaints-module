"""End-to-end agent tests against the exact inputs used in the demo video.

These run without a Groq key (the deterministic fallback path), so CI needs no
secrets and no network. With GROQ_API_KEY set they exercise the real LLM path.
"""

from __future__ import annotations

import pytest

from app.agent.graph import GRAPH
from app.services.form_schema import (
    STATUS_READY,
    empty_schema,
    flatten,
)

# The three prompts from the presenter's script document, verbatim.
PROMPT_1 = (
    "Apollo Pharmacy reported discolored capsules in Amoxicillin Capsules 500 mg. "
    "Batch number AMX240602. Manufacturing date March 2026. Expiry date "
    "February 2028. Please log this complaint"
)
PROMPT_2 = "ah sorry the batch number is BMX240602 and affected quantity is 48 capcules"
PROMPT_3 = (
    "ah sorry the batch number is CHG 260712Aand affected quantity is "
    "50 kg (2 HDPE Drum)"
)

PDF_TEXT = """
ZENITH LIFE SCIENCES LIMITED
Customer Complaint Report
Complaint No: CC-2026-00154

Complainant: ABC Formulations Ltd.
Received via: Email

Product Name | Metformin Hydrochloride API
Grade | IP/BP
Batch / Lot No. | MFH260712A
Quantity Affected | 25 kg (1 HDPE Drum)
Manufacturing date 25 June 2026

Nature of complaint: Multiple dark foreign particles were observed inside one
sealed HDPE drum during incoming quality inspection. The drum had no visible
external damage. Material has been quarantined.
"""


def _run(state: dict) -> dict:
    return GRAPH.invoke(state)


def _base() -> dict:
    return {
        "session_id": "test",
        "form_sections": empty_schema(),
        "risk": {},
        "status": "pending_triage",
    }


class TestLogComplaint:
    def test_populates_form_and_risk(self):
        result = _run({**_base(), "user_input": PROMPT_1})
        values = flatten(result["form_sections"])

        assert result["tool_used"] == "log_complaint"
        assert result["status"] == STATUS_READY
        assert values["batch_lot_number"] == "AMX240602"
        assert "Amoxicillin" in values["product_name"]
        assert values["product_strength"] == "500 mg"
        assert values["manufacturing_date"] == "March 2026"
        assert values["expiry_date"] == "February 2028"
        assert "Apollo Pharmacy" in values["customer_name"]

    def test_generates_risk_assessment(self):
        result = _run({**_base(), "user_input": PROMPT_1})
        risk = result["risk"]
        assert risk["severity"] in {"Critical", "Major", "Minor"}
        assert risk["suggested_next_action"]
        assert risk["initial_risk_assessment"]

    def test_schema_switches_to_four_sections(self):
        result = _run({**_base(), "user_input": PROMPT_1})
        titles = [s["title"] for s in result["form_sections"]]
        assert titles == [
            "ORIGIN & CUSTOMER DETAILS",
            "PRODUCT & BATCH IDENTIFICATION",
            "FACILITY & MATERIAL IMPACT",
            "DEFECT ANALYSIS",
        ]


class TestEditComplaint:
    def test_patches_only_named_fields(self):
        logged = _run({**_base(), "user_input": PROMPT_1})
        before = flatten(logged["form_sections"])

        edited = _run(
            {
                "session_id": "test",
                "form_sections": logged["form_sections"],
                "risk": logged["risk"],
                "status": logged["status"],
                "user_input": PROMPT_2,
            }
        )
        after = flatten(edited["form_sections"])

        assert edited["tool_used"] == "edit_complaint"
        assert after["batch_lot_number"] == "BMX240602"
        assert "48" in after["affected_quantity"]

        # Everything the user did not mention must survive untouched.
        for key in (
            "product_name",
            "product_strength",
            "manufacturing_date",
            "expiry_date",
            "customer_name",
            "complaint_category",
            "complaint_description",
        ):
            assert after[key] == before[key], f"{key} was clobbered by the edit"

    def test_handles_missing_space_typo(self):
        """'CHG 260712Aand affected' must yield batch 'CHG 260712A'."""
        logged = _run({**_base(), "document_text": PDF_TEXT, "filename": "c.pdf"})
        edited = _run(
            {
                "session_id": "test",
                "form_sections": logged["form_sections"],
                "risk": logged["risk"],
                "status": logged["status"],
                "user_input": PROMPT_3,
            }
        )
        batch = flatten(edited["form_sections"])["batch_lot_number"]
        assert batch.replace(" ", "").upper().startswith("CHG260712A")
        assert not batch.lower().endswith("and")

    def test_reply_names_the_display_label(self):
        logged = _run({**_base(), "user_input": PROMPT_1})
        edited = _run(
            {
                "session_id": "test",
                "form_sections": logged["form_sections"],
                "risk": logged["risk"],
                "status": logged["status"],
                "user_input": PROMPT_2,
            }
        )
        assert "Batch / Lot Number" in edited["reply"]


class TestExtractDocument:
    def test_extracts_api_complaint(self):
        result = _run({**_base(), "document_text": PDF_TEXT, "filename": "report.pdf"})
        values = flatten(result["form_sections"])

        assert result["tool_used"] == "extract_document"
        assert values["batch_lot_number"] == "MFH260712A"
        assert "Metformin" in values["product_name"]
        assert "ABC Formulations" in values["customer_name"]
        assert result["status"] == STATUS_READY

    def test_api_gets_grade_label(self):
        result = _run({**_base(), "document_text": PDF_TEXT, "filename": "report.pdf"})
        labels = {
            f["key"]: f["label"] for s in result["form_sections"] for f in s["fields"]
        }
        assert labels["product_strength"] == "Product Strength/Grade"

    def test_foreign_matter_is_critical(self):
        result = _run({**_base(), "document_text": PDF_TEXT, "filename": "report.pdf"})
        assert result["risk"]["severity"] == "Critical"


class TestRouting:
    def test_empty_form_routes_correction_to_log(self):
        """A correction-shaped message with no complaint loaded is a new complaint."""
        result = _run({**_base(), "user_input": PROMPT_2})
        assert result["tool_used"] == "log_complaint"

    def test_document_always_routes_to_extract(self):
        result = _run({**_base(), "user_input": "here", "document_text": PDF_TEXT})
        assert result["tool_used"] == "extract_document"


class TestSchemaHelpers:
    def test_apply_patch_is_sparse(self):
        from app.services.form_schema import apply_patch, populated_schema

        sections = populated_schema(
            {"product_name": "X", "batch_lot_number": "B1", "customer_name": "C"}
        )
        patched = apply_patch(sections, {"batch_lot_number": "B2"})
        values = flatten(patched)
        assert values["batch_lot_number"] == "B2"
        assert values["product_name"] == "X"
        assert values["customer_name"] == "C"

    @pytest.mark.parametrize(
        ("product", "expected"),
        [
            ("Metformin Hydrochloride API", "Product Strength/Grade"),
            ("Amoxicillin Capsules", "Product Strength"),
        ],
    )
    def test_strength_label(self, product, expected):
        from app.services.form_schema import strength_label_for

        assert strength_label_for(product) == expected
