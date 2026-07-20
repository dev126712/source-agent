from decimal import Decimal
from operator import add
from typing import Annotated, Literal, TypedDict

from pydantic import BaseModel

from app.schemas.candidate import ProductCandidateIn


class SourceRef(BaseModel):
    url: str
    title: str | None = None
    used_for: str | None = None  # what the agent extracted from it


class Finding(BaseModel):
    kind: Literal["supplier", "demand_signal", "competition", "note"]
    summary: str
    data: dict | None = None  # e.g. {"moq": 100, "unit_price": 4.20}
    source_url: str | None = None


class SourcingState(TypedDict, total=False):
    # --- inputs (set at graph entry) ---
    candidate: ProductCandidateIn
    sourcing_mode: Literal["retail_arb", "wholesale", "artisan"]

    # --- identification ---
    resolved_asin: str | None
    resolved_title: str | None
    resolved_category: str | None
    identity_confidence: float

    # --- amazon data ---
    amazon_price: Decimal | None
    bsr: int | None
    offer_count: int | None
    referral_fee_pct: Decimal | None
    fba_fee: Decimal | None

    # --- research findings (accumulate across nodes) ---
    findings: Annotated[list[Finding], add]
    sources: Annotated[list[SourceRef], add]

    # --- computed economics ---
    est_profit: Decimal | None
    est_margin_pct: Decimal | None
    breakeven_price: Decimal | None

    # --- output ---
    verdict: Literal["strong", "marginal", "avoid"] | None
    risk_flags: list[str]
    reasoning: str | None

    # --- control ---
    errors: Annotated[list[str], add]
    should_abort: bool
