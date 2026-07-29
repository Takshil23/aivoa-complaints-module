"""Turn an uploaded complaint document into text for the extraction tool.

The assignment states production-grade OCR is not required. PDFs are parsed with
pdfplumber, which recovers both prose and *tables* — the demo's progress label
says "Extracting tabular data via OCR", and real complaint reports put the batch
details in a table, so table recovery matters more than OCR here.

Scanned/image-only PDFs are detected and reported honestly rather than silently
returning nothing.
"""

from __future__ import annotations

import io
import logging

logger = logging.getLogger(__name__)

SUPPORTED_SUFFIXES = {".pdf", ".txt", ".eml", ".md"}


class DocumentParseError(RuntimeError):
    pass


def _table_to_text(table: list[list[str | None]]) -> str:
    lines = []
    for row in table:
        cells = [(c or "").strip().replace("\n", " ") for c in row]
        if any(cells):
            lines.append(" | ".join(cells))
    return "\n".join(lines)


def parse_pdf(data: bytes) -> str:
    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover
        raise DocumentParseError("pdfplumber is not installed") from exc

    chunks: list[str] = []
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page_no, page in enumerate(pdf.pages, start=1):
                text = (page.extract_text() or "").strip()
                if text:
                    chunks.append(f"--- Page {page_no} ---\n{text}")
                for table in page.extract_tables() or []:
                    rendered = _table_to_text(table)
                    if rendered:
                        chunks.append(f"--- Page {page_no} table ---\n{rendered}")
    except Exception as exc:  # noqa: BLE001
        raise DocumentParseError(f"Could not read the PDF: {exc}") from exc

    combined = "\n\n".join(chunks).strip()
    if not combined:
        raise DocumentParseError(
            "No selectable text found — this looks like a scanned image PDF. "
            "Production-grade OCR is out of scope; please upload a text-based PDF, "
            "or paste the complaint text into the chat instead."
        )
    return combined


def parse(filename: str, data: bytes) -> str:
    lowered = (filename or "").lower()
    suffix = lowered[lowered.rfind(".") :] if "." in lowered else ""

    if suffix == ".pdf" or data[:5] == b"%PDF-":
        return parse_pdf(data)

    if suffix in {".txt", ".eml", ".md"} or not suffix:
        for encoding in ("utf-8", "utf-16", "latin-1"):
            try:
                text = data.decode(encoding).strip()
                if text:
                    return text
            except UnicodeDecodeError:
                continue
        raise DocumentParseError("Could not decode the file as text.")

    raise DocumentParseError(
        f"Unsupported file type '{suffix}'. Upload a PDF, .txt or .eml."
    )
