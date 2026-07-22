"""Best Buy adapter tests.

IMPORTANT: these run against recorded/synthetic payloads via httpx.MockTransport.
They verify request construction and response mapping — they do NOT prove the
adapter works against the live Best Buy service, which has never been called
(no API key was available when this was written). Treat green tests here as
"the shape is right", not "it works in production".
"""

from decimal import Decimal

import httpx
import pytest

from app.adapters import retailers
from app.adapters.retailers import (
    BestBuyRetailer,
    MockRetailer,
    RetailerAPIError,
    _money,
    _search_terms,
    get_retailer_adapters,
)

STORES_PAYLOAD = {
    "from": 1, "to": 2, "total": 2, "currentPage": 1, "totalPages": 1,
    "stores": [
        {"storeId": 1118, "name": "Roseville", "region": "MN", "city": "Roseville",
         "lat": 45.0234, "lng": -93.1567},
        {"storeId": 281, "name": "Richfield", "region": "MN", "city": "Richfield",
         "lat": 44.8756, "lng": -93.2934},
    ],
}

PRODUCTS_PAYLOAD = {
    "from": 1, "to": 2, "total": 2, "currentPage": 1, "totalPages": 1,
    "products": [
        {"sku": 6428324, "upc": "195697123456", "name": "Ninja Air Fryer",
         "manufacturer": "Ninja", "salePrice": 89.99, "regularPrice": 129.99,
         "url": "https://www.bestbuy.com/site/6428324.p", "inStoreAvailability": True},
        # no upc, no salePrice -> exercises both fallbacks
        {"sku": 6501234, "name": "Generic Blender", "manufacturer": "Acme",
         "regularPrice": 39.99, "url": "https://www.bestbuy.com/site/6501234.p",
         "inStoreAvailability": False},
    ],
}


def _adapter(handler, monkeypatch) -> BestBuyRetailer:
    """Wire an httpx.MockTransport in behind the adapter's own client."""
    monkeypatch.setattr(retailers.settings, "bestbuy_api_key", "test-key")
    monkeypatch.setattr(retailers.settings, "bestbuy_base_url", "https://api.bestbuy.com/v1")

    real_client = httpx.AsyncClient

    def _client(*a, **kw):
        return real_client(transport=httpx.MockTransport(handler), **kw)

    monkeypatch.setattr(retailers.httpx, "AsyncClient", _client)
    return BestBuyRetailer()


# --------------------------------------------------------------------------
# request construction
# --------------------------------------------------------------------------

async def test_find_stores_builds_the_region_filter_and_maps_fields(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json=STORES_PAYLOAD)

    stores = await _adapter(handler, monkeypatch).find_stores(province="mn", limit=5)

    assert "/stores(region=MN)" in seen["url"], "filter belongs in the path, not the query"
    assert "apiKey=test-key" in seen["url"]
    assert "format=json" in seen["url"]
    assert "pageSize=5" in seen["url"]

    assert [s.store_id for s in stores] == ["1118", "281"]
    assert stores[0].retailer == "bestbuy"
    assert stores[0].province == "MN"
    assert stores[0].lat == pytest.approx(45.0234)


async def test_multi_word_category_becomes_multiple_search_clauses(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(httpx.URL(str(request.url)))
        return httpx.Response(200, json=PRODUCTS_PAYLOAD)

    await _adapter(handler, monkeypatch).search_products(
        store_id="1118", category="kitchen gadgets", limit=25
    )

    url = httpx.URL(seen["url"]).path
    assert "search=kitchen" in url and "search=gadgets" in url
    assert "inStoreAvailability=true" in url


async def test_search_terms_strips_filter_syntax():
    """An unescaped & | ( ) = or " would silently change the query's meaning."""
    assert _search_terms("kitchen gadgets") == ["kitchen", "gadgets"]
    assert _search_terms('home & garden (indoor)') == ["home", "garden", "indoor"]
    assert _search_terms("a=b|c") == ["a", "b", "c"]
    assert _search_terms("   ") == []


async def test_empty_category_makes_no_request(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("should not have issued a request")

    out = await _adapter(handler, monkeypatch).search_products(
        store_id="1118", category="!!!", limit=10
    )
    assert out == []


# --------------------------------------------------------------------------
# response mapping
# --------------------------------------------------------------------------

async def test_products_map_to_retailer_products(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=PRODUCTS_PAYLOAD)

    products = await _adapter(handler, monkeypatch).search_products(
        store_id="1118", category="kitchen"
    )

    assert len(products) == 2
    a, b = products
    assert a.sku == "6428324"
    assert a.upc == "195697123456"
    assert a.brand == "Ninja"
    assert a.price == Decimal("89.99"), "sale price wins over regular"
    assert a.in_stock is True
    assert a.stable_id() == "195697123456", "UPC is the dedup identity"

    assert b.upc is None
    assert b.price == Decimal("39.99"), "falls back to regularPrice"
    assert b.in_stock is False
    assert b.stable_id() == "bestbuy:6501234", "no UPC -> retailer:sku fallback"


def test_money_never_goes_through_float():
    """Rule #5: money is Decimal. Decimal(str(x)) avoids binary artifacts."""
    assert _money(0.1, None) == Decimal("0.1")
    assert _money(None, 19.99) == Decimal("19.99")
    assert _money(None, None) is None
    # the float trap this guards against
    assert _money(0.1, None) + _money(0.2, None) == Decimal("0.3")


async def test_product_without_sku_is_skipped(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"products": [{"name": "orphan"}]})

    out = await _adapter(handler, monkeypatch).search_products(
        store_id="1", category="x"
    )
    assert out == [], "sku is the dedup fallback; a product without one is unusable"


# --------------------------------------------------------------------------
# failure modes — must be loud, never a silent empty list
# --------------------------------------------------------------------------

async def test_canadian_province_fails_loudly(monkeypatch):
    """The app ships Ontario/Québec/BC; this US API cannot resolve them. Returning
    [] would read as 'no stores here' rather than 'wrong question'."""
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("should not have issued a request")

    with pytest.raises(RetailerAPIError, match="Canadian provinces"):
        await _adapter(handler, monkeypatch).find_stores(province="Ontario")


async def test_403_names_the_api_key(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": "nope"})

    with pytest.raises(RetailerAPIError, match="BESTBUY_API_KEY"):
        await _adapter(handler, monkeypatch).find_stores(province="MN")


async def test_http_error_is_wrapped(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out")

    with pytest.raises(RetailerAPIError, match="request failed"):
        await _adapter(handler, monkeypatch).find_stores(province="MN")


async def test_missing_key_raises_before_any_request(monkeypatch):
    monkeypatch.setattr(retailers.settings, "bestbuy_api_key", "")
    with pytest.raises(RetailerAPIError, match="not set"):
        await BestBuyRetailer().find_stores(province="MN")


# --------------------------------------------------------------------------
# registry wiring — the zero-credential default must survive
# --------------------------------------------------------------------------

def test_defaults_to_mock_when_unconfigured(monkeypatch):
    monkeypatch.setattr(retailers.settings, "bestbuy_api_key", "")
    adapters = get_retailer_adapters()
    assert [a.name for a in adapters] == [MockRetailer.name]


def test_configured_key_switches_discovery_to_the_real_adapter(monkeypatch):
    monkeypatch.setattr(retailers.settings, "bestbuy_api_key", "test-key")
    adapters = get_retailer_adapters()
    assert [a.name for a in adapters] == [BestBuyRetailer.name]


def test_explicit_request_wins_over_configuration(monkeypatch):
    monkeypatch.setattr(retailers.settings, "bestbuy_api_key", "")
    adapters = get_retailer_adapters(["bestbuy"])
    assert [a.name for a in adapters] == ["bestbuy"], (
        "an explicitly named adapter is returned even unconfigured, so the caller "
        "gets a clear error rather than a silently empty run"
    )
