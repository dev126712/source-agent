"""Discovery orchestrator.

Runs the location-based prospecting loop:
  seed -> expand categories -> discover stores -> fetch products
       -> filter against seen-memory -> emit ProductCandidates.

The emitted candidates are the same canonical type the evaluation graph consumes,
so discovery chains straight into the existing profit/verdict pipeline.

The same code path serves both on-demand calls and (for premium users) a future
scheduled trigger — only `triggered_by` differs.
"""

import random
import uuid
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.retailers import (
    RetailerProduct,
    get_retailer_adapters,
)
from app.core.enums import InputChannel, SourcingMode
from app.schemas.candidate import ProductCandidateIn
from app.services import seed_expansion, seen_memory


@dataclass
class DiscoveryRequest:
    user_id: uuid.UUID
    province: str
    seed: str | None = None
    exploration: float = 0.5
    category_count: int = 4
    stores_per_retailer: int = 5
    products_per_store: int = 25
    triggered_by: str = "on_demand"
    retailers: list[str] | None = None


@dataclass
class DiscoveryResult:
    categories: list[str]
    stores_found: int
    products_seen: int
    candidates: list[ProductCandidateIn] = field(default_factory=list)


def _to_candidate(p: RetailerProduct) -> ProductCandidateIn:
    return ProductCandidateIn(
        name=p.name,
        upc=p.upc,
        url=p.url,
        brand=p.brand,
        category_hint=p.category,
        local_price=p.price,
        source_name=p.retailer,
        sourcing_mode=SourcingMode.retail_arb,
        input_channel=InputChannel.discovery,
        raw_input=p.model_dump(mode="json"),
    )


async def run_discovery(
    session: AsyncSession,
    req: DiscoveryRequest,
    *,
    rng: random.Random | None = None,
) -> DiscoveryResult:
    rng = rng or random.Random()

    # 1. Expand the loose seed into concrete categories (looseness lives here).
    categories = seed_expansion.expand_categories(
        seed=req.seed,
        exploration=req.exploration,
        n=req.category_count,
        rng=rng,
    )

    adapters = get_retailer_adapters(req.retailers)

    # 2. Discover stores in the province across all live retailers.
    all_products: list[RetailerProduct] = []
    stores_found = 0
    for adapter in adapters:
        stores = await adapter.find_stores(
            province=req.province, limit=req.stores_per_retailer
        )
        stores_found += len(stores)
        # 3. Fetch products per store per category.
        for store in stores:
            for category in categories:
                products = await adapter.search_products(
                    store_id=store.store_id,
                    category=category,
                    limit=req.products_per_store,
                )
                all_products.extend(products)

    products_seen = len(all_products)

    # 4. Filter against the user's seen-memory (TTL-aware) + in-batch dedup.
    keys = [p.stable_id() for p in all_products]
    seen_keys = await seen_memory.load_seen_keys(
        session, user_id=req.user_id, keys=keys
    )
    fresh = seen_memory.filter_unseen(all_products, seen_keys)

    # 5. Record the fresh ones so future runs won't repeat them (until TTL).
    await seen_memory.record_seen(session, user_id=req.user_id, products=fresh)

    # 6. Emit canonical candidates for the evaluation graph.
    candidates = [_to_candidate(p) for p in fresh]

    return DiscoveryResult(
        categories=categories,
        stores_found=stores_found,
        products_seen=products_seen,
        candidates=candidates,
    )
