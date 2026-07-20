"""Retailer adapter abstraction.

Same idea as PostBridge's PlatformAdapter, but for *sourcing* retailers instead
of *publishing* platforms. Each retailer (Walmart, etc.) is one adapter behind a
common interface. Reality check: most retailers gate product/inventory APIs
behind partner approval, so expect to launch with a mock + one real adapter and
roll out others behind this same interface over time.
"""

from abc import ABC, abstractmethod
from decimal import Decimal

from pydantic import BaseModel


class RetailerStore(BaseModel):
    retailer: str
    store_id: str
    name: str
    province: str
    lat: float | None = None
    lng: float | None = None


class RetailerProduct(BaseModel):
    retailer: str
    sku: str                      # retailer's own product id
    upc: str | None = None
    name: str
    brand: str | None = None
    category: str | None = None
    price: Decimal | None = None
    in_stock: bool = True
    url: str | None = None

    def stable_id(self) -> str:
        """Preferred identity for dedup: UPC if present, else retailer:sku."""
        return self.upc or f"{self.retailer}:{self.sku}"


class RetailerAdapter(ABC):
    name: str

    @abstractmethod
    async def find_stores(self, *, province: str, limit: int = 10) -> list[RetailerStore]:
        ...

    @abstractmethod
    async def search_products(
        self, *, store_id: str, category: str, limit: int = 25
    ) -> list[RetailerProduct]:
        ...


class MockRetailer(RetailerAdapter):
    """Deterministic-ish fake data so the discovery loop runs without approvals.

    Product ids incorporate a per-call nonce so repeated runs surface *new* items,
    letting us exercise the seen-memory filter realistically.
    """

    name = "mockmart"

    async def find_stores(self, *, province: str, limit: int = 10) -> list[RetailerStore]:
        return [
            RetailerStore(
                retailer=self.name,
                store_id=f"{self.name}-{province}-{i}",
                name=f"MockMart {province} #{i}",
                province=province,
            )
            for i in range(1, limit + 1)
        ]

    async def search_products(
        self, *, store_id: str, category: str, limit: int = 25
    ) -> list[RetailerProduct]:
        import random

        out: list[RetailerProduct] = []
        for _ in range(limit):
            n = random.randint(10_000_000, 99_999_999)
            out.append(
                RetailerProduct(
                    retailer=self.name,
                    sku=f"SKU{n}",
                    upc=str(600_000_000_000 + n),
                    name=f"{category.title()} item {n % 1000}",
                    category=category,
                    price=Decimal(f"{5 + n % 40}.99"),
                    in_stock=True,
                    url=f"https://mockmart.example/p/{n}",
                )
            )
        return out


_REGISTRY: dict[str, type[RetailerAdapter]] = {
    MockRetailer.name: MockRetailer,
}


def get_retailer_adapters(names: list[str] | None = None) -> list[RetailerAdapter]:
    """Return live adapter instances. Defaults to all registered."""
    chosen = names or list(_REGISTRY.keys())
    return [_REGISTRY[n]() for n in chosen if n in _REGISTRY]
