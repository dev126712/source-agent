"""Artisan research honesty tests.

`artisan_research` used to emit a Finding with ``kind="demand_signal"`` whose
summary admitted the research was "pending". The text was honest; the *kind* was
not — anything filtering on ``kind == "demand_signal"`` (or counting demand
evidence) treated a measurement that was never taken as a real signal.

Same invariant as the wholesale fix: never assert evidence we did not gather,
but never go silent about it either.
"""

from decimal import Decimal

from app.agent.nodes.research import artisan_research
from app.agent.nodes.scoring import _rules_verdict, compute_profit
from app.agent.state import SourcingState
from app.core.enums import InputChannel, SourcingMode
from app.schemas.candidate import ProductCandidateIn


def _candidate(**kw) -> ProductCandidateIn:
    return ProductCandidateIn(
        name="Hand-thrown mug",
        sourcing_mode=SourcingMode.artisan,
        input_channel=InputChannel.text,
        **kw,
    )


def _state(candidate, **kw) -> SourcingState:
    base: SourcingState = {
        "candidate": candidate,
        "sourcing_mode": "artisan",
        "findings": [],
        "sources": [],
        "errors": [],
        "risk_flags": [],
        "should_abort": False,
        "amazon_price": Decimal("50.00"),
    }
    base.update(kw)
    return base


async def test_emits_no_unearned_demand_signal():
    """The regression: an un-researched niche must not surface as a demand signal."""
    out = await artisan_research(_state(_candidate()))

    kinds = [f.kind for f in out["findings"]]
    assert "demand_signal" not in kinds, "must not assert demand it never measured"


async def test_records_why_no_research_ran():
    """Not asserting evidence is only half of it — the gap must be on the record."""
    out = await artisan_research(_state(_candidate()))

    notes = [f for f in out["findings"] if f.kind == "note"]
    assert len(notes) == 1, "the gap must be recorded, not left silent"
    assert "No niche-demand research performed" in notes[0].summary
    assert notes[0].data["researched"] is False


async def test_speculative_risk_is_still_flagged():
    out = await artisan_research(_state(_candidate()))
    assert "artisan demand is speculative until validated" in out["risk_flags"]


async def test_priced_artisan_still_computes_profit():
    """The honesty change must not disturb the deterministic money path:
    sale 50.00 - cost 12.00 - referral 7.50 (15%) - fba 4.75 = 25.75"""
    out = await compute_profit(_state(_candidate(local_price=Decimal("12.00"))))

    assert out["est_profit"] == Decimal("25.75")
    assert "errors" not in out


def test_artisan_can_never_reach_strong():
    """Documents a live structural limit, not a desired behaviour: artisan always
    emits a risk flag, and _rules_verdict requires zero risks for "strong". So an
    artisan candidate cannot return BUY at any margin until the research loop
    lands and the flag becomes conditional."""
    assert _rules_verdict(Decimal("90"), ["artisan demand is speculative until validated"]) == "marginal"
    assert _rules_verdict(Decimal("90"), []) == "strong"
