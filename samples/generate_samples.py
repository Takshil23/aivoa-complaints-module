"""Generate realistic pharmaceutical customer-complaint documents for the demo.

The assignment says: "You may create your own realistic pharmaceutical complaint
PDFs, emails, or images for demonstration."

Produces, in this folder:
  Fictional_Pharma_Customer_Complaint_API.pdf   - the API / foreign-matter case
                                                  from the demo video
  Fictional_Pharma_Customer_Complaint_FDF.pdf   - a finished-dose-form case
  Fictional_Pharma_Customer_Complaint_Email.txt - a raw email complaint

All companies, batch numbers and people are fictional.

Run:  python samples/generate_samples.py
      (needs `reportlab`: pip install reportlab)
"""

from __future__ import annotations

import sys
from pathlib import Path

OUT = Path(__file__).parent

# --- Case 1: the API complaint reproduced from the demo video -----------------
API_CASE = {
    "filename": "Fictional_Pharma_Customer_Complaint_API.pdf",
    "owner": "ZENITH LIFE SCIENCES LIMITED",
    "owner_sub": "Plot 42, Pharma SEZ, Ankleshwar, Gujarat 393002, India",
    "owner_meta": "CDSCO Licence: G/28/1174   |   US FDA FEI: 3009887421",
    "title": "CUSTOMER COMPLAINT REPORT",
    "meta": [
        ("Complaint No.", "CC-2026-00154"),
        ("Date Received", "12 July 2026"),
        ("Received Via", "Email"),
        ("Logged By", "R. Deshmukh, QA Officer"),
    ],
    "complainant": [
        ("Customer Name", "ABC Formulations Ltd."),
        ("Contact Person", "S. Iyer, Head - Quality Control"),
        ("Site", "Unit II, Baddi, Himachal Pradesh"),
        ("Purchase Order", "PO/ABC/2026/0774"),
    ],
    "product": [
        ("Product Name", "Metformin Hydrochloride API"),
        ("Product Strength/Grade", "IP/BP"),
        ("Batch / Lot No.", "MFH260712A"),
        ("Quantity Affected", "25 kg (1 HDPE Drum)"),
        ("Manufacturing Date", "25 June 2026"),
        ("Retest Date", "24 June 2029"),
        ("Expiry Date", "Not Provided"),
        ("Quantity Supplied", "500 kg (20 HDPE Drums)"),
    ],
    "narrative": [
        "During incoming quality inspection at the customer's Baddi facility, "
        "multiple dark foreign particles were observed inside one sealed HDPE "
        "drum of Metformin Hydrochloride API.",
        "The drum tamper-evident seal was found intact and the drum showed no "
        "visible external damage. Particles were described as irregular, dark "
        "grey to black, approximately 0.5-2 mm, dispersed through the upper "
        "layer of the powder bed.",
        "The affected drum has been quarantined and segregated. The customer "
        "has withheld the remaining 19 drums of the same batch pending our "
        "response, and requests a laboratory investigation with a manufacturing "
        "record review.",
    ],
    "attachments": [
        "Photographs of the foreign particles (4 images)",
        "Incoming inspection record IQC/2026/1188",
        "Copy of the drum label and tamper seal",
    ],
    "footer": (
        "This is a fictional document created for a technical assessment "
        "demonstration. All entities, batch numbers and personnel are invented."
    ),
}

# --- Case 2: a finished dose form complaint ----------------------------------
FDF_CASE = {
    "filename": "Fictional_Pharma_Customer_Complaint_FDF.pdf",
    "owner": "ZENITH LIFE SCIENCES LIMITED",
    "owner_sub": "Plot 42, Pharma SEZ, Ankleshwar, Gujarat 393002, India",
    "owner_meta": "CDSCO Licence: G/28/1174   |   US FDA FEI: 3009887421",
    "title": "CUSTOMER COMPLAINT REPORT",
    "meta": [
        ("Complaint No.", "CC-2026-00161"),
        ("Date Received", "21 July 2026"),
        ("Received Via", "Distributor"),
        ("Logged By", "P. Kulkarni, QA Officer"),
    ],
    "complainant": [
        ("Customer Name", "Northbridge Hospital Pharmacy"),
        ("Contact Person", "Dr. A. Menon, Chief Pharmacist"),
        ("Site", "Northbridge General Hospital, Pune"),
        ("Purchase Order", "PO/NBH/2026/2210"),
    ],
    "product": [
        ("Product Name", "Cefixime Dispersible Tablets"),
        ("Product Strength", "200 mg"),
        ("Batch / Lot No.", "CFX250918B"),
        ("Quantity Affected", "3 blister strips (30 tablets)"),
        ("Manufacturing Date", "September 2025"),
        ("Expiry Date", "August 2027"),
        ("Quantity Supplied", "600 strips"),
    ],
    "narrative": [
        "The hospital pharmacy reported that tablets in three blister strips "
        "had developed brown mottling on the tablet surface and a faint "
        "sulphurous odour on opening.",
        "The blister foil showed partial delamination along one edge of each "
        "affected strip. Storage records confirm the cartons were held at "
        "22-24 C and 48-55% RH throughout.",
        "The pharmacy has withdrawn the affected strips from dispensing and "
        "requests investigation and replacement stock.",
    ],
    "attachments": [
        "Photographs of mottled tablets (3 images)",
        "Pharmacy storage temperature log for July 2026",
    ],
    "footer": (
        "This is a fictional document created for a technical assessment "
        "demonstration. All entities, batch numbers and personnel are invented."
    ),
}

EMAIL = """From: s.iyer@abcformulations-example.com
To: qa.complaints@zenithlifesciences-example.com
Cc: purchase@abcformulations-example.com
Date: Mon, 27 Jul 2026 09:14:22 +0530
Subject: URGENT - Foreign particles found in Ibuprofen BP batch IBU260415C

Dear Zenith QA team,

We are writing to raise a formal quality complaint regarding a consignment
received at our Baddi Unit II facility on 22 July 2026.

Product:            Ibuprofen BP (API)
Grade:              BP/EP
Batch / Lot No.:    IBU260415C
Manufacturing date: 15 April 2026
Retest date:        14 April 2029
Quantity supplied:  300 kg (12 fibre drums)
Quantity affected:  50 kg (2 fibre drums)

During incoming quality inspection our QC analysts observed translucent
fibrous strands, approximately 3-8 mm long, in the powder of two drums
(drum serials 07 and 11). Both drums were sealed and undamaged on arrival.
The material in both drums has been quarantined and is not released for
manufacturing.

Given that this is the second foreign matter observation from your Ankleshwar
site this year, we request:

  1. A laboratory investigation with particle identification.
  2. A review of the manufacturing and packing records for this batch.
  3. Your CAPA response within 15 working days.

We are holding the remaining 10 drums pending your reply.

Regards,
S. Iyer
Head - Quality Control
ABC Formulations Ltd.

--
This is a fictional email created for a technical assessment demonstration.
"""


def build_pdf(case: dict) -> Path:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    path = OUT / case["filename"]
    styles = getSampleStyleSheet()

    h_owner = ParagraphStyle(
        "owner", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=14,
        textColor=colors.HexColor("#1e293b"), spaceAfter=2,
    )
    h_sub = ParagraphStyle(
        "sub", parent=styles["Normal"], fontSize=8.5,
        textColor=colors.HexColor("#64748b"), spaceAfter=1,
    )
    h_title = ParagraphStyle(
        "title", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=12.5,
        alignment=TA_CENTER, spaceBefore=14, spaceAfter=12,
        textColor=colors.HexColor("#0f172a"),
    )
    h_sec = ParagraphStyle(
        "sec", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=9.5,
        textColor=colors.HexColor("#334155"), spaceBefore=12, spaceAfter=6,
    )
    body = ParagraphStyle(
        "body", parent=styles["Normal"], fontSize=9.5, leading=14, spaceAfter=7,
    )
    small = ParagraphStyle(
        "small", parent=styles["Normal"], fontSize=7.5, leading=10,
        textColor=colors.HexColor("#94a3b8"), spaceBefore=16,
    )

    cell = ParagraphStyle(
        "cell", parent=styles["Normal"], fontSize=9, leading=11.5,
        textColor=colors.HexColor("#0f172a"),
    )

    def kv_table(rows: list[tuple[str, str]], cols: int = 2) -> Table:
        """Render key/value pairs as a real table so table extraction has
        something to recover. Values are Paragraphs so long text wraps inside
        the cell rather than being clipped at the column edge."""
        data = []
        if cols == 2:
            for i in range(0, len(rows), 2):
                pair = rows[i : i + 2]
                line = []
                for key, value in pair:
                    line += [key, Paragraph(value, cell)]
                while len(line) < 4:
                    line.append("")
                data.append(line)
            widths = [38 * mm, 45 * mm, 38 * mm, 45 * mm]
        else:
            data = [[k, Paragraph(v, cell)] for k, v in rows]
            widths = [50 * mm, 116 * mm]

        table = Table(data, colWidths=widths, hAlign="LEFT")
        style = [
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#0f172a")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dbe3f0")),
        ]
        for col in (0, 2) if cols == 2 else (0,):
            style.append(("FONTNAME", (col, 0), (col, -1), "Helvetica-Bold"))
            style.append(
                ("BACKGROUND", (col, 0), (col, -1), colors.HexColor("#f7f8fa"))
            )
        table.setStyle(TableStyle(style))
        return table

    story = [
        Paragraph(case["owner"], h_owner),
        Paragraph(case["owner_sub"], h_sub),
        Paragraph(case["owner_meta"], h_sub),
        Paragraph(case["title"], h_title),
        kv_table(case["meta"]),
        Paragraph("1.  COMPLAINANT DETAILS", h_sec),
        kv_table(case["complainant"]),
        Paragraph("2.  PRODUCT &amp; BATCH DETAILS", h_sec),
        kv_table(case["product"]),
        Paragraph("3.  NATURE OF COMPLAINT", h_sec),
    ]
    for para in case["narrative"]:
        story.append(Paragraph(para, body))

    story.append(Paragraph("4.  ATTACHMENTS PROVIDED BY CUSTOMER", h_sec))
    for item in case["attachments"]:
        story.append(Paragraph(f"-&nbsp;&nbsp;{item}", body))

    story.append(Spacer(1, 8))
    story.append(
        kv_table(
            [
                ("Acknowledged To Customer", "Yes - 12 July 2026"),
                ("Investigation Reference", "To be assigned"),
            ],
            cols=1,
        )
    )
    story.append(Paragraph(case["footer"], small))

    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=22 * mm,
        rightMargin=22 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=case["filename"],
        author=case["owner"],
    )
    doc.build(story)
    return path


def main() -> int:
    try:
        import reportlab  # noqa: F401
    except ImportError:
        print("reportlab is required:  pip install reportlab", file=sys.stderr)
        return 1

    for case in (API_CASE, FDF_CASE):
        print("wrote", build_pdf(case))

    email_path = OUT / "Fictional_Pharma_Customer_Complaint_Email.txt"
    email_path.write_text(EMAIL, encoding="utf-8")
    print("wrote", email_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
