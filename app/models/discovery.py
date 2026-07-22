import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class SeenProduct(Base):
    """Per-user memory of products already surfaced by discovery.

    The filter excludes rows where expires_at is still in the future, so a
    location is never permanently exhausted — old products resurface after TTL.
    """

    __tablename__ = "seen_products"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    product_key: Mapped[str] = mapped_column(String(64))  # RetailerProduct.stable_id()
    seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    __table_args__ = (
        # The hot path: "have I seen this key, still un-expired, for this user?"
        # Unique because record_seen upserts on this pair to refresh the TTL —
        # ON CONFLICT needs a matching unique constraint to target.
        Index("ix_seen_user_key", "user_id", "product_key", unique=True),
    )


class DiscoveryRun(Base):
    """One location-based discovery pass. Groups the candidates it produced."""

    __tablename__ = "discovery_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    province: Mapped[str] = mapped_column(String(64))
    seed: Mapped[str | None] = mapped_column(String(256))  # the loose vibe, if any
    categories: Mapped[list | None] = mapped_column(String(512))  # expanded, csv
    exploration: Mapped[float] = mapped_column(String(8), default="0.5")
    stores_found: Mapped[int] = mapped_column(Integer, default=0)
    products_seen: Mapped[int] = mapped_column(Integer, default=0)
    products_new: Mapped[int] = mapped_column(Integer, default=0)
    triggered_by: Mapped[str] = mapped_column(String(16), default="on_demand")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
