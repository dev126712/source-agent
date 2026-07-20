import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import CandidateStatus, InputChannel, SourcingMode
from app.db.session import Base


class ProductCandidate(Base):
    __tablename__ = "product_candidates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # --- identity (at least one is guaranteed by the schema layer) ---
    name: Mapped[str | None] = mapped_column(String(512))
    upc: Mapped[str | None] = mapped_column(String(32))
    asin: Mapped[str | None] = mapped_column(String(16))
    url: Mapped[str | None] = mapped_column(Text)
    brand: Mapped[str | None] = mapped_column(String(256))
    category_hint: Mapped[str | None] = mapped_column(String(256))

    # --- source context ---
    local_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    source_name: Mapped[str | None] = mapped_column(String(256))
    source_location: Mapped[str | None] = mapped_column(String(256))
    quantity_available: Mapped[int | None] = mapped_column(Integer)
    moq: Mapped[int | None] = mapped_column(Integer)

    # --- pipeline / bookkeeping ---
    sourcing_mode: Mapped[SourcingMode] = mapped_column(String(20))
    input_channel: Mapped[InputChannel] = mapped_column(String(20))
    status: Mapped[CandidateStatus] = mapped_column(
        String(20), default=CandidateStatus.pending, index=True
    )
    sourcing_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    dedup_hash: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    raw_input: Mapped[dict | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        # Fast claiming query: WHERE run_id = ? AND status = 'pending'
        Index("ix_candidate_run_status", "sourcing_run_id", "status"),
        # Cheap dedup lookups, scoped per user
        Index("ix_candidate_user_dedup", "user_id", "dedup_hash"),
    )
