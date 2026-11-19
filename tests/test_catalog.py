import httpx
import pytest
from conftest import SEARCH, fixture, v2

from digikala_mcp import catalog

pytestmark = pytest.mark.anyio


async def test_dk_search(client, api):
    api[SEARCH] = v2(fixture("search.json"))
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
        "price": 42503600,  # 425,036,000 Rial; no discount, so no price_before_discount/discount_pct
        "in_stock": True,
        "seller": "دیجی\u200cکالا",
        "rating": 4.4,  # 87.64 / 20
        "rating_count": 2164,
        "image": "https://dkstatics-public.digikala.com/digikala-products/img20109389.jpg?x-oss-process=image/resize,m_lfit,h_300,w_300/quality,q_80",
        "url": "https://www.digikala.com/product/dkp-20109389/",
        "match": "all",
    }
    # cases for the phone: Persian title only, so 'samsung' is missing; 'a07' is in some of them
    case = next(p for p in data["products"] if p["id"] == 20915539)
    assert case["match"] == "some" and case["missing_words"] == ["samsung"]
    assert data["matches"] == {"all": 7, "some": 5, "none": 0} and "note" not in data
    deal = next(p for p in data["products"] if p["id"] == 20915539)
    assert deal["discount_pct"] == 12 and deal["price_before_discount"] == 235500
    # the facets list low-id brands (IBM, ...) and unrelated categories, so they are dropped
    assert "brands" not in data and "categories" not in data
    sent = api.calls[0].url.params
    assert sent["q"] == "samsung a07" and sent["sort"] == "20" and sent["page"] == "1"
    assert sent["price[min]"] == "10000000" and sent["price[max]"] == "600000000"  # Toman -> Rial
    assert sent["brands[0]"] == "18" and sent["has_selling_stock"] == "1"


async def test_dk_search_can_include_out_of_stock(client, api):
    api[SEARCH] = v2(fixture("search.json"))
    await client.call_tool("dk_search", {"query": "samsung", "in_stock_only": False})
    assert "has_selling_stock" not in api.calls[0].url.params


async def test_dk_find_cheapest(client, api):
    api[SEARCH] = v2(fixture("search.json"))
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
    api[SEARCH] = v2(fixture("search.json"))
    data = (await client.call_tool("dk_find_cheapest", {"query": "zzqxqzzqxq", "pages": 1})).structured_content
    assert data["products"] == [] and data["scanned"] == 0 and "dk_suggest" in data["note"]
    # Persian digits and Latin case are normalised; the English title counts too
    data = (await client.call_tool("dk_find_cheapest", {"query": "SAMSUNG A۰۷", "pages": 1})).structured_content
    assert data["products"][0]["id"] == 20109389


async def test_dk_find_cheapest_needs_every_query_word(client, api):
    body = fixture("search.json")
    body["data"]["products"][0].update(title_fa="گوشی موبایل شیائومی مدل Redmi A3", title_en="")
    api[SEARCH] = v2(body)
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
            return httpx.Response(200, json=v2(body))
        return httpx.Response(200, json=v2(fixture("search.json")))

    api[SEARCH] = search
    data = (
        await client.call_tool("dk_find_cheapest", {"query": "samsung a07", "pages": 1, "max_price": 1000000})
    ).structured_content
    # the floor comes from the unfiltered page (phones), so the case is not "the cheapest samsung a07"
    assert data["price_floor"] == 11875000 and data["products"] == [] and "price range" in data["note"]
    assert len(api.calls) == 2


async def test_dk_find_cheapest_with_min_price(client, api):
    api[SEARCH] = v2(fixture("search.json"))
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
    api["/discovery/api/v2/autocomplete"] = fixture("autocomplete.json")
    data = (await client.call_tool("dk_suggest", {"query": "موبایل سامسونگ"})).structured_content
    assert data["keywords"][2] == "موبایل سامسونگ a17" and len(data["keywords"]) == 4
    assert data["categories"][0] == {"keyword": "موبایل سامسونگ", "code": "mobile-phone", "title": "گوشی موبایل"}
    assert len(data["categories"]) == 2 and len(data["trending"]) == 2


async def test_dk_search_reads_the_v2_listing_widget(client, api):
    api[SEARCH] = fixture("search_v2.json")
    data = (await client.call_tool("dk_search", {"query": "موبایل", "in_stock_only": False})).structured_content
    assert (data["total"], data["total_pages"]) == (958, 48)
    assert [p["id"] for p in data["products"]] == [14794189, 21679993, 21660239]
    assert data["products"][0]["price"] == 41459990 and data["products"][0]["image"].startswith("https://")


async def test_dk_categories(client, api):
    # No arguments lists the main categories, from /v1/best-selling/ (alive).
    api["/v1/best-selling/"] = fixture("best_selling.json")
    roots = (await client.call_tool("dk_categories", {})).structured_content
    assert [c["code"] for c in roots["categories"]] == ["mobile", "toys", "electronic-devices"]
    assert roots["found"] == 3 and "retired" in roots["note"]
    # Listing a parent's sub-categories died with /v1/category-tree/.
    children = (await client.call_tool("dk_categories", {"parent_id": 1})).structured_content
    assert children["categories"] == [] and "retired" in children["note"]
    # A query resolves to a verified leaf via dk_suggest + the v2 search facet.
    api["/discovery/api/v2/autocomplete"] = fixture("autocomplete.json")

    def search(request):
        if "categories[0]" in request.url.params:
            return httpx.Response(200, json=v2(fixture("category_products.json")))
        return httpx.Response(200, json=v2(fixture("seller.json")))  # facet lists mobile-phone id 11

    api[SEARCH] = search
    found = (await client.call_tool("dk_categories", {"query": "موبایل سامسونگ"})).structured_content
    assert {c["code"] for c in found["categories"]} == {"mobile-phone"}
    assert found["categories"][0]["id"] == 11 and found["categories"][0]["verified_total"] == 4026


async def test_dk_category_products_unsellable_cards(client, api):
    # /v1/categories/<code>/search/ is retired: the category is resolved via the
    # v2 facet, then browsed with a categories[0]=<id> v2 search.
    def search(request):
        if "categories[0]" in request.url.params:
            return httpx.Response(200, json=v2(fixture("category_products.json")))
        return httpx.Response(200, json=v2(fixture("seller.json")))  # facet lists mobile-phone id 11

    api[SEARCH] = search
    data = (
        await client.call_tool("dk_category_products", {"category_code": "mobile-phone", "in_stock_only": False})
    ).structured_content
    assert data["total"] == 4026
    p = data["products"][0]
    # null fields and a zero rating count are left out of cards
    assert {k: v for k, v in p.items() if k not in ("image", "url")} == {
        "id": 22667973,
        "title": p["title"],
        "brand": "اپل",
        "in_stock": False,
    }
    assert p["url"].endswith("dkp-22667973/") and p["image"].startswith("https://") and "brands" not in data
    sent = [c for c in api.calls if "categories[0]" in c.url.params][0].url.params
    assert sent["categories[0]"] == "11" and sent["sort"] == "22"


async def test_dk_category_products_feature_filters(client, api):
    def search(request):
        if "categories[0]" in request.url.params:
            return httpx.Response(200, json=v2(fixture("category_products.json")))
        return httpx.Response(200, json=v2(fixture("seller.json")))

    api[SEARCH] = search
    args = {
        "category_code": "mobile-phone",
        "attributes": {"2226": [19239], "2251": [19515, 19516]},  # Android; two storage sizes
        "colors": [1],
        "seller_type": "digikala",
        "fast_delivery": True,
        "ready_to_ship": True,
    }
    assert not (await client.call_tool("dk_category_products", args)).is_error
    sent = [c for c in api.calls if "categories[0]" in c.url.params][0].url.params
    assert sent["attributes[2226][0]"] == "19239"
    assert (sent["attributes[2251][0]"], sent["attributes[2251][1]"]) == ("19515", "19516")
    assert sent["color_palettes[0]"] == "1" and sent["seller_types[0]"] == "digikala"
    assert sent["has_jet_shipment_by_seller_or_digikala"] == "1" and sent["has_ready_to_shipment"] == "1"


async def test_dk_filters_for_a_category(client, api):
    # The category id is resolved from the v2 facet; the filters come from a
    # categories[0]=<id> v2 search, not the retired /v1/categories/.../search/.
    def search(request):
        if "categories[0]" in request.url.params:
            return httpx.Response(200, json=v2(fixture("category_filters.json")))
        return httpx.Response(200, json=v2(fixture("seller.json")))

    api[SEARCH] = search
    data = (await client.call_tool("dk_filters", {"category_code": "mobile-phone"})).structured_content
    assert data["total"] == 4031
    assert data["price_range"] == {"min": 1635000, "max": 579999000}  # Rial / 10
    os_ = data["attributes"][0]
    assert (os_["id"], os_["title"]) == (2226, "سیستم عامل")
    assert os_["values"]["Android"] == 19239 and "value_count" not in os_
    assert data["colors"]["صورتی"] == 1
    assert data["seller_types"] == ["trusted", "digikala"] and data["fast_delivery_available"] is True
    assert data["brands"]["archos"] == 62 and "categories" not in data


async def test_dk_filters_one_attribute_and_cap(client, api, monkeypatch):
    def search(request):
        if "categories[0]" in request.url.params:
            return httpx.Response(200, json=v2(fixture("category_filters.json")))
        return httpx.Response(200, json=v2(fixture("seller.json")))

    api[SEARCH] = search
    monkeypatch.setattr(catalog, "FILTER_VALUES", 2)
    data = (await client.call_tool("dk_filters", {"category_code": "mobile-phone"})).structured_content
    # an alphabetical list cut short would hide common values, so a long one only gives its count
    assert data["attributes"][0] == {"id": 2226, "title": "سیستم عامل", "value_count": 4}
    assert data["attributes"][2]["values"] == {"فاقد پشتیبانی از کارت حافظه": 31362, "microSD": 19520}  # 2: listed
    one = (
        await client.call_tool("dk_filters", {"category_code": "mobile-phone", "attribute_id": 2226})
    ).structured_content
    assert one["title"] == "سیستم عامل" and len(one["values"]) == 4  # every value, not cut
    missing = await client.call_tool("dk_filters", {"category_code": "mobile-phone", "attribute_id": 1})
    assert missing.is_error and "No attribute 1" in missing.content[0].text


async def test_dk_filters_for_a_query(client, api):
    api[SEARCH] = fixture("search_v2.json")
    data = (await client.call_tool("dk_filters", {"query": "موبایل"})).structured_content
    assert list(data["categories"]) == ["doll-house", "brush-and-makeup-accesories", "stabilizer-gimbal"]
    assert "brands" not in data  # the search's brand facet is not the query's brands
    assert data["seller_types"] == ["official", "trusted", "digikala", "roosta"]
    assert data["total"] == 958 and data["fast_delivery_available"]
    # v2 lists attributes as attribute_<id> keys
    assert next(a for a in data["attributes"] if a["id"] == 2251)["values"]["256 گیگابایت"] == 19476
    assert next(a for a in data["attributes"] if a["id"] == 2226)["values"]["Android"] == 19239
    assert api.calls[0].url.params["q"] == "موبایل"


async def test_dk_filters_needs_a_category_or_query(client, api):
    result = await client.call_tool("dk_filters", {})
    assert result.is_error and not api.calls


async def test_dk_best_for_budget(client, api):
    api[SEARCH] = v2(fixture("budget_search.json"))
    data = (
        await client.call_tool("dk_best_for_budget", {"query": "هدفون بی سیم", "max_price": 5000000})
    ).structured_content
    # only titles with every word (most 'هدفون بلوتوثی' ones are out); mean of the 6 ratings = 21.8 / 6
    assert data["candidates"] == 6 and data["skipped_few_ratings"] == 0 and data["average_rating"] == 3.63
    assert [p["id"] for p in data["picks"]] == [15556320, 9053401, 11477591, 5112620, 6454441, 19019009]
    top = data["picks"][0]
    assert (top["rating"], top["rating_count"], top["weighted_rating"]) == (4.0, 68, 3.92)  # (20*3.633 + 4*68) / 88
    assert top["price"] == 950000 and top["budget_used_pct"] == 19
    # both 3.8, but 3129 ratings hold their score better than 142 ratings
    assert [p["weighted_rating"] for p in data["picks"][1:3]] == [3.8, 3.78]
    budget = api.calls[0].url.params
    assert budget["price[max]"] == "50000000" and budget["has_selling_stock"] == "1"
    assert "price[max]" not in api.calls[-1].url.params  # the unfiltered call for the accessory floor


async def test_dk_best_for_budget_min_ratings_and_empty(client, api):
    api[SEARCH] = v2(fixture("budget_search.json"))
    args = {"query": "هدفون بی سیم", "max_price": 5000000, "min_ratings": 100}
    data = (await client.call_tool("dk_best_for_budget", args)).structured_content
    assert data["skipped_few_ratings"] == 2 and len(data["picks"]) == 4  # 65 and 68 ratings dropped
    data = (await client.call_tool("dk_best_for_budget", {**args, "max_price": 1000})).structured_content
    assert data["picks"] == [] and "note" in data


async def test_dk_best_for_budget_by_category(client, api):
    def facet_body():
        body = v2(fixture("seller.json"))
        body["data"]["widgets"][0]["data"]["filters"]["categories"] = {
            "options": [{"id": 211, "code": "headphone", "title_fa": "هدفون"}]
        }
        return body

    def search(request):
        if "categories[0]" in request.url.params:
            return httpx.Response(200, json=v2(fixture("budget_search.json")))
        return httpx.Response(200, json=facet_body())

    api[SEARCH] = search
    args = {"category_code": "headphone", "max_price": 5000000, "pages": 1}
    data = (await client.call_tool("dk_best_for_budget", args)).structured_content
    assert data["candidates"] == 12  # no title check when browsing a category
    sent = [c for c in api.calls if "categories[0]" in c.url.params][0].url.params
    assert sent["price[max]"] == "50000000"


async def test_fetch_reuses_a_recent_answer(client, api):
    api[SEARCH] = v2(fixture("search.json"))
    for _ in range(2):
        await client.call_tool("dk_search", {"query": "samsung a07"})
    assert len(api.calls) == 1


async def test_dk_category_products_one_brand(client, api):
    def search(request):
        params = request.url.params
        if params.get("q") == "xiaomi":
            body = v2(fixture("seller.json"))
            body["data"]["widgets"][0]["data"]["filters"]["brands"] = {
                "options": [{"id": 12345, "code": "xiaomi", "title_fa": "شیائومی"}]
            }
            return httpx.Response(200, json=body)
        if "categories[0]" in params:
            return httpx.Response(200, json=v2(fixture("category_products.json")))
        return httpx.Response(200, json=v2(fixture("seller.json")))

    api[SEARCH] = search
    result = await client.call_tool("dk_category_products", {"category_code": "mobile-phone", "brand_code": "xiaomi"})
    assert not result.is_error
    sent = [c for c in api.calls if "brands[0]" in c.url.params][0].url.params
    assert sent["brands[0]"] == "12345" and sent["categories[0]"] == "11"


async def test_dk_category_products_unknown_code_errors(client, api):
    # The retired tree means an unknown code can no longer be checked against
    # /v1/categories/.../search/: it fails fast with a helpful message instead.
    api[SEARCH] = v2(fixture("seller.json"))
    result = await client.call_tool("dk_category_products", {"category_code": "nonexistent-cat-zz"})
    assert result.is_error and "could not be resolved" in result.content[0].text
    assert not any("categories[0]" in c.url.params for c in api.calls)


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
    # /v1/sellers/ is retired: the tool fails fast and points at the replacement.
    result = await client.call_tool("dk_seller", {"seller_code": "CGDG9"})
    assert result.is_error and "retired" in result.content[0].text
    assert "dk_seller_on_product" in result.content[0].text and not api.calls
    # The replacement reads the sellers off one product's offers (dk_product).
    api["/product/v1/products/20109389/"] = fixture("product.json")
    data = (await client.call_tool("dk_seller_on_product", {"product_id": 20109389})).structured_content
    assert data["product"] == {
        "id": 20109389,
        "title": "گوشی موبایل سامسونگ مدل Galaxy A07 دو سیم کارت ظرفیت 64 گیگابایت و رم 4 گیگابایت",
        "price": 42503600,
        "url": "https://www.digikala.com/product/dkp-20109389/",
    }
    assert {
        "code": "CGDG9",
        "title": "اسمارت تکنولوژی قشم",
        "rating": 4.4,
        "url": "https://www.digikala.com/seller/CGDG9/",
    } in data["sellers"]
    assert "dead" in data["note"]


async def test_dk_deals(client, api):
    # The main-store Incredible Offers endpoint is retired: deals now come from
    # the v2 search (sort=26, biggest discount first) instead, so there are no
    # timed deal_ends any more. Supermarket (Fresh) deals are unchanged.
    api[SEARCH] = v2(fixture("deals.json"))
    api["/fresh/v1/incredible-offers/products/"] = fixture("fresh_deals.json")
    deals = (await client.call_tool("dk_deals", {"query": "هدفون"})).structured_content
    first = deals["products"][0]
    assert first["discount_pct"] == 90 and first["price"] == 999990 and first["price_before_discount"] == 10000000
    assert "NOT the timed" in deals["note"]
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


async def test_dk_categories_main_list_is_cached(client, api):
    api["/v1/best-selling/"] = fixture("best_selling.json")
    first = (await client.call_tool("dk_categories", {})).structured_content
    second = (await client.call_tool("dk_categories", {})).structured_content
    assert first == second and len(api.calls) == 1  # fetched once, then the in-process list


async def test_dk_find_cheapest_translates_persian_brand_words(client, api):
    # Real titles say "iPhone", never "آیفون": the Persian query must be searched
    # in Latin, or only mockups (whose titles literally contain آیفون) match.
    assert catalog.translate_query("گوشی آیفون") == "گوشی iPhone"
    assert catalog.translate_query("گوشی سامسونگ") == "گوشی Samsung"
    assert catalog.translate_query("هدفون بی سیم") == "هدفون بی سیم"  # generic words stay Persian
    api[SEARCH] = v2(fixture("search.json"))
    await client.call_tool("dk_find_cheapest", {"query": "گوشی آیفون", "pages": 1})
    assert api.calls[0].url.params["q"] == "گوشی iPhone"
