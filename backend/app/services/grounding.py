"""Refuse to put a value in a regulated record unless the source actually said it.

A QMS Customer Complaint is a regulated document. A fabricated batch number in one
is not a cosmetic defect — it is the kind of thing that fails an audit, so this is
enforced in code rather than requested in a prompt.

The failure this exists to stop, observed against a live model: given the message
"i dont have that", the agent returned a complete complaint — customer, product,
batch `AMX500123`, quantity, dates, a defect description — and the form went to
*Ready to Commit*. Every value traced back to an example in the prompt's own field
contract. A small model with nothing to extract will happily extract the
instructions instead.

The rule: a field the model claims to have **read** must be traceable to the source
text. Fields the prompt explicitly allows it to **infer** (how the complaint
arrived, which site block, which packaging, the defect category) are exempt, and
the UI badges those as `AI INFERRED` anyway. Anything else that cannot be traced
becomes "Not Provided" — the honest answer.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Read from the source, never invented. These are the fields an investigator
# would act on, and the ones a wrong value does real damage in.
GROUNDED_FIELDS = (
    "customer_name",
    "product_name",
    "product_strength",
    "batch_lot_number",
    "affected_quantity",
    "manufacturing_date",
    "expiry_date",
)

# At least one of these must survive, or there is no complaint to log at all.
IDENTITY_FIELDS = ("product_name", "batch_lot_number", "customer_name")

_WORD = re.compile(r"[a-z0-9]+")
_PLACEHOLDER = {"", "not provided", "n/a", "na", "none", "unknown", "-"}


def _tokens(text: str) -> list[str]:
    """Alphanumeric runs, lowercased. Single characters are dropped — they carry
    no evidence and match almost anything."""
    return [t for t in _WORD.findall(text.lower()) if len(t) > 1]


def is_supported(value: str, source: str) -> bool:
    """Does `source` actually contain the substance of `value`?

    Token containment rather than substring, so a model that reformats
    "Batch No. AMX240602" to "AMX240602", or drops a comma, still passes — while
    "Amoxicillin Capsules" invented out of a prompt example does not.
    """
    if (value or "").strip().lower() in _PLACEHOLDER:
        return True  # nothing asserted, nothing to ground

    needles = _tokens(value)
    if not needles:
        return True  # e.g. a value that is only punctuation

    haystack = set(_tokens(source))
    return all(token in haystack for token in needles)


def ground(
    fields: dict[str, str],
    source: str,
    inferred: set[str],
    *,
    not_provided: str = "Not Provided",
) -> tuple[dict[str, str], list[str]]:
    """Blank every read-field the source does not support.

    Returns the cleaned fields and the list of keys that were dropped, so the
    caller can log them — a model inventing data is worth knowing about.
    """
    dropped: list[str] = []
    cleaned = dict(fields)

    for key in GROUNDED_FIELDS:
        if key in inferred:
            continue  # the prompt permits inference here; the UI badges it
        value = cleaned.get(key, "")
        if not is_supported(value, source):
            dropped.append(f"{key}={value!r}")
            cleaned[key] = not_provided

    if dropped:
        logger.warning(
            "grounding: dropped %d unsupported value(s) from the model: %s",
            len(dropped),
            ", ".join(dropped),
        )
    return cleaned, dropped


def has_complaint(fields: dict[str, str], *, not_provided: str = "Not Provided") -> bool:
    """Is there enough grounded substance here to be a complaint at all?

    One identity field is deliberately enough: "Apollo Pharmacy says the capsules
    are discoloured" is a real complaint even though it names no batch.
    """
    placeholders = _PLACEHOLDER | {not_provided.lower()}
    return any(
        (fields.get(key) or "").strip().lower() not in placeholders
        for key in IDENTITY_FIELDS
    )
