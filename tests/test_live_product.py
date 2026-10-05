import pytest

pytestmark = [pytest.mark.anyio, pytest.mark.live]

PID = {"product_id": 20109389}  # Samsung Galaxy A07, a long-lived best seller


async def call(client, name, args):
    result = await client.call_tool(name, args)
    assert not result.is_error, result.content[0].text
    return result.structured_content


async def text_size(client, name, args):
    """Bytes of the text content the model reads (the SDK pretty-prints it, so it is larger than the JSON)."""
    result = await client.call_tool(name, args)
    assert not result.is_error, result.content[0].text
    return sum(len(c.text.encode()) for c in result.content)


async def test_dk_product(client):
    data = await call(client, "dk_product", PID)
    assert data["id"] == 20109389 and data["brand_code"] == "samsung" and data["brand_id"] == 18 and data["specs"]
    offers = [o["price"] for o in data["offers"] if o["price"]]
    assert offers and offers == sorted(offers) and offers[0] > 1000000
    assert await text_size(client, "dk_product", PID) < 15000


async def test_dk_product_fresh(client):
    data = await call(client, "dk_product", {"product_id": 4369031, "include_specs": False})
    assert data["id"] == 4369031 and data["offers"] and data["store"] == "supermarket"


async def test_dk_price_history(client):
    data = await call(client, "dk_price_history", PID)
    assert any(v["days"] and v["lowest"] > 0 for v in data["variants"])


async def test_dk_reviews(client):
    data = await call(client, "dk_reviews", {**PID, "sort": "newest"})
    assert data["reviews"] and data["total"] > 100
    assert all(r["rating"] is None or 1 <= r["rating"] <= 5 for r in data["reviews"])
    assert await text_size(client, "dk_reviews", PID) < 15000


async def test_dk_questions(client):
    data = await call(client, "dk_questions", PID)
    assert data["questions"] and data["questions"][0]["answers"]
    assert await text_size(client, "dk_questions", PID) < 15000


async def test_dk_similar(client):
    data = await call(client, "dk_similar", {**PID, "sort": "cheapest"})
    prices = [p["price"] for p in data["products"]]
    assert prices and prices[0] == min(prices)  # similar-products sorting is only roughly ascending
    unknown = await client.call_tool("dk_similar", {"product_id": 999999999})
    assert unknown.is_error and "not found" in unknown.content[0].text


async def test_dk_compare(client):
    data = await call(client, "dk_compare", {"product_ids": [20109389, 20110013]})
    assert len(data["products"]) == 2 and data["specs"]
    assert all(len(row["values"]) == 2 for row in data["specs"]) and data["missing_ids"] == []
    four = {"product_ids": [20109389, 20110013, 20110012, 21013179]}
    assert await text_size(client, "dk_compare", four) < 15000


async def test_dk_shortlist(client):
    data = await call(client, "dk_shortlist", {"product_ids": [20109389, 20110013, 999999999]})
    assert [p["id"] for p in data["products"]] == [20109389, 20110013]
    assert all(p["price"] and p["cheapest_offer"] <= p["price"] for p in data["products"] if p["in_stock"])
    assert [e["id"] for e in data["errors"]] == [999999999]


async def test_dk_installments(client):
    data = await call(client, "dk_installments", PID)
    # Digikala stopped listing plans on 2026-10-05 (its own product page shows none either)
    assert data["plans"] or "note" in data
    for plan in data["plans"]:
        assert plan["monthly_repayment"] > 0 and plan["credit_amount"] > 0
