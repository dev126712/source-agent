"""Seen-product memory.

Guarantees a user never sees the same exact product twice *within the TTL
window*. After expiry, products may resurface, so a location is never
permanently exhausted (the 1b choice).
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.retailers import RetailerProduct
from app.models.discovery import SeenProduct

DEFAULT_TTL_DAYS = 90


def filter_unseen(
    products: list[RetailerProduct], seen_keys: set[str]
) -> list[RetailerProduct]:
    """Pure function: drop any product whose stable_id is in the seen set.

    In-run dedup is included too — the same product from two stores collapses.
    """
    out: list[RetailerProduct] = []
    batch_keys: set[str] = set()
    for p in products:
        key = p.stable_id()
        if key in seen_keys or key in batch_keys:
            continue
        batch_keys.add(key)
        out.append(p)
    return out


async def load_seen_keys(
    session: AsyncSession, *, user_id: uuid.UUID, keys: list[str]
) -> set[str]:
    """Return the subset of `keys` this user has seen and that hasn't expired."""
    if not keys:
        return set()
    now = datetime.now(timezone.utc)
    stmt = select(SeenProduct.product_key).where(
        SeenProduct.user_id == user_id,
        SeenProduct.product_key.in_(keys),
        SeenProduct.expires_at > now,
    )
    rows = await session.execute(stmt)
    return {r[0] for r in rows}


async def record_seen(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    products: list[RetailerProduct],
    ttl_days: int = DEFAULT_TTL_DAYS,
) -> None:
    """Persist newly surfaced products with a fresh expiry. Upsert refreshes TTL
    on re-encounter so an actively-recurring product stays suppressed."""
    if not products:
        return
    expires = datetime.now(timezone.utc) + timedelta(days=ttl_days)
    values = [
        {
            "id": uuid.uuid4(),
            "user_id": user_id,
            "product_key": p.stable_id(),
            "expires_at": expires,
        }
        for p in products
    ]
    stmt = pg_insert(SeenProduct).values(values)
    # If the same (user, key) shows up again, push the expiry out rather than error.
    stmt = stmt.on_conflict_do_update(
        index_elements=[SeenProduct.user_id, SeenProduct.product_key],
        set_={"expires_at": expires, "seen_at": datetime.now(timezone.utc)},
    )
    await session.execute(stmt)
