import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import SubscriptionTier
from app.db.session import get_session
from app.services.discovery import DiscoveryRequest, run_discovery

router = APIRouter(prefix="/discovery", tags=["discovery"])


class DiscoverIn(BaseModel):
    province: str
    seed: str | None = None
    exploration: float = Field(0.5, ge=0.0, le=1.0)
    category_count: int = Field(4, ge=1, le=12)


class DiscoverOut(BaseModel):
    categories: list[str]
    stores_found: int
    products_seen: int
    products_new: int
    candidates: list[dict]


# Placeholder for real auth; wired to JWT (httponly cookie) like ApplyOps later.
async def current_user_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


async def current_tier() -> SubscriptionTier:
    return SubscriptionTier.free


@router.post("/run", response_model=DiscoverOut)
async def discover(
    body: DiscoverIn,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(current_user_id),
) -> DiscoverOut:
    """On-demand location discovery. Returns fresh (never-before-seen) candidates."""
    req = DiscoveryRequest(
        user_id=user_id,
        province=body.province,
        seed=body.seed,
        exploration=body.exploration,
        category_count=body.category_count,
        triggered_by="on_demand",
    )
    result = await run_discovery(session, req)
    return DiscoverOut(
        categories=result.categories,
        stores_found=result.stores_found,
        products_seen=result.products_seen,
        products_new=len(result.candidates),
        candidates=[c.model_dump(mode="json") for c in result.candidates],
    )


@router.post("/schedule")
async def schedule_discovery(
    body: DiscoverIn,
    user_id: uuid.UUID = Depends(current_user_id),
    tier: SubscriptionTier = Depends(current_tier),
) -> dict:
    """Premium-only: register a recurring discovery. Same code path as /run,
    invoked by Celery beat. Gated here."""
    if tier != SubscriptionTier.premium:
        raise HTTPException(
            status_code=402,
            detail="Scheduled discovery requires a premium subscription",
        )
    # TODO: persist a schedule row; Celery beat picks it up and calls run_discovery
    # with triggered_by="scheduled".
    return {"status": "scheduled", "province": body.province}
