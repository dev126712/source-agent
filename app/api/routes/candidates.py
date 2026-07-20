import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.adapters.csv_adapter import CSVValidationSummary, validate_csv
from app.agent.graph import get_compiled_graph
from app.agent.state import SourcingState
from app.core.config import settings
from app.core.enums import InputChannel, SourcingMode
from app.schemas.candidate import ProductCandidateIn

router = APIRouter(prefix="/candidates", tags=["candidates"])


@router.post("/evaluate")
async def evaluate_candidate(candidate: ProductCandidateIn) -> dict:
    """Run one candidate through the agent synchronously (for text/single input).

    Bulk work goes through the Celery path instead; this is for interactive,
    one-off evaluation.
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
        "est_margin_pct": _dec(final.get("est_margin_pct")),
        "est_profit": _dec(final.get("est_profit")),
        "reasoning": final.get("reasoning"),
        "risk_flags": final.get("risk_flags", []),
        "resolved_asin": final.get("resolved_asin"),
        "bsr": final.get("bsr"),
        "sources": [s.model_dump() for s in final.get("sources", [])],
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
