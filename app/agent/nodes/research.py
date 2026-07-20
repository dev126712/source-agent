"""Mode-specific research nodes.

Each has the same signature but different internal logic. These are where the
web-search agent earns its keep. The web_search / web_fetch tool bindings are
left as integration points (marked TODO) — the structure and the accumulation
of Finding / SourceRef objects into state is what matters here.
"""

from decimal import Decimal

from app.agent.state import Finding, SourcingState


async def retail_arb_research(state: SourcingState) -> dict:
    """Local price is already known; confirm the Amazon side is real and sellable."""
    findings: list[Finding] = []
    risk: list[str] = []

    bsr = state.get("bsr")
    offers = state.get("offer_count")

    if bsr is not None:
        # High BSR = slow-moving. Threshold varies wildly by category in reality.
        if bsr > 100_000:
            risk.append(f"high BSR ({bsr}) suggests slow sales")
        findings.append(
            Finding(kind="demand_signal", summary=f"BSR is {bsr}", data={"bsr": bsr})
        )

    if offers is not None and offers > 15:
        risk.append(f"crowded listing ({offers} sellers)")
        findings.append(
            Finding(kind="competition", summary=f"{offers} competing offers")
        )

    return {"findings": findings, "risk_flags": risk}


async def wholesale_research(state: SourcingState) -> dict:
    """Heaviest web-search node: find local suppliers, MOQs, and tier pricing.

    Production: bind web_search + web_fetch and run a ReAct loop up to
    settings.max_research_iterations, appending each supplier as a Finding.
    """
    c = state["candidate"]

    # TODO: replace with real agentic search loop.
    # Placeholder demonstrates the shape of accumulated findings.
    findings = [
        Finding(
            kind="supplier",
            summary=f"Candidate supplier for {c.name or 'product'}",
            data={"moq": c.moq or 100, "unit_price": None},
            source_url=None,
        )
    ]
    risk = []
    if not c.moq:
        risk.append("MOQ unknown; sourcing cost not yet verified")

    return {"findings": findings, "risk_flags": risk}


async def artisan_research(state: SourcingState) -> dict:
    """Gauge Amazon-side demand for the niche and local availability."""
    findings = [
        Finding(
            kind="demand_signal",
            summary="Niche demand assessment pending web research",
            data=None,
        )
    ]
    risk = ["artisan demand is speculative until validated"]
    return {"findings": findings, "risk_flags": risk}
