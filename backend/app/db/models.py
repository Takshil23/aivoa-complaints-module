"""SQLAlchemy models.

Portable across PostgreSQL, MySQL and SQLite: the JSON column type maps to
jsonb / JSON / TEXT respectively, and no server-specific defaults are used.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Session(Base):
    """One complaint-intake working session (one browser tab)."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    form_sections: Mapped[list] = mapped_column(JSON, default=list)
    risk: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="pending_triage")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.id",
    )


class ChatMessage(Base):
    """A rendered bubble in the copilot transcript."""

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))          # user | assistant
    kind: Mapped[str] = mapped_column(String(16), default="text")  # text | file
    content: Mapped[str] = mapped_column(Text, default="")
    meta: Mapped[dict] = mapped_column(JSON, default=dict)  # filename, tool_used, …
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now
    )

    session: Mapped[Session] = relationship(back_populates="messages")


class Complaint(Base):
    """A complaint committed to the QMS ledger."""

    __tablename__ = "complaints"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    complaint_number: Mapped[str] = mapped_column(
        String(32), unique=True, index=True
    )
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    complaint_source: Mapped[str] = mapped_column(String(128), default="")
    customer_name: Mapped[str] = mapped_column(String(255), default="")
    product_name: Mapped[str] = mapped_column(String(255), default="")
    product_strength: Mapped[str] = mapped_column(String(128), default="")
    batch_lot_number: Mapped[str] = mapped_column(String(128), index=True, default="")
    affected_quantity: Mapped[str] = mapped_column(String(128), default="")
    manufacturing_date: Mapped[str] = mapped_column(String(64), default="")
    expiry_date: Mapped[str] = mapped_column(String(64), default="")
    originating_site_block: Mapped[str] = mapped_column(String(128), default="")
    impacted_npm: Mapped[str] = mapped_column(String(255), default="")
    complaint_category: Mapped[str] = mapped_column(String(255), default="")
    complaint_description: Mapped[str] = mapped_column(Text, default="")

    severity: Mapped[str] = mapped_column(String(32), default="")
    suggested_next_action: Mapped[str] = mapped_column(Text, default="")
    initial_risk_assessment: Mapped[str] = mapped_column(Text, default="")

    # Full schema snapshot, so a record renders exactly as it was committed even
    # if the schema evolves later.
    form_snapshot: Mapped[list] = mapped_column(JSON, default=list)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now()
    )

    LEDGER_FIELDS = (
        "complaint_source",
        "customer_name",
        "product_name",
        "product_strength",
        "batch_lot_number",
        "affected_quantity",
        "manufacturing_date",
        "expiry_date",
        "originating_site_block",
        "impacted_npm",
        "complaint_category",
        "complaint_description",
    )
