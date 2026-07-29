"""Canonical complaint form schema.

The demo video shows the form's *sections and labels* changing once a complaint
has been parsed (and `Product Strength` becoming `Product Strength/Grade` for an
API rather than a finished dose form). So the schema is treated as data the agent
returns, and the React form renders whatever arrives — it hardcodes no fields.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal

FieldType = Literal["text", "textarea", "select"]

SITE_BLOCK_OPTIONS = [
    "Manufacturing",
    "Packaging",
    "Warehouse / Storage",
    "Quality Control Laboratory",
    "Distribution",
]

STATUS_PENDING = "pending_triage"
STATUS_READY = "ready_to_commit"
STATUS_COMMITTED = "committed"

# Values the LLM is told to use when a datum genuinely is not in the source.
NOT_PROVIDED = "Not Provided"


def _field(
    key: str,
    label: str,
    ftype: FieldType = "text",
    value: str = "",
    placeholder: str = "",
    options: list[str] | None = None,
    inferred: bool = False,
    full_width: bool = False,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "type": ftype,
        "value": value,
        "placeholder": placeholder,
        "options": options,
        "inferred": inferred,
        "fullWidth": full_width,
    }


def empty_schema() -> list[dict[str, Any]]:
    """The three-section 'awaiting AI' state shown at 0:00 in the demo."""
    return [
        {
            "index": 1,
            "title": "PRODUCT & BATCH IDENTIFICATION",
            "fields": [
                _field(
                    "product_name",
                    "Product Name (API/FDF)",
                    placeholder="Awaiting AI extraction...",
                ),
                _field(
                    "batch_lot_number",
                    "Batch / Lot Number",
                    placeholder="Awaiting AI extraction...",
                ),
            ],
        },
        {
            "index": 2,
            "title": "FACILITY & MATERIAL IMPACT",
            "fields": [
                _field(
                    "originating_site_block",
                    "Originating Site Block",
                    "select",
                    placeholder="Awaiting AI classification...",
                    options=SITE_BLOCK_OPTIONS,
                ),
                _field(
                    "impacted_npm",
                    "Impacted Non-Product Materials (NPM)",
                    placeholder="e.g., Primary packaging...",
                ),
            ],
        },
        {
            "index": 3,
            "title": "DEFECT ANALYSIS",
            "fields": [
                _field(
                    "complaint_description",
                    "Structured Defect Summary",
                    "textarea",
                    placeholder=(
                        "AI will synthesize the complaint into a formal QMS "
                        "description..."
                    ),
                    full_width=True,
                ),
            ],
        },
    ]


def populated_schema(
    values: dict[str, str],
    inferred_keys: set[str] | None = None,
    strength_label: str = "Product Strength",
) -> list[dict[str, Any]]:
    """The four-section state shown once a complaint has been parsed.

    `strength_label` lets the agent switch to "Product Strength/Grade" for an
    API, exactly as the demo does at 2:20.
    """
    inferred_keys = inferred_keys or set()

    def val(key: str) -> str:
        return values.get(key, "") or ""

    def mk(key: str, label: str, **kw: Any) -> dict[str, Any]:
        return _field(key, label, value=val(key), inferred=key in inferred_keys, **kw)

    return [
        {
            "index": 1,
            "title": "ORIGIN & CUSTOMER DETAILS",
            "fields": [
                mk("complaint_source", "Complaint Source"),
                mk("customer_name", "Customer Name"),
            ],
        },
        {
            "index": 2,
            "title": "PRODUCT & BATCH IDENTIFICATION",
            "fields": [
                mk("product_name", "Product Name"),
                mk("product_strength", strength_label),
                mk("batch_lot_number", "Batch / Lot Number"),
                mk("affected_quantity", "Affected Quantity"),
                mk("manufacturing_date", "Manufacturing Date"),
                mk("expiry_date", "Expiry Date"),
            ],
        },
        {
            "index": 3,
            "title": "FACILITY & MATERIAL IMPACT",
            "fields": [
                mk(
                    "originating_site_block",
                    "Originating Site Block",
                    ftype="select",
                    options=SITE_BLOCK_OPTIONS,
                ),
                mk("impacted_npm", "Impacted Non-Product Materials (NPM)"),
            ],
        },
        {
            "index": 4,
            "title": "DEFECT ANALYSIS",
            "fields": [
                mk("complaint_category", "Complaint Category", full_width=True),
                mk(
                    "complaint_description",
                    "Complaint Description",
                    ftype="textarea",
                    full_width=True,
                ),
            ],
        },
    ]


# --- helpers used by the edit tool -------------------------------------------

def flatten(sections: list[dict[str, Any]]) -> dict[str, str]:
    """sections -> {field_key: value}"""
    return {f["key"]: f["value"] for s in sections for f in s["fields"]}


def label_map(sections: list[dict[str, Any]]) -> dict[str, str]:
    """sections -> {field_key: display label}, so the copilot can echo the
    label the user actually sees ('Batch / Lot Number', not 'batch_lot_number')."""
    return {f["key"]: f["label"] for s in sections for f in s["fields"]}


def apply_patch(
    sections: list[dict[str, Any]], patch: dict[str, str]
) -> list[dict[str, Any]]:
    """Merge a sparse {field_key: new_value} patch over the existing schema.

    This is *the* mechanism that satisfies the assignment's requirement that an
    edit preserves "all other complaint information": fields absent from the
    patch are never touched.
    """
    out = deepcopy(sections)
    for section in out:
        for field in section["fields"]:
            if field["key"] in patch:
                field["value"] = patch[field["key"]]
                field["inferred"] = False  # user-confirmed beats model-inferred
    return out


def strength_label_for(product_name: str) -> str:
    """APIs are graded (IP/BP/USP); finished dose forms have a strength."""
    name = (product_name or "").lower()
    if "api" in name or "active pharmaceutical ingredient" in name:
        return "Product Strength/Grade"
    return "Product Strength"
