"""Wholesale cost-basis regression tests.

`wholesale_research` used to emit a supplier Finding hardcoded to
``unit_price: None``. That finding could never satisfy ``_cost_basis``, so a
wholesale candidate without a manually typed ``local_price`` — the actual
wholesale use case — always produced ``est_profit=None``, which
``_rules_verdict`` turned into a confident "avoid".

Two invariants are guarded here:
  1. Never emit a supplier finding we cannot price (no fabricated cost basis).
  2. When there is no cost basis, say so explicitly — an unpriced candidate must
     never read as a researched rejection.
"""

from decimal import Decimal

from app.agent.nodes.research import wholesale_research
from app.agent.nodes.scoring import _cost_basis, _rules_verdict, compute_profit
from app.agent.state import Finding, SourcingState
from app.core.enums import InputChannel, SourcingMode
from app.schemas.candidate import ProductCandidateIn


def _candidate(**kw) -> ProductCandidateIn:
    return ProductCandidateIn(
        name="Bulk widgets",
        sourcing_mode=SourcingMode.wholesale,
        input_channel=InputChannel.text,
        **kw,
    )


def _state(candidate, **kw) -> SourcingState:
    base: SourcingState = {
        "candidate": candidate,
        "sourcing_mode": "wholesale",
        "findings": [],
        "sources": [],
        "errors": [],
        "risk_flags": [],
        "should_abort": False,
        "amazon_price": Decimal("50.00"),
    }
    base.update(kw)
    return base


async def test_priced_candidate_yields_a_priced_supplier_finding():
    """The supplier finding must carry a real number, so the ledger's cost basis
    is traceable to cited evidence rather than to an invisible fallback."""
    out = await wholesale_research(_state(_candidate(local_price=Decimal("8.50"), moq=500)))

    findings = out["findings"]
    assert len(findings) == 1
    assert findings[0].kind == "supplier"
    assert findings[0].data["unit_price"] == "8.50"
    assert findings[0].data["moq"] == 500
    assert out["risk_flags"] == []


async def test_unpriced_candidate_emits_no_supplier_finding():
    """The regression itself: no *priced* placeholder finding, and the gap flagged."""
    out = await wholesale_research(_state(_candidate(moq=500)))

    kinds = [f.kind for f in out["findings"]]
    assert "supplier" not in kinds, "must not emit a supplier finding it cannot price"
    assert "supplier unit price not yet researched" in out["risk_flags"]


async def test_unpriced_candidate_still_records_why():
    """An empty evidence trail reads as 'nothing to report'. The run must say
    that supplier search has not run yet — rule #6 (keep the trail intact)."""
    out = await wholesale_research(_state(_candidate(moq=500)))

    notes = [f for f in out["findings"] if f.kind == "note"]
    assert len(notes) == 1, "the gap must be recorded, not left silent"
    assert "No supplier search performed" in notes[0].summary
    assert notes[0].data["researched"] is False
    # and it must still be unusable as a cost basis
    assert _cost_basis(_state(_candidate(), findings=out["findings"])) is None


async def test_missing_moq_is_still_flagged():
    out = await wholesale_research(_state(_candidate(local_price=Decimal("8.50"))))
    assert any("MOQ unknown" in r for r in out["risk_flags"])


def test_cost_basis_resolves_from_a_supplier_finding():
    """This path was dead until the fix — nothing ever produced a non-null
    unit_price. It is the seam real supplier research will plug into, so guard
    it now: cost comes from the finding when there is no local_price."""
    state = _state(
        _candidate(),
        findings=[
            Finding(kind="demand_signal", summary="no price here"),
            Finding(kind="supplier", summary="supplier A", data={"unit_price": "4.20"}),
        ],
    )
    assert _cost_basis(state) == Decimal("4.20")


def test_local_price_takes_precedence_over_findings():
    state = _state(
        _candidate(local_price=Decimal("8.50")),
        findings=[Finding(kind="supplier", summary="s", data={"unit_price": "4.20"})],
    )
    assert _cost_basis(state) == Decimal("8.50")


async def test_profit_computed_from_a_finding_only():
    """sale 50.00 − cost 10.00 − referral 7.50 (15%) − fba 4.75 = 27.75"""
    state = _state(
        _candidate(),
        findings=[Finding(kind="supplier", summary="s", data={"unit_price": "10.00"})],
    )
    out = await compute_profit(state)

    assert out["est_profit"] == Decimal("27.75")
    assert out["breakeven_price"] == Decimal("22.25")
    assert "errors" not in out


async def test_no_cost_basis_reports_an_explicit_error():
    """Silence here is what let an unpriced candidate read as a real rejection."""
    out = await compute_profit(_state(_candidate()))

    assert out["est_profit"] is None
    assert out["est_margin_pct"] is None
    assert out["errors"], "a missing cost basis must be reported, not swallowed"
    assert "cost basis" in out["errors"][0]


def test_unknown_margin_is_not_a_researched_rejection():
    """Documents the remaining sharp edge: `avoid` is still returned when the
    margin is simply unknown. The reasoning string now says so explicitly, but
    the verdict taxonomy has no 'insufficient data' value."""
    assert _rules_verdict(None, []) == "avoid"
