import httpx
import pytest
from conftest import fixture

pytestmark = pytest.mark.anyio


async def test_dk_search(client, api):
    api["/v1/search/"] = fixture("search.json")
    args = {"query": "samsung a07", "sort": "cheapest", "min_price": 1000000, "max_price": 60000000, "brand_ids": [18]}
    data = (await client.call_tool("dk_search", args)).structured_content
    assert data["total"] == 828 and data["total_pages"] == 42
    # brand + price range: the API sorts only within each category, so the page is re-sorted
    prices = [p["price"] for p in data["products"]]
    assert prices == sorted(prices) and prices[0] == 145000
    assert next(p for p in data["products"] if p["id"] == 20109389) == {
        "id": 20109389,
        "title": "گوشی موبایل سامسونگ مدل Galaxy A07 دو سیم کارت ظرفیت 64 گیگابایت و رم 4 گیگابایت",
        "brand": "سامسونگ",
        "price": 42503600,  # 425,036,000 Rial
        "price_before_discount": 42503600,
        "discount_pct": 0,
        "in_stock": True,
        "seller": "دیجی\u200cکالا",
        "rating": 4.4,  # 87.64 / 20
        "rating_count": 2164,
        "deal_ends": None,
        "url": "https://www.digikala.com/product/dkp-20109389/",
    }
    deal = next(p for p in data["products"] if p["id"] == 20915539)
    assert deal["discount_pct"] == 12 and deal["price_before_discount"] == 235500
    # the facets list low-id brands (IBM, ...) and unrelated categories, so they are dropped
    assert "brands" not in data and "categories" not in data
    sent = api.calls[0].url.params
    assert sent["q"] == "samsung a07" and sent["sort"] == "20" and sent["page"] == "1"
    assert sent["price[min]"] == "10000000" and sent["price[max]"] == "600000000"  # Toman -> Rial
    assert sent["brands[0]"] == "18" and sent["has_selling_stock"] == "1"


async def test_dk_search_can_include_out_of_stock(client, api):
    api["/v1/search/"] = fixture("search.json")
    await client.call_tool("dk_search", {"query": "samsung", "in_stock_only": False})
    assert "has_selling_stock" not in api.calls[0].url.params


async def test_dk_find_cheapest(client, api):
    api["/v1/search/"] = fixture("search.json")
    data = (await client.call_tool("dk_find_cheapest", {"query": "samsung a07", "pages": 2})).structured_content
    # "مناسب برای" cases are dropped; median of the top 5 phones (47,500,000) / 4; the repeated page adds nothing
    assert data["price_floor"] == 11875000 and data["scanned"] == 7 and "note" not in data
    assert [(p["id"], p["price"]) for p in data["products"]] == [
        (20109389, 42503600),
        (20381217, 44518000),
        (20110012, 46811800),
        (21013179, 47500000),
        (20381216, 48377000),
        (20110013, 52960800),
        (20381116, 55002000),
    ]
    assert sorted(c.url.params["page"] for c in api.calls) == ["1", "2"]
    assert all(c.url.params["has_selling_stock"] == "1" for c in api.calls)


async def test_dk_find_cheapest_drops_titles_without_query_words(client, api):
    api["/v1/search/"] = fixture("search.json")
    data = (await client.call_tool("dk_find_cheapest", {"query": "zzqxqzzqxq", "pages": 1})).structured_content
    assert data["products"] == [] and data["scanned"] == 0 and "dk_suggest" in data["note"]
    # Persian digits and Latin case are normalised; the English title counts too
    data = (await client.call_tool("dk_find_cheapest", {"query": "SAMSUNG A۰۷", "pages": 1})).structured_content
    assert data["products"][0]["id"] == 20109389


async def test_dk_find_cheapest_needs_every_query_word(client, api):
    body = fixture("search.json")
    body["data"]["products"][0].update(title_fa="گوشی موبایل شیائومی مدل Redmi A3", title_en="")
    api["/v1/search/"] = body
    data = (await client.call_tool("dk_find_cheapest", {"query": "گوشی سامسونگ", "pages": 1})).structured_content
    assert 20109389 not in [p["id"] for p in data["products"]] and data["scanned"] == 6 and "note" not in data
    # nothing has every word: fall back to any word, and say so
    data = (await client.call_tool("dk_find_cheapest", {"query": "گوشی هواوی", "pages": 1})).structured_content
    assert data["scanned"] == 7 and "only some" in data["note"]
    # an accessory query keeps the "suitable for" titles
    data = (await client.call_tool("dk_find_cheapest", {"query": "کاور مناسب برای", "pages": 1})).structured_content
    assert data["scanned"] == 5


async def test_dk_find_cheapest_floor_ignores_max_price(client, api):
    def search(request):
        if "price[max]" in request.url.params:  # the price-filtered pages only have the cases
            body = fixture("search.json")
            body["data"]["products"] = body["data"]["products"][7:]
            body["data"]["products"][0]["title_fa"] = "کیف کلاسوری Samsung Galaxy A07"  # no "suitable for"
            return httpx.Response(200, json=body)
        return httpx.Response(200, json=fixture("search.json"))

    api["/v1/search/"] = search
    data = (
        await client.call_tool("dk_find_cheapest", {"query": "samsung a07", "pages": 1, "max_price": 1000000})
    ).structured_content
    # the floor comes from the unfiltered page (phones), so the case is not "the cheapest samsung a07"
    assert data["price_floor"] == 11875000 and data["products"] == [] and "price range" in data["note"]
    assert len(api.calls) == 2


async def test_dk_find_cheapest_with_min_price(client, api):
    api["/v1/search/"] = fixture("search.json")
    data = (
        await client.call_tool(
            "dk_find_cheapest", {"query": "samsung a07", "pages": 1, "min_price": 300000, "limit": 2}
        )
    ).structured_content
    assert data["price_floor"] == 300000 and len(api.calls) == 1
    assert [p["price"] for p in data["products"]] == [42503600, 44518000]
    # the API returns nothing for price[min] alone, so an open upper bound is always sent
    assert (
        api.calls[0].url.params["price[min]"] == "3000000" and api.calls[0].url.params["price[max]"] == "10000000000000"
    )


async def test_dk_suggest(client, api):
    api["/v1/autocomplete/"] = fixture("autocomplete.json")
    data = (await client.call_tool("dk_suggest", {"query": "samsung"})).structured_content
    assert "samsung a07" in data["keywords"]
    assert data["categories"][0]["code"] == "mobile-phone"
    assert data["brands"] == [{"id": 18, "title": "سامسونگ", "title_en": "Samsung"}]


async def test_dk_categories(client, api):
    api["/v1/category-tree/"] = fixture("category_tree.json")
    found = (await client.call_tool("dk_categories", {"query": "هدفون"})).structured_content
    assert {c["code"] for c in found["categories"]} == {"headphone", "monitor-headphones"}
    # Arabic yeh/kaf in the query still match Persian titles
    phones = (await client.call_tool("dk_categories", {"query": "گوشي موبايل"})).structured_content
    assert {c["code"] for c in phones["categories"]} == {"mobile-phone", "mobile-accessories"}
    children = (await client.call_tool("dk_categories", {"parent_id": 1})).structured_content["categories"]
    assert [c["code"] for c in children] == ["mobile-phone"]
    roots = (await client.call_tool("dk_categories", {})).structured_content["categories"]
    assert [c["code"] for c in roots] == ["donation", "vehicles", "home-and-kitchen", "mobile", "electronic-devices"]
    mobile = next(
        c
        for c in (await client.call_tool("dk_categories", {"query": "mobile"})).structured_content["categories"]
        if c["id"] == 1
    )
    assert mobile["subcategories"] == 1
    assert len(api.calls) == 1  # the 1.7 MB tree is fetched once


async def test_dk_category_products_unsellable_cards(client, api):
    api["/v1/categories/mobile-phone/search/"] = fixture("category_products.json")
    data = (
        await client.call_tool("dk_category_products", {"category_code": "mobile-phone", "in_stock_only": False})
    ).structured_content
    assert data["total"] == 4026
    p = data["products"][0]
    assert p["id"] == 22667973 and p["in_stock"] is False and p["price"] is None and p["seller"] is None
    assert p["rating"] is None and p["rating_count"] == 0 and "brands" not in data
    assert api.calls[0].url.params["sort"] == "22"


async def test_dk_category_products_one_brand(client, api):
    api["/v1/categories/mobile-phone/brands/xiaomi/search/"] = fixture("category_products.json")
    result = await client.call_tool("dk_category_products", {"category_code": "mobile-phone", "brand_code": "xiaomi"})
    assert not result.is_error and len(api.calls) == 1


async def test_dk_category_products_accepts_real_odd_codes(client, api):
    api["/v1/categories/finger_food/search/"] = fixture("category_products.json")
    result = await client.call_tool("dk_category_products", {"category_code": "finger_food"})
    assert not result.is_error and api.calls[0].url.path == "/v1/categories/finger_food/search/"


async def test_dk_brand_products(client, api):
    body = fixture("brand_products.json")
    body["data"]["brand"] = {"id": 18, "code": "samsung", "title_fa": "سامسونگ", "title_en": "Samsung"}
    api["/v1/brands/samsung/"] = body
    data = (
        await client.call_tool("dk_brand_products", {"brand_code": "samsung", "sort": "best_selling", "page": 2})
    ).structured_content
    assert data["brand"] == {"id": 18, "code": "samsung", "title": "سامسونگ"}
    assert [p["id"] for p in data["products"]] == [20490694, 20109389, 21660239]
    assert data["products"][2]["price"] == 138367100
    assert api.calls[0].url.params["sort"] == "7" and api.calls[0].url.params["page"] == "2"


async def test_dk_seller(client, api):
    api["/v1/sellers/CGDG9/"] = fixture("seller.json")
    data = (await client.call_tool("dk_seller", {"seller_code": "CGDG9"})).structured_content
    assert data["seller"] == {
        "code": "CGDG9",
        "title": "اسمارت تکنولوژی قشم",
        "rating": 4.4,  # 87 / 20 = 4.35, rounded half-up like the site
        "rating_count": 82197,
        "grade": "عالی",
        "on_time_shipping_pct": 99.9,
        "no_cancellation_pct": 99.9,
        "no_return_pct": 99.9,
        "member_for": "6 سال و 2 ماه",
        "is_trusted": True,
        "is_official": False,
        "url": "https://www.digikala.com/seller/CGDG9/",
    }
    assert data["total"] == 135 and data["products"][0]["price"] == 3820000


async def test_dk_deals(client, api):
    api["/v1/incredible-offers/products/"] = fixture("deals.json")
    api["/fresh/v1/incredible-offers/products/"] = fixture("fresh_deals.json")
    deals = (await client.call_tool("dk_deals", {"query": "هدفون"})).structured_content
    first = deals["products"][0]
    assert first["discount_pct"] == 90 and first["price"] == 999990 and first["price_before_discount"] == 10000000
    assert first["deal_ends"] == "2026-10-03 12:00:00"
    sent = api.calls[0].url.params
    assert sent["sort"] == "26" and sent["q"] == "هدفون" and sent["has_selling_stock"] == "1"

    fresh = (
        await client.call_tool("dk_deals", {"store": "supermarket", "query": "شیر", "sort": "cheapest"})
    ).structured_content
    assert fresh["total"] == 128 and fresh["products"][0]["price"] == 346500
    assert api.calls[1].url.path == "/fresh/v1/incredible-offers/products/" and api.calls[1].url.params["q"] == "شیر"


async def test_dk_best_sellers(client, api):
    api["/v1/best-selling/"] = fixture("best_selling.json")
    data = (await client.call_tool("dk_best_sellers", {"category_id": 1, "limit": 2})).structured_content
    assert [p["id"] for p in data["products"]] == [15572856, 20109389]
    assert data["categories"][0] == {"id": 1, "code": "mobile", "title": "موبایل"}
    assert api.calls[0].url.params["category_id"] == "1"


async def test_dk_best_sellers_leaf_category(client, api):
    api["/v1/best-selling/"] = lambda r: httpx.Response(400, json={"status": 400, "message": "not main category"})
    result = await client.call_tool("dk_best_sellers", {"category_id": 11})
    assert result.is_error and "dk_categories() with no arguments" in result.content[0].text


async def test_dk_fresh_search(client, api):
    body = fixture("fresh_search.json")
    body["data"]["products"][1].update(status="in_supply", default_variant=[])  # listed but not sellable
    api["/fresh/v1/search/"] = body
    api["/fresh/v1/categories/dairy/search/"] = fixture("fresh_category.json")
    found = (await client.call_tool("dk_fresh_search", {"query": "شیر", "sort": "cheapest"})).structured_content
    assert [p["price"] for p in found["products"]] == [28000, 40600] and found["subcategories"] == []
    assert api.calls[0].url.params["sort"] == "20"

    # category_code wins over query and lists the sub-categories
    browsed = (await client.call_tool("dk_fresh_search", {"query": "شیر", "category_code": "dairy"})).structured_content
    assert browsed["total"] == 2791
    assert browsed["subcategories"][0] == {"code": "breakfast-cheese", "title": "پنیر صبحانه"}
    assert "q" not in api.calls[1].url.params

    # a query lists no sub-categories: on a miss the API sends all ~200 Fresh categories
    api["/fresh/v1/search/"] = fixture("fresh_category.json")
    missed = (await client.call_tool("dk_fresh_search", {"query": "zzqxqzzqxq"})).structured_content
    assert missed["subcategories"] == []

    empty = await client.call_tool("dk_fresh_search", {})
    assert empty.is_error and "category_code" in empty.content[0].text


@pytest.mark.parametrize(
    ("name", "args"),
    [
        ("dk_category_products", {"category_code": "../x"}),
        ("dk_category_products", {"category_code": "a/b"}),
        ("dk_seller", {"seller_code": "a/b"}),
        ("dk_search", {"query": "x"}),
        ("dk_search", {"query": "phone", "page": 0}),
        ("dk_search", {"query": "phone", "brand_ids": [1, 2, 3, 4, 5, 6]}),
        ("dk_search", {"query": "phone", "sort": "random"}),
        ("dk_find_cheapest", {"query": "phone", "pages": 9}),
    ],
)
async def test_bad_input_rejected_before_any_call(client, api, name, args):
    result = await client.call_tool(name, args)
    assert result.is_error and not api.calls
