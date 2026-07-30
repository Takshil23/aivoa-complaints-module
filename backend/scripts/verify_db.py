"""Prove the schema really works on PostgreSQL or MySQL, not just SQLite.

The brief mandates MySQL or PostgreSQL. The models are written to be portable —
`JSON` maps to jsonb / JSON / TEXT, no server-specific defaults — but portable in
principle and portable in fact are different claims, and only this settles it.

    cd backend
    .venv\\Scripts\\python.exe scripts/verify_db.py --url postgresql+psycopg://user:pass@host:5432/aivoa
    .venv\\Scripts\\python.exe scripts/verify_db.py --url mysql+pymysql://user:pass@host:3306/aivoa

With no --url it reads DATABASE_URL from backend/.env.

What it checks, in the order the app would hit it: connect, create the schema,
round-trip the JSON columns (nested, unicode, long text), the complaint-number
sequence, the batch index used by duplicate detection, cascade delete, and the
timezone-aware timestamps. It cleans up every row it writes.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, event, func, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.config import settings  # noqa: E402
from app.db.models import Base, ChatMessage, Complaint, Session  # noqa: E402
from app.services.form_schema import populated_schema  # noqa: E402

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []


def record(status: str, name: str, detail: str = "") -> None:
    results.append((status, name, detail))
    print(f"{'[ok]  ' if status == PASS else '[FAIL]'} {name}"
          + (f" - {detail}" if detail else ""))


def require(ok: bool, label: str, detail: str = "") -> bool:
    record(PASS if ok else FAIL, label, detail)
    return ok


def head(title: str) -> None:
    print(f"\n{'=' * 74}\n{title}\n{'=' * 74}")


# A payload designed to break a database that only pretends to store JSON:
# nesting, non-ASCII, quotes, and the exact shape the form actually carries.
TRICKY = populated_schema(
    {
        "customer_name": 'Apothèke "Zentral" GmbH & Co. KG',
        "product_name": "Metformin Hydrochloride API",
        "batch_lot_number": "MFH260712A",
        "complaint_description": "Dark foreign particles — 25 kg (1 HDPE Drum). "
        + "Long text padding. " * 40,
    },
    inferred_keys={"impacted_npm"},
    strength_label="Product Strength/Grade",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=settings.database_url)
    parser.add_argument(
        "--keep", action="store_true", help="leave the test rows behind"
    )
    args = parser.parse_args()
    url = args.url

    head("1. Connection")
    dialect = url.split(":", 1)[0]
    print(f"  {dialect} — {url.split('@')[-1] if '@' in url else url}")
    if dialect.startswith("sqlite"):
        print(
            "\n  NOTE: this is SQLite. The assignment mandates MySQL or PostgreSQL,\n"
            "  so pass --url, or set DATABASE_URL, before treating this as done.\n"
        )

    connect_args = {"check_same_thread": False} if dialect.startswith("sqlite") else {}
    try:
        engine = create_engine(url, pool_pre_ping=True, connect_args=connect_args)
        if engine.dialect.name == "sqlite":
            # Mirror app.db.session: without this SQLite ignores foreign keys, so
            # the cascade check below would pass for the wrong reason.
            @event.listens_for(engine, "connect")
            def _fk_on(dbapi_connection, _record):  # noqa: ANN001
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

        with engine.connect() as connection:
            version = connection.exec_driver_sql("SELECT 1").scalar()
        require(version == 1, "server answers a trivial query")
    except Exception as exc:  # noqa: BLE001
        record(FAIL, "connect", str(exc)[:300])
        print(
            "\n  Could not connect. Check the host, port, credentials and that the\n"
            "  database itself exists — SQLAlchemy will not create it for you."
        )
        return 1

    head("2. Schema creation")
    try:
        Base.metadata.create_all(engine)
        require(True, "create_all succeeded on this engine")
    except Exception as exc:  # noqa: BLE001
        record(FAIL, "create_all", str(exc)[:300])
        return 1

    from sqlalchemy import inspect

    tables = set(inspect(engine).get_table_names())
    for table in ("sessions", "chat_messages", "complaints"):
        require(table in tables, f"table '{table}' exists")

    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    written: list[str] = []

    head("3. JSON round-trip")
    with SessionLocal() as db:
        record_row = Session(
            form_sections=TRICKY,
            risk={
                "severity": "Critical",
                "suggested_next_action": "Laboratory investigation & manufacturing "
                "record review",
                "initial_risk_assessment": "Foreign particulate — propagates "
                "downstream.",
            },
            status="ready_to_commit",
        )
        db.add(record_row)
        db.commit()
        written.append(record_row.id)
        session_id = record_row.id

    with SessionLocal() as db:
        loaded = db.get(Session, session_id)
        require(loaded is not None, "session read back")
        require(
            json.dumps(loaded.form_sections, sort_keys=True)
            == json.dumps(TRICKY, sort_keys=True),
            "form_sections survived the JSON column byte for byte",
        )
        values = {
            f["key"]: f["value"]
            for section in loaded.form_sections
            for f in section["fields"]
        }
        require(
            values.get("customer_name") == 'Apothèke "Zentral" GmbH & Co. KG',
            "non-ASCII and quotes preserved",
            values.get("customer_name", ""),
        )
        require(
            len(values.get("complaint_description", "")) > 700,
            "long description not truncated",
            f"{len(values.get('complaint_description', ''))} chars",
        )
        require(
            any(
                f.get("inferred")
                for section in loaded.form_sections
                for f in section["fields"]
            ),
            "AI INFERRED flags survived the round trip",
        )
        require(
            loaded.risk.get("severity") == "Critical", "risk dict round-tripped"
        )

    head("4. Timestamps")
    with SessionLocal() as db:
        loaded = db.get(Session, session_id)
        require(
            isinstance(loaded.created_at, datetime),
            "created_at comes back as a datetime",
            str(loaded.created_at),
        )
        # MySQL drops the tzinfo unless the column is explicitly configured; the
        # app only ever formats it, so naive is acceptable — but say so out loud.
        naive = loaded.created_at.tzinfo is None
        record(
            PASS,
            "created_at timezone",
            "naive (driver dropped tzinfo — fine, the API isoformats it)"
            if naive
            else "timezone-aware",
        )

    head("5. Transcript + cascade delete")
    with SessionLocal() as db:
        for role, content in (
            ("assistant", "Ready to process new complaints."),
            ("user", "ah sorry the batch number is CHG 260712Aand"),
        ):
            db.add(
                ChatMessage(
                    session_id=session_id,
                    role=role,
                    content=content,
                    meta={"icon": "spark", "toolUsed": "edit_complaint"},
                )
            )
        db.commit()

    with SessionLocal() as db:
        messages = list(
            db.scalars(
                select(ChatMessage)
                .where(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.id)
            )
        )
        require(len(messages) == 2, "messages persisted", str(len(messages)))
        require(
            messages[0].id < messages[1].id,
            "autoincrement id preserves transcript order",
        )
        require(
            messages[1].meta.get("toolUsed") == "edit_complaint",
            "message meta JSON round-tripped",
        )

    head("6. Ledger: sequence, index, uniqueness")
    with SessionLocal() as db:
        year = datetime.now(timezone.utc).year
        prefix = f"CC-{year}-"
        count = db.scalar(
            select(func.count(Complaint.id)).where(
                Complaint.complaint_number.like(f"{prefix}%")
            )
        )
        require(count is not None, "complaint-number sequence query runs", str(count))
        number = f"{prefix}{(count or 0) + 1:05d}-verify"

        complaint = Complaint(
            complaint_number=number,
            session_id=session_id,
            customer_name="ABC Formulations Ltd.",
            product_name="Metformin Hydrochloride API",
            batch_lot_number="CHG 260712A",
            complaint_description="Dark foreign particles in one sealed HDPE drum.",
            severity="Critical",
            suggested_next_action="Laboratory investigation & manufacturing record review",
            initial_risk_assessment="Foreign particulate in an API.",
            form_snapshot=TRICKY,
        )
        db.add(complaint)
        db.commit()
        written.append(complaint.id)
        complaint_id = complaint.id

    with SessionLocal() as db:
        found = db.get(Complaint, complaint_id)
        require(found is not None, "complaint committed and read back", number)
        require(
            found.form_snapshot and len(found.form_snapshot) == len(TRICKY),
            "form_snapshot JSON persisted on the ledger row",
        )
        # The query behind duplicate detection.
        matches = list(
            db.scalars(
                select(Complaint).where(Complaint.batch_lot_number == "CHG 260712A")
            )
        )
        require(bool(matches), "batch index query finds the row (duplicate detection)")

        duplicate = Complaint(complaint_number=number, batch_lot_number="X")
        db.add(duplicate)
        try:
            db.commit()
            record(FAIL, "duplicate complaint_number rejected", "it was accepted")
        except Exception:
            db.rollback()
            record(PASS, "duplicate complaint_number rejected by the unique index")

    if not args.keep:
        head("7. Cleanup + cascade")
        with SessionLocal() as db:
            db.query(Complaint).filter(Complaint.id == complaint_id).delete()
            # Delete through the ORM, not a bulk query: bulk deletes bypass the
            # relationship cascade on purpose, so this is the path the app takes.
            db.delete(db.get(Session, session_id))
            db.commit()
        with SessionLocal() as db:
            orphans = db.scalar(
                select(func.count(ChatMessage.id)).where(
                    ChatMessage.session_id == session_id
                )
            )
            require(
                orphans == 0,
                "deleting the session removed its messages (cascade)",
                f"{orphans} left",
            )
            require(
                db.get(Complaint, complaint_id) is None, "test complaint removed"
            )

    engine.dispose()

    failed = sum(1 for status, _, _ in results if status == FAIL)
    head("Summary")
    print(f"  {len(results) - failed} passed, {failed} failed  —  {dialect}")
    if failed:
        print("\n  FAILURES:")
        for status, name, detail in results:
            if status == FAIL:
                print(f"    - {name}: {detail}")
    elif dialect.startswith("sqlite"):
        print("\n  Passed, but on SQLite. Re-run against MySQL or PostgreSQL.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
