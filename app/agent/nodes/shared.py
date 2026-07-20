"""Shared graph nodes: identification, Amazon data pull, and routing.

These run for every candidate regardless of sourcing mode.
"""

from app.agent.state import SourceRef, SourcingState
from app.providers.amazon import get_amazon_provider
from app.services import fees

IDENTITY_CONFIDENCE_THRESHOLD = 0.4


async def identify_product(state: SourcingState) -> dict:
    """Resolve the fuzzy candidate to a concrete product / ASIN.

    In production this binds UPC lookup + web_search (+ vision for photos).
    Here we derive confidence from which identifiers are present: a UPC or
    ASIN is high-confidence, a bare name is lower.
    """
    c = state["candidate"]

    if c.asin:
        confidence = 0.95
    elif c.upc:
        confidence = 0.85
    elif c.name and c.brand:
        confidence = 0.6
    elif c.name:
        confidence = 0.45
    else:
        confidence = 0.2  # url-only, needs a fetch to resolve

    should_abort = confidence < IDENTITY_CONFIDENCE_THRESHOLD

    return {
        "resolved_asin": c.asin,
        "resolved_title": c.name,
        "identity_confidence": confidence,
        "should_abort": should_abort,
        "errors": (["identity confidence below threshold"] if should_abort else []),
    }


async def fetch_amazon_data(state: SourcingState) -> dict:
    """Pull Amazon-side data. LLM-free by design — deterministic and cheap."""
    if state.get("should_abort"):
        return {}

    c = state["candidate"]
    provider = get_amazon_provider()
    data = await provider.lookup(asin=c.asin, upc=c.upc, name=c.name)

    if not data.found:
        return {
            "should_abort": True,
            "errors": ["no matching Amazon listing found"],
        }

    return {
        "resolved_asin": data.asin,
        "resolved_title": data.title or state.get("resolved_title"),
        "resolved_category": data.category,
        "amazon_price": data.price,
        "bsr": data.bsr,
        "offer_count": data.offer_count,
        "referral_fee_pct": fees.referral_fee_pct(data.category),
        "fba_fee": fees.fba_fee(),
        "sources": [
            SourceRef(url="amazon-data-provider", used_for="price, bsr, offers")
        ],
    }


def route_by_mode(state: SourcingState) -> str:
    """Conditional edge target after fetch_amazon_data."""
    if state.get("should_abort"):
        return "score_and_report"
    return {
        "retail_arb": "retail_arb_research",
        "wholesale": "wholesale_research",
        "artisan": "artisan_research",
    }[state["sourcing_mode"]]
