import httpx
import pytest
from conftest import fixture

pytestmark = pytest.mark.anyio

PID = {"product_id": 20109389}


async def test_dk_product(client, api):
    api["/product/v1/products/20109389/"] = fixture("product.json")
    p = (await client.call_tool("dk_product", {**PID, "max_offers": 3})).structured_content
    assert p["price"] == 42503600 and p["in_stock"] and p["rating"] == 4.4
    assert p["brand_code"] == "samsung" and p["brand_id"] == 18 and p["store"] == "digikala"
    assert p["category"] == {"id": 11, "code": "mobile-phone", "title": "گوشی موبایل"}
    assert p["lowest_price_30d"] == 28373600 and p["colors"] == ["سبز", "مشکی"]
    assert p["offers_count"] == 8
    # cheapest first, across colors and sellers
    assert [(o["variant_id"], o["price"]) for o in p["offers"]] == [
        (72287314, 42503600),
        (80919193, 42918000),
        (74547381, 42979400),
    ]
    assert p["offers"][1] == {
        "variant_id": 80919193,
        "variant": "سبز",
        "price": 42918000,
        "price_before_discount": 42918000,
        "discount_pct": 0,
        "stock_left": 2,
        "seller": "سپاهان همراه یاقوت",
        "seller_code": "CGXGH",
        "seller_rating": 4.3,
        "warranty": "گارانتی 18 ماهه شرکتی",
        "shipping": "موجود در انبار دیجی\u200cکالا",
        "ships_by": ["digikala"],
        "free_shipping": False,
        "lead_time_days": 0,
    }
    assert p["specs"]["صفحه نمایش"]["اندازه"] == "6.7 اینچ"


async def test_dk_product_free_shipping_offer(client, api):
    body = fixture("product.json")
    body["data"]["product"]["variants"][0]["shipment_methods"]["providers"] = [
        {"type": "seller", "price": {"text": "رایگان", "is_free": True}}
    ]
    api["/product/v1/products/20109389/"] = body
    p = (await client.call_tool("dk_product", PID)).structured_content
    assert [o["free_shipping"] for o in p["offers"]].count(True) == 1


async def test_dk_product_without_specs(client, api):
    api["/product/v1/products/20109389/"] = fixture("product.json")
    p = (await client.call_tool("dk_product", {**PID, "include_specs": False})).structured_content
    assert "specs" not in p and len(p["offers"]) == 8


async def test_dk_product_falls_back_to_fresh(client, api):
    # Fresh (supermarket) ids answer HTTP 200 with body status 301 on the main product service.
    api["/product/v1/products/4369031/"] = fixture("fresh_redirect.json")
    api["/fresh/v1/product/4369031/"] = fixture("fresh_product.json")
    p = (await client.call_tool("dk_product", {"product_id": 4369031})).structured_content
    assert p["price"] == 28000 and p["category"]["code"] == "low-fat-milk"
    assert p["store"] == "supermarket" and p["url"] == "https://www.digikala.com/supermarket/product/4369031/"
    assert (
        p["offers"][0]["ships_by"] == ["ارسال سریع سوپرمارکتی دیجی\u200cکالا"]
        and p["offers"][0]["seller_rating"] is None
    )
    assert p["lowest_price_30d"] is None


async def test_dk_product_inactive(client, api):
    api["/product/v1/products/1/"] = {"status": 200, "data": {"product": {"is_inactive": True}}}
    result = await client.call_tool("dk_product", {"product_id": 1})
    assert result.is_error and "dk_search" in result.content[0].text


async def test_dk_price_history(client, api):
    api["/v1/product/20109389/price-chart/"] = fixture("price_chart.json")
    data = (await client.call_tool("dk_price_history", PID)).structured_content
    black, purple = data["variants"]
    assert black["variant"] == "مشکی" and black["lowest"] == 34499000 and black["highest"] == 37819600
    assert black["last_price"] == 34499000 and black["days"][0] == {"day": "1405/07/07", "price": 34500000}
    # a variant not for sale on any day has no prices
    assert purple["days"] == [] and purple["lowest"] is None


async def test_dk_reviews(client, api):
    api["/v1/rate-review/products/20109389/"] = fixture("comments.json")
    data = (await client.call_tool("dk_reviews", {**PID, "sort": "buyers_first", "page": 2})).structured_content
    assert data["total"] == 1251 and len(data["reviews"]) == 3
    first, long = data["reviews"][0], data["reviews"][1]
    assert first["rating"] == 4 and first["verified_buyer"] and first["likes"] == 120 and first["variant"] == "سبز"
    assert first["seller"] == "دیجی\u200cکالا"
    assert len(long["text"]) == 301 and long["text"].endswith("…")
    sent = api.calls[0].url.params
    assert sent["sort"] == "buyers" and sent["page"] == "2"


async def test_dk_questions(client, api):
    api["/v1/product/20109389/questions/"] = fixture("questions.json")
    data = (await client.call_tool("dk_questions", PID)).structured_content
    q = data["questions"][0]
    assert q["answer_count"] == 18 and len(q["answers"]) == 2
    assert q["answers"][0] == {"text": "صد در صد سامسونگ بهنره", "answered_by": "buyer", "likes": 28}
    assert api.calls[0].url.params["sort"] == "answers"


async def test_dk_similar(client, api):
    api["/v1/products/20109389/similar/"] = fixture("similar.json")
    data = (await client.call_tool("dk_similar", {**PID, "sort": "cheapest"})).structured_content
    assert [p["price"] for p in data["products"]] == [1570000, 1633000, 1635000]
    assert data["products"][1]["rating"] == 1.0
    assert api.calls[0].url.params["sort"] == "20"


async def test_dk_similar_unknown_id(client, api):
    api["/v1/products/999999999/similar/"] = lambda r: httpx.Response(
        400, json={"status": 400, "message": 'Value "<ARRAY>" is empty, but non empty value was expected.'}
    )
    result = await client.call_tool("dk_similar", {"product_id": 999999999})
    assert result.is_error and "Product 999999999 not found" in result.content[0].text


async def test_dk_compare(client, api):
    api["/v1/product/compare/"] = fixture("compare.json")
    data = (await client.call_tool("dk_compare", {"product_ids": [20109389, 20110013]})).structured_content
    assert [p["id"] for p in data["products"]] == [20109389, 20110013]
    # both are Galaxy A07s: every row is identical, so it is folded into same_specs
    assert data["specs"] == [] and data["same_specs"]["مشخصات کلی / مدل"] == "Galaxy A07"
    assert len(data["same_specs"]) == 13 and data["missing_ids"] == []
    # a spec only one product has is null for the other, and unknown ids are reported
    body = fixture("compare.json")
    body["data"]["compare_products"][1]["attribute_groups"][0]["attributes"][0]["values"] = []
    api["/v1/product/compare/"] = body
    data = (await client.call_tool("dk_compare", {"product_ids": [20109389, 20110013, 999]})).structured_content
    assert data["specs"] == [{"group": "مشخصات کلی", "name": "نوع گوشی موبایل", "values": ["سیستم عامل اندروید", None]}]
    assert len(data["same_specs"]) == 12 and data["missing_ids"] == [999]
    sent = api.calls[0].url.params
    assert sent["product_ids[0]"] == "20109389" and sent["product_ids[1]"] == "20110013"


async def test_dk_compare_needs_two(client, api):
    result = await client.call_tool("dk_compare", {"product_ids": [20109389]})
    assert result.is_error and not api.calls


async def test_dk_installments(client, api):
    api["/v1/product/20109389/digipay-credit/"] = fixture("installments.json")
    data = (await client.call_tool("dk_installments", PID)).structured_content
    # three variants with the same terms collapse into one plan
    assert data["plans"] == [
        {
            "credit_amount": 70000000,
            "monthly_repayment": 6585300,
            "months": 12,
            "variant_ids": [71571641, 71571681, 72287314],
        }
    ]
