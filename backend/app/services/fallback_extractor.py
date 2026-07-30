"""Deterministic, regex-based complaint extractor.

Used only when no GROQ_API_KEY is configured, so the app is runnable and testable
before credentials exist (and so the test suite does not need network access).
It is intentionally simple — the LLM path is the real implementation.
"""

from __future__ import annotations

import re

from app.services.form_schema import NOT_PROVIDED

_MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|"
    "November|December"
)

# Separators cover prose ("Batch number AMX240602"), colons, and the
# pipe-delimited cells pdfplumber produces from a table row
# ("Batch / Lot No. | MFH260712A").
_BATCH = re.compile(
    r"\b(?:batch|lot)\s*(?:/\s*lot\s*)?(?:number|no\.?|#)?\s*[:\-|]?\s*"
    r"([A-Z]{2,4}\s?\d{5,10}[A-Z]?)",
    re.IGNORECASE,
)
_STRENGTH = re.compile(r"\b(\d+(?:\.\d+)?)\s*(mg|mcg|g|ml|IU)\b", re.IGNORECASE)
_GRADE = re.compile(r"\b(IP\s*/\s*BP|USP\s*/\s*NF|IP|BP|USP|EP)\b")
_MFG = re.compile(
    rf"manufactur\w*\s*(?:date)?\s*[:\-]?\s*"
    rf"((?:\d{{1,2}}\s+)?(?:{_MONTHS})\s+\d{{4}}|\d{{2}}[/-]\d{{2}}[/-]\d{{2,4}})",
    re.IGNORECASE,
)
_EXP = re.compile(
    rf"(?:expiry|expiration|exp\.?)\s*(?:date)?\s*[:\-]?\s*"
    rf"((?:\d{{1,2}}\s+)?(?:{_MONTHS})\s+\d{{4}}|\d{{2}}[/-]\d{{2}}[/-]\d{{2,4}})",
    re.IGNORECASE,
)
_QTY = re.compile(
    r"\b(\d+)\s*(capsules?|tablets?|vials?|bottles?|kg|g|units?|drums?)\b",
    re.IGNORECASE,
)
# `[ \t]+` rather than `\s+`: a company or product name must never be stitched
# together across a line break.
_CUSTOMER = re.compile(
    r"\b([A-Z][A-Za-z&.\-]*(?:[ \t]+[A-Z][A-Za-z&.\-]*){0,3}[ \t]+"
    r"(?:Pharmacy|Pharmaceuticals?|Formulations?|Labs?|Laboratories|Hospital|"
    r"Healthcare|Life[ \t]+Sciences|Ltd\.?|Limited|Inc\.?|LLP|Pvt\.?))"
)
_PRODUCT = re.compile(
    r"\b([A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+)*[ \t]+"
    r"(?:Capsules?|Tablets?|Injection|Suspension|Syrup|Ointment|Cream|API))\b"
)
_IS_API = re.compile(r"\bAPI\b", re.IGNORECASE)
_REF = re.compile(r"\b(CC-\d{4}-\d{4,6})\b")

_DEFECT_MAP = [
    (r"foreign (?:matter|particle|body)|black particle|dark particle",
     "Foreign Matter Contamination", "Critical"),
    (r"discolo|mottl|stain", "Product Defect - Discoloration", "Major"),
    (r"delaminat", "Packaging Defect", "Major"),
    (r"broken|crack|chip|damag", "Product Defect - Physical Damage", "Major"),
    (r"label|mislabel", "Labelling Error", "Major"),
    (r"seal|leak|packag", "Packaging Defect", "Major"),
    (r"short (?:shipment|supply)|missing quantity", "Short Shipment", "Minor"),
    (r"not work|ineffective|no relief|efficacy", "Efficacy Complaint", "Major"),
]


def _first(pattern: re.Pattern[str], text: str, group: int = 1) -> str:
    match = pattern.search(text)
    return match.group(group).strip() if match else ""


def _labelled(text: str, *labels: str) -> str:
    """Read `Label | Value` / `Label: Value` rows out of a document.

    Structured documents put the facts in a table, so a label lookup beats the
    loose prose patterns. Pipe-delimited rows (what pdfplumber's table extractor
    emits) are tried first, because the same PDF also yields a run-together
    prose line where the value cannot be bounded reliably.
    """
    for require_pipe in (True, False):
        separator = r"\s*\|\s*" if require_pipe else r"\s*[:\-]\s*"
        for label in labels:
            # A label can start a line or follow a pipe — in a 4-column table the
            # second key/value pair sits mid-row ("Batch | X | Quantity | Y").
            pattern = re.compile(
                rf"(?:^|\|)[^\S\n]*{re.escape(label)}{separator}([^|\n]+)",
                re.IGNORECASE | re.MULTILINE,
            )
            match = pattern.search(text)
            if not match:
                continue
            value = re.sub(r"\s+", " ", match.group(1)).strip(" \t|:")
            if not require_pipe:
                # Prose captures can run to a sentence end; table cells cannot,
                # so only trim a trailing period outside a table.
                value = value.rstrip(".")
            # A very long capture means the pattern ran past the real value.
            if value and len(value) <= 120:
                return value
    return ""


def _classify(text: str) -> tuple[str, str]:
    lowered = text.lower()
    for pattern, category, severity in _DEFECT_MAP:
        if re.search(pattern, lowered):
            return category, severity
    return "Product Quality Complaint", "Major"


def _source(text: str, customer: str) -> str:
    lowered = text.lower()
    for needle, label in (
        ("pharmacy", "Pharmacy"),
        ("hospital", "Hospital"),
        ("distributor", "Distributor"),
        ("phone", "Phone"),
        ("email", "Email"),
        ("@", "Email"),
    ):
        if needle in lowered:
            return label
    return "Email" if customer else NOT_PROVIDED


def extract(text: str) -> dict:
    """Return the same shape the LLM tools return."""
    # Prefer an explicit labelled row; fall back to the loose prose patterns.
    customer = _labelled(text, "Customer Name", "Complainant") or _first(
        _CUSTOMER, text
    )
    product = _labelled(text, "Product Name", "Product") or _first(_PRODUCT, text)
    is_api = bool(_IS_API.search(product))

    batch = _first(_BATCH, text)
    if batch:
        batch = re.sub(r"\s+", " ", batch).strip()

    strength = _labelled(
        text, "Product Strength/Grade", "Product Strength", "Grade", "Strength"
    )
    strength_match = _STRENGTH.search(text)
    if strength:
        pass
    elif is_api:
        strength = _first(_GRADE, text) or NOT_PROVIDED
    elif strength_match:
        strength = f"{strength_match.group(1)} {strength_match.group(2).lower()}"
    else:
        strength = NOT_PROVIDED

    quantity = _labelled(text, "Quantity Affected", "Affected Quantity")
    if not quantity:
        qty_match = _QTY.search(text)
        quantity = (
            f"{qty_match.group(1)} {qty_match.group(2).lower()}"
            if qty_match
            else NOT_PROVIDED
        )

    category, severity = _classify(text)
    npm = "HDPE Drum" if "drum" in text.lower() else (
        "Primary Packaging (Bottle)" if "bottle" in text.lower() else NOT_PROVIDED
    )

    inferred = [
        key
        for key, value in (
            ("complaint_source", True),
            ("originating_site_block", True),
            ("impacted_npm", npm != NOT_PROVIDED),
            ("complaint_category", True),
        )
        if value
    ]

    description = (
        f"{customer or 'The customer'} reported "
        f"{quantity if quantity != NOT_PROVIDED else 'an issue'} "
        f"relating to {product or 'the product'}"
        f"{f' (batch {batch})' if batch else ''}. "
        "Requesting investigation."
    )

    return {
        "fields": {
            "complaint_source": _source(text, customer),
            "customer_name": customer or NOT_PROVIDED,
            "product_name": product or NOT_PROVIDED,
            "product_strength": strength,
            "batch_lot_number": batch or NOT_PROVIDED,
            "affected_quantity": quantity,
            "manufacturing_date": _first(_MFG, text) or NOT_PROVIDED,
            "expiry_date": _first(_EXP, text) or NOT_PROVIDED,
            "originating_site_block": "Manufacturing",
            "impacted_npm": npm,
            "complaint_category": category,
            "complaint_description": description,
        },
        "risk": {
            "severity": severity,
            "suggested_next_action": (
                "Laboratory investigation & manufacturing record review"
                if severity == "Critical"
                else "Route to QA Investigation & Issue Replacement"
            ),
            "initial_risk_assessment": (
                f"Probable {category.lower()}. Requires batch record review and "
                "evaluation of retained samples."
            ),
        },
        "inferred_fields": inferred,
        "document_reference": _first(_REF, text),
        "reply": (
            "Complaint parsed successfully. I've extracted the product details, "
            "mapped the batch information, and generated an initial risk assessment."
        ),
    }


# --- deterministic edit path -------------------------------------------------

_EDIT_TARGETS: list[tuple[str, re.Pattern[str]]] = [
    (
        "batch_lot_number",
        re.compile(
            r"(?:batch|lot)\s*(?:/\s*lot\s*)?(?:number|no\.?|#)?\s*(?:is|to|=|:)?\s*"
            r"([A-Z]{2,4}\s?\d{5,10}[A-Z]?)",
            re.IGNORECASE,
        ),
    ),
    (
        "affected_quantity",
        re.compile(
            r"(?:affected\s+)?quantity\s*(?:is|to|=|:)?\s*"
            r"(\d+\s*[A-Za-z]+(?:\s*\([^)]*\))?)",
            re.IGNORECASE,
        ),
    ),
    (
        "customer_name",
        re.compile(r"customer(?:\s+name)?\s*(?:is|to|=|:)\s*([^.,;]+)", re.IGNORECASE),
    ),
    (
        "product_name",
        re.compile(r"product(?:\s+name)?\s*(?:is|to|=|:)\s*([^.,;]+)", re.IGNORECASE),
    ),
    (
        "expiry_date",
        re.compile(
            rf"expiry\s*(?:date)?\s*(?:is|to|=|:)?\s*"
            rf"((?:\d{{1,2}}\s+)?(?:{_MONTHS})\s+\d{{4}})",
            re.IGNORECASE,
        ),
    ),
]


_RUN_ON = re.compile(r"(?<=[A-Za-z0-9])and(?=\s|$).*$", re.IGNORECASE)


def clean_batch(value: str) -> str:
    """Split a run-on batch number: "CHG 260712Aand affected" -> "CHG 260712A".

    The officers in the demo type corrections without a space before "and", so the
    batch swallows the rest of the sentence. Applied to model output too, not just
    the regex path — the 8B models copy the run-on verbatim however firmly the
    prompt asks them not to, so this is a guarantee rather than a hope.

    Only fires when a digit survives the cut, so a genuine token like "GRAND" is
    left alone.
    """
    cleaned = _RUN_ON.sub("", value).strip(" .,;")
    return cleaned if any(ch.isdigit() for ch in cleaned) else value


def extract_edits(instruction: str) -> dict[str, str]:
    """Best-effort sparse patch from a correction sentence."""
    patch: dict[str, str] = {}
    for key, pattern in _EDIT_TARGETS:
        match = pattern.search(instruction)
        if match:
            value = re.sub(r"\s+", " ", match.group(1)).strip(" .,;")
            if key == "batch_lot_number":
                value = clean_batch(value)
            if value:
                patch[key] = value
    return patch
