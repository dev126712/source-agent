"""Mode-specific research nodes.

Each has the same signature but different internal logic. These are where the
web-search agent earns its keep. The web_search / web_fetch tool bindings are
left as integration points (marked TODO) — the structure and the accumulation
of Finding / SourceRef objects into state is what matters here.
"""

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
    findings: list[Finding] = []
    risk: list[str] = []

    # The only supplier cost we can substantiate today is the one supplied with
    # the candidate. Emit a *priced* supplier finding only when we actually have
    # a price — never a placeholder one. A finding carrying unit_price=None can
    # never satisfy _cost_basis, so it added nothing but noise to the evidence
    # trail, and inventing a number here would manufacture an authoritative
    # margin out of thin air (rule #1).
    if c.local_price is not None:
        findings.append(
            Finding(
                kind="supplier",
                summary=(
                    f"Supplier unit price supplied with the candidate for "
                    f"{c.name or 'product'}"
                ),
                data={"moq": c.moq, "unit_price": str(c.local_price)},
                source_url=c.url,
            )
        )
    else:
        # Record the gap rather than going silent. An empty evidence trail reads
        # as "nothing to report"; this says "supplier search has not run yet",
        # which is the actual state of the world (rule #6).
        findings.append(
            Finding(
                kind="note",
                summary=(
                    "No supplier search performed — the agentic supplier/MOQ "
                    "research loop is not yet implemented, and no unit price "
                    "was supplied with the candidate."
                ),
                data={"unit_price": None, "researched": False},
            )
        )
        risk.append("supplier unit price not yet researched")

    if not c.moq:
        risk.append("MOQ unknown; sourcing cost not yet verified")

    return {"findings": findings, "risk_flags": risk}


async def artisan_research(state: SourcingState) -> dict:
    """Gauge Amazon-side demand for the niche and local availability.

    Production: bind web_search + web_fetch to assess niche demand and local
    availability, appending each signal as a Finding.
    """
    # TODO: replace with real agentic search loop.
    # Recorded as a `note`, not a `demand_signal`. The old placeholder claimed
    # the latter, so anything filtering on kind == "demand_signal" counted a
    # measurement that was never taken (rule #6).
    findings: list[Finding] = [
        Finding(
            kind="note",
            summary=(
                "No niche-demand research performed — the artisan demand / "
                "local availability research loop is not yet implemented."
            ),
            data={"researched": False},
        )
    ]
    risk = ["artisan demand is speculative until validated"]
    return {"findings": findings, "risk_flags": risk}
