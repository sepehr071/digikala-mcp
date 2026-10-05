import pytest

pytestmark = [pytest.mark.anyio, pytest.mark.live]

SELLER = "CGDG9"


async def call(client, name, args):
    result = await client.call_tool(name, args)
    assert not result.is_error, result.content[0].text
    return result.structured_content


async def text_size(client, name, args):
    """Bytes of the text content the model reads (the SDK pretty-prints it, so it is larger than the JSON)."""
    result = await client.call_tool(name, args)
    assert not result.is_error, result.content[0].text
    return sum(len(c.text.encode()) for c in result.content)


def prices(data):
    return [p["price"] for p in data["products"]]


async def test_dk_search(client):
    data = await call(client, "dk_search", {"query": "گوشی سامسونگ", "sort": "cheapest", "min_price": 5000000})
    assert data["products"] and all(p["in_stock"] and p["price"] >= 5000000 for p in data["products"])
    assert prices(data) == sorted(prices(data))
    assert await text_size(client, "dk_search", {"query": "گوشی سامسونگ"}) < 15000


async def test_dk_search_flags_loose_matches(client):
    data = await call(client, "dk_search", {"query": "گوشی سامسونگ"})
    assert data["matches"]["all"] > 0 and all("match" in p for p in data["products"])
    nonsense = await call(client, "dk_search", {"query": "zxqv blorptastic"})
    assert not nonsense["matches"]["all"]


async def test_dk_filters_then_filtered_browse(client):
    f = await call(client, "dk_filters", {"category_code": "mobile-phone"})
    assert f["brands"] and f["colors"] and f["price_range"]["min"] < f["price_range"]["max"]
    os_ = next(a for a in f["attributes"] if a["id"] == 2226)  # operating system
    android = os_["values"]["Android"]
    plain = await call(client, "dk_category_products", {"category_code": "mobile-phone"})
    only = await call(
        client, "dk_category_products", {"category_code": "mobile-phone", "attributes": {2226: [android]}}
    )
    assert 0 < only["total"] < plain["total"]
    by_seller = await call(client, "dk_category_products", {"category_code": "mobile-phone", "seller_type": "digikala"})
    assert 0 < by_seller["total"] < plain["total"]
    assert await text_size(client, "dk_filters", {"category_code": "mobile-phone"}) < 15000
    q = await call(client, "dk_filters", {"query": "هدفون بی سیم"})
    assert "headphone" in q["categories"]


async def test_dk_best_for_budget(client):
    data = await call(client, "dk_best_for_budget", {"query": "هدفون بی سیم", "max_price": 3000000})
    picks = data["picks"]
    assert picks and all(p["price"] <= 3000000 and p["in_stock"] for p in picks)
    assert [p["weighted_rating"] for p in picks] == sorted((p["weighted_rating"] for p in picks), reverse=True)
    cat = await call(client, "dk_best_for_budget", {"category_code": "mobile-phone", "max_price": 20000000, "pages": 1})
    assert cat["picks"] and all(p["price"] <= 20000000 for p in cat["picks"])


async def test_dk_search_brand_and_price_cheapest(client):
    args = {
        "query": "گوشی سامسونگ",
        "sort": "cheapest",
        "brand_ids": [18],
        "min_price": 10000000,
        "max_price": 20000000,
    }
    data = await call(client, "dk_search", args)
    assert data["products"] and prices(data) == sorted(prices(data))
    assert all(10000000 <= p <= 20000000 for p in prices(data))


async def test_dk_find_cheapest(client):
    data = await call(client, "dk_find_cheapest", {"query": "samsung a07", "pages": 2})
    assert data["products"] and prices(data) == sorted(prices(data))
    assert all(p["price"] >= data["price_floor"] > 0 for p in data["products"])
    phones = await call(client, "dk_find_cheapest", {"query": "گوشی سامسونگ", "max_price": 60000000})
    assert phones["products"] and all(
        "سامسونگ" in p["title"] and "مناسب برای" not in p["title"] for p in phones["products"]
    )
    nonsense = await call(client, "dk_find_cheapest", {"query": "zzqxqzzqxq", "pages": 1})
    assert nonsense["products"] == []


async def test_dk_suggest(client):
    data = await call(client, "dk_suggest", {"query": "samsung"})
    assert data["keywords"]


async def test_dk_categories(client):
    data = await call(client, "dk_categories", {"query": "mobile-phone"})
    assert any(c["code"] == "mobile-phone" and c["id"] == 11 for c in data["categories"])


async def test_dk_category_products(client):
    data = await call(
        client, "dk_category_products", {"category_code": "mobile-phone", "sort": "cheapest", "brand_ids": [18]}
    )
    assert data["products"] and all(p["brand"] == "سامسونگ" for p in data["products"])
    assert prices(data) == sorted(prices(data))
    xiaomi = await call(client, "dk_category_products", {"category_code": "mobile-phone", "brand_code": "xiaomi"})
    assert xiaomi["products"] and all(p["brand"] == "شیائومی" for p in xiaomi["products"])
    unknown = await client.call_tool("dk_category_products", {"category_code": "nonexistent-cat-zz"})
    assert unknown.is_error and "unknown category or brand" in unknown.content[0].text


async def test_dk_brand_products(client):
    data = await call(client, "dk_brand_products", {"brand_code": "samsung", "sort": "most_expensive"})
    assert data["brand"]["id"] == 18 and data["products"] and prices(data) == sorted(prices(data), reverse=True)


async def test_dk_seller(client):
    data = await call(client, "dk_seller", {"seller_code": SELLER})
    assert data["seller"]["code"] == SELLER and 0 < data["seller"]["rating"] <= 5
    assert data["products"]


async def test_dk_deals(client):
    data = await call(client, "dk_deals", {})
    discounts = [p["discount_pct"] for p in data["products"]]
    # the API sorts by the exact discount and shows it rounded, so neighbours can swap by 1
    assert data["products"] and discounts[0] == max(discounts) > 0


async def test_dk_deals_supermarket(client):
    data = await call(client, "dk_deals", {"store": "supermarket"})
    assert data["products"] and all(p["price"] > 0 for p in data["products"])
    milk = await call(client, "dk_deals", {"store": "supermarket", "query": "شیر"})
    assert milk["products"] and all("شیر" in p["title"] for p in milk["products"])


async def test_dk_best_sellers(client):
    data = await call(client, "dk_best_sellers", {"category_id": 1, "limit": 5})
    assert len(data["products"]) == 5 and data["categories"]
    leaf = await client.call_tool("dk_best_sellers", {"category_id": 11})
    assert leaf.is_error and "main category" in leaf.content[0].text


async def test_dk_fresh_search(client):
    data = await call(client, "dk_fresh_search", {"query": "شیر", "sort": "cheapest"})
    assert data["products"] and prices(data) == sorted(prices(data))
    dairy = await call(client, "dk_fresh_search", {"category_code": "dairy"})
    assert dairy["products"] and dairy["subcategories"]
    # a real code with "_" (mostly out of stock, so list everything)
    finger = await call(client, "dk_category_products", {"category_code": "finger_food", "in_stock_only": False})
    assert finger["total"] > 0 and finger["products"]
