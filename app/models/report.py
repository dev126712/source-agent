import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import Verdict
from app.db.session import Base


class SourcingRun(Base):
    """Groups a batch of candidates (e.g. one CSV upload) for progress tracking."""

    __tablename__ = "sourcing_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    label: Mapped[str | None] = mapped_column(String(256))
    total: Mapped[int] = mapped_column(Integer, default=0)
    completed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SourcingReport(Base):
    """The researched output for a single candidate. Kept separate from the
    candidate so the input contract stays clean and the report is auditable."""

    __tablename__ = "sourcing_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("product_candidates.id"), index=True
    )

    # --- resolved identity ---
    resolved_asin: Mapped[str | None] = mapped_column(String(16))
    resolved_title: Mapped[str | None] = mapped_column(String(512))
    resolved_category: Mapped[str | None] = mapped_column(String(256))

    # --- amazon data snapshot ---
    amazon_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    bsr: Mapped[int | None] = mapped_column(Integer)
    offer_count: Mapped[int | None] = mapped_column(Integer)

    # --- computed economics ---
    est_profit: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    est_margin_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    breakeven_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))

    # --- verdict ---
    verdict: Mapped[Verdict | None] = mapped_column(String(12))
    risk_flags: Mapped[list | None] = mapped_column(JSONB)
    reasoning: Mapped[str | None] = mapped_column(Text)

    # --- evidence trail: every finding + source URL the agent used ---
    findings: Mapped[list | None] = mapped_column(JSONB)
    sources: Mapped[list | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
