"""Amazon data provider abstraction.

Swap Keepa / SP-API / mock behind one interface so the agent never depends
on a specific data source. Only the mock is implemented here; the others are
stubbed with the same signature.
"""

from abc import ABC, abstractmethod
from decimal import Decimal

from pydantic import BaseModel

from app.core.config import settings


class AmazonProductData(BaseModel):
    asin: str | None = None
    title: str | None = None
    category: str | None = None
    price: Decimal | None = None
    bsr: int | None = None
    offer_count: int | None = None
    found: bool = True


class AmazonDataProvider(ABC):
    @abstractmethod
    async def lookup(
        self, *, asin: str | None = None, upc: str | None = None, name: str | None = None
    ) -> AmazonProductData: ...


class MockAmazonProvider(AmazonDataProvider):
    """Deterministic fake data so the pipeline runs without credentials."""

    async def lookup(self, *, asin=None, upc=None, name=None) -> AmazonProductData:
        seed = asin or upc or name or "unknown"
        h = abs(hash(seed))
        return AmazonProductData(
            asin=asin or f"B0{h % 100000000:08d}",
            title=name or "Sample product",
            category="Home & Kitchen",
            price=Decimal(f"{15 + h % 60}.99"),
            bsr=1000 + h % 90000,
            offer_count=1 + h % 25,
            found=True,
        )


class KeepaProvider(AmazonDataProvider):
    def __init__(self, api_key: str):
        self.api_key = api_key

    async def lookup(self, *, asin=None, upc=None, name=None) -> AmazonProductData:
        # TODO: implement Keepa /product endpoint call via httpx
        raise NotImplementedError("Keepa provider not yet implemented")


def get_amazon_provider() -> AmazonDataProvider:
    if settings.amazon_provider == "mock":
        return MockAmazonProvider()
    if settings.amazon_provider == "keepa":
        return KeepaProvider(settings.keepa_api_key)
    raise ValueError(f"Unsupported amazon_provider: {settings.amazon_provider}")
