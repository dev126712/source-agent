"""Final nodes: deterministic profit math, then LLM verdict synthesis."""

from decimal import Decimal

from app.agent.state import SourcingState
from app.services import fees


async def compute_profit(state: SourcingState) -> dict:
    """Pure arithmetic. No LLM — a wrong margin that looks authoritative is
    worse than no margin at all."""
    if state.get("should_abort"):
        return {}

    sale_price = state.get("amazon_price")
    if sale_price is None:
        return {"errors": ["no sale price; cannot compute profit"]}

    # Cost basis: local price for arbitrage, or wholesale unit price from findings.
    cost = _cost_basis(state)

    referral = fees.referral_fee_amount(sale_price, state.get("resolved_category"))
    fba = state.get("fba_fee") or fees.fba_fee()
    total_fees = referral + fba

    breakeven = cost + total_fees if cost is not None else None
    profit = (sale_price - cost - total_fees) if cost is not None else None
    margin = (
        (profit / sale_price * Decimal(100)).quantize(Decimal("0.01"))
        if profit is not None and sale_price > 0
        else None
    )

    return {
        "est_profit": profit.quantize(Decimal("0.01")) if profit is not None else None,
        "est_margin_pct": margin,
        "breakeven_price": (
            breakeven.quantize(Decimal("0.01")) if breakeven is not None else None
        ),
    }


def _cost_basis(state: SourcingState) -> Decimal | None:
    c = state["candidate"]
    if c.local_price is not None:
        return c.local_price
    for f in state.get("findings", []):
        if f.kind == "supplier" and f.data and f.data.get("unit_price") is not None:
            return Decimal(str(f.data["unit_price"]))
    return None


async def score_and_report(state: SourcingState) -> dict:
    """Synthesize a verdict from accumulated state.

    This is the one post-routing node that uses the LLM — but only for
    synthesis and explanation, over numbers that were computed deterministically.
    A rules-first verdict is applied so the output is sane even if the LLM call
    is skipped or fails.
    """
    if state.get("should_abort"):
        return {
            "verdict": "avoid",
            "reasoning": "; ".join(state.get("errors", [])) or "could not evaluate",
            "risk_flags": state.get("risk_flags", []),
        }

    margin = state.get("est_margin_pct")
    verdict = _rules_verdict(margin, state.get("risk_flags", []))

    # TODO: call get_llm() to produce human-readable reasoning that cites the
    # specific findings/sources in state. Deterministic fallback below.
    reasoning = _fallback_reasoning(state, verdict, margin)

    return {"verdict": verdict, "reasoning": reasoning}


def _rules_verdict(margin: Decimal | None, risks: list[str]) -> str:
    if margin is None:
        return "avoid"
    if margin >= Decimal("25") and len(risks) == 0:
        return "strong"
    if margin >= Decimal("15"):
        return "marginal"
    return "avoid"


def _fallback_reasoning(state: SourcingState, verdict: str, margin) -> str:
    parts = [f"Verdict: {verdict}."]
    if margin is not None:
        parts.append(f"Estimated margin {margin}%.")
    if state.get("bsr") is not None:
        parts.append(f"BSR {state['bsr']}.")
    if state.get("risk_flags"):
        parts.append("Risks: " + "; ".join(state["risk_flags"]) + ".")
    return " ".join(parts)
