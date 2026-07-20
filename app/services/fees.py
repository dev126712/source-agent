"""Deterministic Amazon fee logic.

These numbers feed profit math, so they must never be produced by an LLM.
Maintain this ruleset by hand against Amazon's published fee schedules.
The values below are illustrative placeholders — verify before production use.
"""

from decimal import Decimal

# Referral fee % by category (simplified; Amazon has ~30 categories).
REFERRAL_FEE_PCT: dict[str, Decimal] = {
    "Home & Kitchen": Decimal("0.15"),
    "Electronics": Decimal("0.08"),
    "Toys & Games": Decimal("0.15"),
    "Beauty": Decimal("0.15"),
    "Grocery": Decimal("0.08"),
    "Clothing": Decimal("0.17"),
    "_default": Decimal("0.15"),
}

# FBA fulfilment fee by rough size/weight tier. Real tiers depend on
# dimensions + weight; this is a stand-in until dimension data is wired in.
FBA_FEE_BY_TIER: dict[str, Decimal] = {
    "small_standard": Decimal("3.22"),
    "large_standard": Decimal("4.75"),
    "large_bulky": Decimal("9.50"),
    "_default": Decimal("4.75"),
}

MIN_REFERRAL_FEE = Decimal("0.30")


def referral_fee_pct(category: str | None) -> Decimal:
    return REFERRAL_FEE_PCT.get(category or "_default", REFERRAL_FEE_PCT["_default"])


def fba_fee(tier: str = "_default") -> Decimal:
    return FBA_FEE_BY_TIER.get(tier, FBA_FEE_BY_TIER["_default"])


def referral_fee_amount(sale_price: Decimal, category: str | None) -> Decimal:
    pct = referral_fee_pct(category)
    return max(sale_price * pct, MIN_REFERRAL_FEE)
