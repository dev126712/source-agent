from decimal import Decimal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.adapters.csv_adapter import CSVValidationSummary, validate_csv
from app.agent.graph import get_compiled_graph
from app.agent.state import SourcingState
from app.core.config import settings
from app.core.enums import SourcingMode
from app.schemas.candidate import ProductCandidateIn
from app.services import fees

router = APIRouter(prefix="/candidates", tags=["candidates"])


@router.post("/evaluate")
async def evaluate_candidate(candidate: ProductCandidateIn) -> dict:
    """Run one candidate through the agent synchronously (for text/single input).

    Bulk work goes through the Celery path instead; this is for interactive,
    one-off evaluation. The response is deliberately whole: verdict, the
    deterministic profit ledger, and the cited findings/sources so the caller
    can render an auditable trail (see CLAUDE.md rule #6).
    """
    graph = get_compiled_graph()
    initial: SourcingState = {
        "candidate": candidate,
        "sourcing_mode": candidate.sourcing_mode.value,
        "findings": [],
        "sources": [],
        "errors": [],
        "risk_flags": [],
        "should_abort": False,
    }
    final = await graph.ainvoke(initial)
    return {
        "verdict": final.get("verdict"),
        "reasoning": final.get("reasoning"),
        "sourcing_mode": candidate.sourcing_mode.value,
        # identity
        "resolved_asin": final.get("resolved_asin"),
        "resolved_title": final.get("resolved_title"),
        "resolved_category": final.get("resolved_category"),
        "identity_confidence": final.get("identity_confidence"),
        # amazon-side
        "bsr": final.get("bsr"),
        "offer_count": final.get("offer_count"),
        # economics (all computed in Python — never by the LLM)
        "est_margin_pct": _dec(final.get("est_margin_pct")),
        "est_profit": _dec(final.get("est_profit")),
        "ledger": _ledger(final),
        # evidence
        "risk_flags": final.get("risk_flags", []),
        "findings": [f.model_dump() for f in final.get("findings", [])],
        "sources": [s.model_dump() for s in final.get("sources", [])],
        "errors": final.get("errors", []),
    }


def _ledger(final: SourcingState) -> dict | None:
    """Expose the deterministic profit breakdown line by line.

    Every value here is derived from numbers the graph already computed in
    Python; nothing is recomputed by an LLM or the frontend.
    """
    sale = final.get("amazon_price")
    if sale is None:
        return None
    cents = Decimal("0.01")
    referral = fees.referral_fee_amount(sale, final.get("resolved_category")).quantize(cents)
    fba = (final.get("fba_fee") or fees.fba_fee()).quantize(cents)
    net_proceeds = (sale - referral - fba).quantize(cents)
    profit = final.get("est_profit")
    # cost basis is exact from the identity: profit = sale - cost - referral - fba
    cost = (net_proceeds - profit) if profit is not None else None
    roi = (profit / cost * 100).quantize(cents) if (profit is not None and cost) else None
    return {
        "sale_price": _dec(sale),
        "referral_fee": _dec(referral),
        "referral_fee_pct": _dec(fees.referral_fee_pct(final.get("resolved_category")) * 100),
        "fba_fee": _dec(fba),
        "net_proceeds": _dec(net_proceeds),
        "cost_basis": _dec(cost),
        "breakeven": _dec(final.get("breakeven_price")),
        "profit": _dec(profit),
        "roi_pct": _dec(roi),
    }


@router.post("/csv/validate", response_model=CSVValidationSummary)
async def validate_csv_upload(
    file: UploadFile = File(...),
    sourcing_mode: SourcingMode = Form(...),
) -> CSVValidationSummary:
    """Phase 1 of bulk upload: validate and preview before enqueuing."""
    raw = await file.read()
    try:
        return validate_csv(
            raw, sourcing_mode=sourcing_mode, max_rows=settings.max_candidates_per_csv
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


def _dec(v) -> float | None:
    return float(v) if v is not None else None
