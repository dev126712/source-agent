"""Retailer adapter abstraction.

Same idea as PostBridge's PlatformAdapter, but for *sourcing* retailers instead
of *publishing* platforms. Each retailer (Walmart, etc.) is one adapter behind a
common interface. Reality check: most retailers gate product/inventory APIs
behind partner approval, so expect to launch with a mock + one real adapter and
roll out others behind this same interface over time.
"""

import re
from abc import ABC, abstractmethod
from decimal import Decimal

import httpx
from pydantic import BaseModel

from app.core.config import settings


class RetailerAPIError(RuntimeError):
    """A retailer call failed. Raised rather than returning [] — an empty list is
    indistinguishable from 'this store genuinely stocks nothing', and a silent
    empty result would quietly hollow out a discovery run."""


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

    @classmethod
    def is_configured(cls) -> bool:
        """Whether this adapter has what it needs to run (credentials, etc.).
        Unconfigured adapters are left out of the default set."""
        return True

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


class BestBuyRetailer(RetailerAdapter):
    """Best Buy Developer API (https://api.bestbuy.com/v1).

    Auth is a plain `apiKey` query parameter. Filters live in a parenthesised
    segment of the *path*, not the query string:

        /v1/stores(region=MN)?format=json&pageSize=10&apiKey=…
        /v1/products(search=kitchen&search=gadgets)?format=json&pageSize=25&apiKey=…

    KNOWN LIMITATION — `search_products` is not store-scoped. The Products
    endpoint has no per-store inventory filter; `inStoreAvailability` is a
    chain-wide boolean, not "on the shelf at store 1118". `store_id` is
    therefore accepted for interface conformance and used only to keep the
    result attributable, NOT to filter inventory. Treat the output as "carried
    in stores in this region", not "in stock at this store". Per-store
    availability needs the invite-only Commerce API.
    """

    name = "bestbuy"

    # Only what we map, to keep responses small.
    _PRODUCT_FIELDS = (
        "sku,upc,name,manufacturer,salePrice,regularPrice,url,inStoreAvailability"
    )

    @classmethod
    def is_configured(cls) -> bool:
        return bool(settings.bestbuy_api_key)

    async def _get(self, path: str, params: dict) -> dict:
        if not settings.bestbuy_api_key:
            raise RetailerAPIError(
                "BESTBUY_API_KEY is not set; cannot call the Best Buy API"
            )
        url = f"{settings.bestbuy_base_url}{path}"
        params = {**params, "format": "json", "apiKey": settings.bestbuy_api_key}
        try:
            async with httpx.AsyncClient(
                timeout=settings.retailer_timeout_seconds
            ) as client:
                resp = await client.get(url, params=params)
        except httpx.HTTPError as exc:  # network, DNS, timeout
            raise RetailerAPIError(f"Best Buy request failed: {exc}") from exc

        if resp.status_code == 403:
            raise RetailerAPIError(
                "Best Buy rejected the API key (403). Check BESTBUY_API_KEY."
            )
        if resp.status_code != 200:
            raise RetailerAPIError(
                f"Best Buy returned HTTP {resp.status_code} for {path}"
            )
        try:
            return resp.json()
        except ValueError as exc:
            raise RetailerAPIError("Best Buy returned a non-JSON body") from exc

    async def find_stores(self, *, province: str, limit: int = 10) -> list[RetailerStore]:
        region = province.strip().upper()
        if not re.fullmatch(r"[A-Z]{2}", region):
            # Fail loudly: the API would just return zero stores, which reads as
            # "no stores here" rather than "you asked the wrong question". The
            # app currently ships Canadian province names, which this API — a US
            # service — cannot resolve.
            raise RetailerAPIError(
                f"Best Buy expects a 2-letter US state code for region, got "
                f"{province!r}. This adapter cannot serve Canadian provinces."
            )

        data = await self._get(
            f"/stores(region={region})",
            {"pageSize": min(max(limit, 1), 100), "show": "storeId,name,region,city,lat,lng"},
        )
        return [
            RetailerStore(
                retailer=self.name,
                store_id=str(s["storeId"]),
                name=s.get("name") or f"Best Buy {s.get('city', region)}",
                province=s.get("region") or region,
                lat=s.get("lat"),
                lng=s.get("lng"),
            )
            for s in data.get("stores", [])
        ]

    async def search_products(
        self, *, store_id: str, category: str, limit: int = 25
    ) -> list[RetailerProduct]:
        terms = _search_terms(category)
        if not terms:
            return []
        # Each word becomes its own `search=` clause (the documented way to
        # express a multi-word query); clauses AND together.
        clauses = "&".join(f"search={t}" for t in terms)
        data = await self._get(
            f"/products({clauses}&inStoreAvailability=true)",
            {"pageSize": min(max(limit, 1), 100), "show": self._PRODUCT_FIELDS},
        )

        out: list[RetailerProduct] = []
        for p in data.get("products", []):
            sku = p.get("sku")
            if sku is None:
                continue  # sku is our identity fallback; without it we cannot dedup
            out.append(
                RetailerProduct(
                    retailer=self.name,
                    sku=str(sku),
                    upc=p.get("upc") or None,
                    name=p.get("name") or f"SKU {sku}",
                    brand=p.get("manufacturer"),
                    category=category,
                    price=_money(p.get("salePrice"), p.get("regularPrice")),
                    in_stock=bool(p.get("inStoreAvailability", False)),
                    url=p.get("url"),
                )
            )
        return out


def _search_terms(category: str) -> list[str]:
    """Split a loose category into Best Buy search words.

    Strips anything that would be read as filter syntax (& | ( ) = " ,) — an
    unescaped one of those would silently change the query's meaning.
    """
    cleaned = re.sub(r"[^A-Za-z0-9\s-]", " ", category or "")
    return [w for w in cleaned.split() if w]


def _money(sale, regular) -> Decimal | None:
    """Prefer sale price, fall back to regular. Via str() — going through float
    would reintroduce binary artifacts into money (rule #5)."""
    for v in (sale, regular):
        if v is not None:
            try:
                return Decimal(str(v))
            except ArithmeticError:
                continue
    return None


_REGISTRY: dict[str, type[RetailerAdapter]] = {
    MockRetailer.name: MockRetailer,
    BestBuyRetailer.name: BestBuyRetailer,
}


def get_retailer_adapters(names: list[str] | None = None) -> list[RetailerAdapter]:
    """Return live adapter instances.

    Default set = every *configured* real adapter, falling back to the mock when
    none are. That keeps `docker compose up` working with zero credentials while
    letting a single env var switch discovery onto real data. An explicitly
    requested adapter is returned even if unconfigured, so the caller gets a
    clear RetailerAPIError instead of a silently empty run.
    """
    if names:
        return [_REGISTRY[n]() for n in names if n in _REGISTRY]

    real = [
        cls
        for n, cls in _REGISTRY.items()
        if n != MockRetailer.name and cls.is_configured()
    ]
    return [cls() for cls in real] if real else [MockRetailer()]
