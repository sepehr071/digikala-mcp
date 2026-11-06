"""Digikala listing tools: search, categories, brands, sellers, deals, best sellers, Fresh supermarket."""

from __future__ import annotations

import asyncio
import math
import statistics
from typing import Annotated, Any, Literal

from pydantic import Field

from .http import SITE, ApiError, fetch
from .registry import tool

SORTS = {
    "relevance": 22,
    "cheapest": 20,
    "most_expensive": 21,
    "best_selling": 7,
    "most_viewed": 4,
    "newest": 1,
    "fastest_delivery": 25,
    "buyers_pick": 27,
    "biggest_discount": 26,  # deal lists only
}

Query = Annotated[
    str,
    Field(
        min_length=2,
        max_length=100,
        description="Persian or English words, e.g. 'گوشی سامسونگ'.",
    ),
]
Sort = Annotated[
    Literal[
        "relevance",
        "cheapest",
        "most_expensive",
        "best_selling",
        "most_viewed",
        "newest",
        "fastest_delivery",
        "buyers_pick",
    ],
    Field(),
]
Page = Annotated[int, Field(ge=1, le=100)]
MinPrice = Annotated[int | None, Field(ge=0)]  # Toman, as INSTRUCTIONS say
MaxPrice = Annotated[int | None, Field(ge=0)]
BrandIds = Annotated[
    list[int] | None,
    Field(max_length=5, description="Brand ids (dk_product brand_id), e.g. [18] Samsung."),
]
InStock = Annotated[bool, Field()]
Code = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_.'’-]{1,80}$")]  # a few real codes have _ . ' ’
Attributes = Annotated[
    dict[int, Annotated[list[int], Field(max_length=20)]] | None,
    Field(
        max_length=10,
        description="{attribute id: [value ids]} from dk_filters, e.g. {2226: [19239]}. Values OR, attributes AND.",
    ),
]
Colors = Annotated[list[int] | None, Field(max_length=10, description="Color ids from dk_filters.")]
SellerType = Annotated[Literal["digikala", "official", "trusted", "roosta"] | None, Field()]
FastDelivery = Annotated[bool, Field(description="Jet delivery only.")]
ReadyToShip = Annotated[bool, Field(description="In Digikala's warehouse only.")]
# dk_category_products repeats dk_search's filters; short descriptions there save tokens on every request
SameBrandIds = Annotated[list[int] | None, Field(max_length=5, description="As dk_search.")]
SameAttributes = Annotated[
    dict[int, Annotated[list[int], Field(max_length=20)]] | None, Field(max_length=10, description="As dk_search.")
]
SameColors = Annotated[list[int] | None, Field(max_length=10, description="As dk_search.")]


@tool("Search products")
async def dk_search(
    query: Query,
    sort: Sort = "relevance",
    min_price: MinPrice = None,
    max_price: MaxPrice = None,
    brand_ids: BrandIds = None,
    attributes: Attributes = None,
    colors: Colors = None,
    seller_type: SellerType = None,
    fast_delivery: FastDelivery = False,
    ready_to_ship: ReadyToShip = False,
    in_stock_only: InStock = True,
    page: Page = 1,
) -> dict[str, Any]:
    """Search products by name: price (Toman), discount, seller, rating, 20 per page.

    Each product has `match` ('all', 'some' + `missing_words`, 'none'); prefer 'all'.
    Filter ids: dk_filters(query=...).
    """
    params = {
        "q": query,
        **listing_params(sort, min_price, max_price, brand_ids, in_stock_only, page),
        **filter_params(attributes, colors, seller_type, fast_delivery, ready_to_ship),
    }
    data = (await fetch("/v1/search/", params))["data"]
    # the brand/category facets are not left in: they list low-id brands and unrelated categories, not the query's
    result = listing(data)
    words = query_words(query)
    for c, p in zip(result["products"], data.get("products") or [], strict=True):
        missing = [w for w in words if w not in title_text(p)]
        c["match"] = "none" if len(missing) == len(words) else "some" if missing else "all"
        if c["match"] == "some":
            c["missing_words"] = missing
    result["matches"] = {m: sum(c["match"] == m for c in result["products"]) for m in ("all", "some", "none")}
    if result["products"] and not result["matches"]["all"]:
        result["note"] = "No title on this page has every query word: these are loose matches. Try dk_suggest."
    if sort in ("cheapest", "most_expensive") and brand_ids and (min_price is not None or max_price is not None):
        result["products"].sort(key=lambda c: c.get("price") or 0, reverse=sort == "most_expensive")
    return result


@tool("Find cheapest product")
async def dk_find_cheapest(
    query: Query,
    pages: Annotated[int, Field(ge=1, le=5, description="Relevance pages to scan.")] = 3,
    min_price: Annotated[
        int | None,
        Field(ge=0, description="Toman. Default: 1/4 of the top matches' median price (drops accessories)."),
    ] = None,
    max_price: MaxPrice = None,
    limit: Annotated[int, Field(ge=1, le=60)] = 10,
) -> dict[str, Any]:
    """Find the cheapest in-stock products that really match a query, sorted by price (Toman).

    Keeps titles with every query word and drops accessories. Then dk_product on the winner:
    another seller may be cheaper.
    """
    base = {"q": query, "has_selling_stock": 1}
    calls = [fetch("/v1/search/", {**base, **_prices(min_price, max_price), "page": n}) for n in range(1, pages + 1)]
    if min_price is None and max_price is not None:
        calls.append(fetch("/v1/search/", {**base, "page": 1}))  # unfiltered, so the floor sees the real items
    bodies = await asyncio.gather(*calls)
    found, loose = _matches(query, bodies[:pages])
    floor = min_price
    if floor is None:
        top = _matches(query, bodies[pages:])[0] if len(bodies) > pages else found
        if top:
            # ponytail: crude accessory filter; a category-aware filter would need one more call per query.
            floor = int(statistics.median(c["price"] for c in top[:5]) / 4)
    offers = sorted((c for c in found if c["price"] >= (floor or 0)), key=lambda c: c["price"])
    result: dict[str, Any] = {"price_floor": floor, "scanned": len(found), "products": offers[:limit]}
    if not offers:
        result["note"] = "No matching product in this price range; try dk_suggest for better words, or another range."
    elif loose:
        result["note"] = "No title contains every query word; these contain only some of them, so check the titles."
    return result


PRIOR_WEIGHT = 20  # ratings a product needs before its own score outweighs the average


@tool("Best picks for a budget")
async def dk_best_for_budget(
    max_price: Annotated[int, Field(ge=1, description="Budget, Toman.")],
    query: Annotated[str | None, Field(min_length=2, max_length=100, description="e.g. 'هدفون بی سیم'.")] = None,
    category_code: Annotated[Code | None, Field(description="Instead of query, e.g. 'mobile-phone'.")] = None,
    min_price: Annotated[
        int | None, Field(ge=0, description="Toman. Default for a query: a floor that drops accessories.")
    ] = None,
    min_ratings: Annotated[int, Field(ge=0, le=1000)] = 5,
    pages: Annotated[int, Field(ge=1, le=5, description="Pages to scan.")] = 3,
    limit: Annotated[int, Field(ge=1, le=30)] = 10,
) -> dict[str, Any]:
    """Rank the best-rated in-stock products within a budget (Toman) by a rating weighted by its count.

    A 5.0 from 3 buyers does not beat a 4.6 from 900. Use for "best X under Y".
    """
    if not query and not category_code:
        raise ApiError("Pass a query (e.g. 'هدفون بی سیم') or a category_code (e.g. 'mobile-phone').")
    budget = _prices(min_price, max_price)
    if category_code:
        bodies = await asyncio.gather(
            *(
                fetch(f"/v1/categories/{category_code}/search/", {**budget, "has_selling_stock": 1, "page": n})
                for n in range(1, pages + 1)
            )
        )
        found = [
            c for b in bodies for c in map(card, b["data"].get("products") or []) if c["in_stock"] and c.get("price")
        ]
    else:
        base = {"q": query, "has_selling_stock": 1}
        calls = [fetch("/v1/search/", {**base, **budget, "page": n}) for n in range(1, pages + 1)]
        if min_price is None:
            calls.append(fetch("/v1/search/", {**base, "page": 1}))  # unfiltered, to see what the real items cost
        bodies = await asyncio.gather(*calls)
        found = _matches(query, bodies[:pages])[0]
        if min_price is None and (top := _matches(query, bodies[pages:])[0]):
            # ponytail: same crude accessory floor as dk_find_cheapest, capped so a small budget still gets results
            floor = min(statistics.median(c["price"] for c in top[:5]) / 4, max_price / 2)
            found = [c for c in found if c["price"] >= floor]
    found = list({c["id"]: c for c in found if c["price"] <= max_price}.values())
    rated = [c for c in found if c.get("rating") and c.get("rating_count", 0) >= min_ratings]
    mean = statistics.mean(c["rating"] for c in rated) if rated else 0
    for c in rated:
        n = c["rating_count"]
        c["weighted_rating"] = round((PRIOR_WEIGHT * mean + c["rating"] * n) / (PRIOR_WEIGHT + n), 2)
        c["budget_used_pct"] = round(100 * c["price"] / max_price)
    rated.sort(key=lambda c: (-c["weighted_rating"], c["price"]))
    result: dict[str, Any] = {
        "candidates": len(found),
        "skipped_few_ratings": len(found) - len(rated),
        "average_rating": round(mean, 2) if rated else None,
        "picks": rated[:limit],
    }
    if not rated:
        result["note"] = (
            "Nothing rated in this budget; raise max_price, lower min_ratings or try dk_suggest for other words."
        )
    return result


ACCESSORY = "مناسب برای"  # "suitable for": Digikala's accessory titles say what they fit


def _matches(query: str, bodies: list[Any]) -> tuple[list[dict[str, Any]], bool]:
    """In-stock cards whose title has every query word, else any query word (loose=True), in relevance order.

    Semantic search answers even nonsense with unrelated items, so titles are checked here.
    """
    words = query_words(query)
    keep_accessories = ACCESSORY in norm(query)
    cards, seen = [], set()
    for body in bodies:
        for p in body["data"].get("products") or []:
            c = card(p)
            title = title_text(p)
            if (
                c["in_stock"]
                and c.get("price")
                and c["id"] not in seen
                and (keep_accessories or ACCESSORY not in title)
            ):
                seen.add(c["id"])
                cards.append((c, title))
    strict = [c for c, title in cards if all(w in title for w in words)]
    if strict:
        return strict, False
    loose = [c for c, title in cards if any(w in title for w in words)]
    return loose, bool(loose)


def query_words(query: str) -> list[str]:
    return [w for w in norm(query).split() if len(w) > 1]


def title_text(p: dict[str, Any]) -> str:
    """Persian and English title, normalized, for word matching."""
    return norm(f"{p.get('title_fa') or ''} {p.get('title_en') or ''}")


@tool("Search suggestions")
async def dk_suggest(
    query: Annotated[str, Field(min_length=1, max_length=100, description="Partial text, e.g. 'هدفون'.")],
) -> dict[str, Any]:
    """Autocomplete a vague or misspelled query into keywords, categories and brands."""
    data = (await fetch("/v1/autocomplete/", {"q": query}))["data"]
    return {
        "keywords": [k.get("keyword") for k in data.get("auto_complete") or []],
        "categories": [
            {
                "keyword": c.get("keyword"),
                "code": (c.get("category") or {}).get("code"),
                "title": (c.get("category") or {}).get("title_fa"),
            }
            for c in data.get("categories") or []
        ],
        "brands": [
            {"id": b["brand"].get("id"), "title": b["brand"].get("title_fa"), "title_en": b["brand"].get("title_en")}
            for b in data.get("advance_links") or []
            if b.get("brand")
        ],
        "trending": [t.get("keyword") for t in data.get("trends") or []],
    }


FILTER_VALUES = 15  # phone storage, cameras, screens have 20-50 values; attribute_id lists all of one


@tool("Filter options")
async def dk_filters(
    category_code: Annotated[Code | None, Field(description="e.g. 'mobile-phone'.")] = None,
    query: Annotated[str | None, Field(min_length=2, max_length=100, description="Instead of a category.")] = None,
    brand_code: Annotated[Code | None, Field(description="With category_code, e.g. 'samsung'.")] = None,
    attribute_id: Annotated[int | None, Field(ge=1, description="List all values of this one attribute.")] = None,
) -> dict[str, Any]:
    """List the filters of a category or a search: attributes, colors, sellers, price range (Toman), brands.

    Maps are {title: id}; an attribute with over 15 values has only `value_count` (call again with
    attribute_id). Pass the ids to dk_category_products or dk_search.
    """
    if category_code:
        path = f"/v1/categories/{category_code}/" + (f"brands/{brand_code}/" if brand_code else "") + "search/"
        data = (await fetch(path, {"page": 1}))["data"]
    elif query:
        data = (await fetch("/v1/search/", {"q": query, "page": 1}))["data"]
    else:
        raise ApiError("Pass a category_code (e.g. 'mobile-phone') or a query (e.g. 'هدفون بی سیم').")
    f = data.get("filters") or {}

    def options(key: str) -> list[dict[str, Any]]:
        return (f.get(key) or {}).get("options") or []

    if attribute_id:
        a = next((a for a in options("attributes") if a.get("id") == attribute_id), None)
        if a is None:
            raise ApiError(f"No attribute {attribute_id} here. Call dk_filters without attribute_id for the list.")
        return {
            "id": attribute_id,
            "title": a.get("title"),
            "values": {o.get("title_fa"): o.get("id") for o in a["options"]},
        }
    price = (f.get("price") or {}).get("options") or {}
    result: dict[str, Any] = {
        "total": (data.get("pager") or {}).get("total_items"),
        "price_range": {"min": toman(price.get("min")), "max": toman(price.get("max"))},
        # title -> id maps: a phone category has ~400 values, and repeated keys would double the size.
        # Long lists are alphabetical (1 TB, 1 GB, 1 MB, ...), so a cut list would hide common values: give the count.
        "attributes": [
            {"id": a.get("id"), "title": a.get("title"), "values": {o.get("title_fa"): o.get("id") for o in opts}}
            if len(opts) <= FILTER_VALUES
            else {"id": a.get("id"), "title": a.get("title"), "value_count": len(opts)}
            for a in options("attributes")
            for opts in [a.get("options") or []]
        ],
        "colors": {c.get("title"): c.get("id") for c in options("color_palettes")},
        "seller_types": [s.get("id") for s in options("seller_types")],
        "fast_delivery_available": "has_jet_shipment_by_seller_or_digikala" in f,
    }
    if category_code and not brand_code:
        result["brands"] = {
            b.get("code"): b.get("id") for b in options("brands")
        }  # code for brand_code, id for brand_ids
    if query:  # the search's brand facet is not the query's brands (see dk_search), its categories are
        result["categories"] = {c.get("code"): c.get("title_fa") for c in options("categories")}
    return result


_tree: list[dict[str, Any]] | None = None


@tool("Find categories")
async def dk_categories(
    query: Annotated[
        str | None,
        Field(min_length=2, max_length=100, description="Persian name (finds more) or English code, e.g. 'لپ تاپ'."),
    ] = None,
    parent_id: Annotated[int | None, Field(ge=1, description="List its sub-categories.")] = None,
    limit: Annotated[int, Field(ge=1, le=100)] = 25,
) -> dict[str, Any]:
    """Find category codes for dk_category_products and main-category ids for dk_best_sellers.

    No arguments lists the main categories. A parent category mixes in accessories: browse its leaf.
    """
    global _tree
    if _tree is None:
        # 1.7 MB for ~3200 categories; it barely changes, so load it once per process (not kept in the fetch cache).
        body = await fetch("/v1/category-tree/", cache=False)
        _tree = [
            {
                "id": c["category"]["id"],
                "code": c["category"].get("code"),
                "title": c["category"].get("title_fa"),
                "parent_id": c.get("parent_id"),
            }
            for c in body["data"]["categories"]
        ]
    children: dict[int, int] = {}
    for c in _tree:
        if c["parent_id"]:
            children[c["parent_id"]] = children.get(c["parent_id"], 0) + 1
    if query:
        q = norm(query)
        found = [c for c in _tree if q in norm(c["title"] or "") or q in (c["code"] or "")]
    else:
        found = [c for c in _tree if c["parent_id"] == parent_id]
    return {
        "categories": [{**c, "subcategories": children.get(c["id"], 0)} for c in found[:limit]],
        "found": len(found),
    }


@tool("Browse a category")
async def dk_category_products(
    category_code: Annotated[Code, Field(description="e.g. 'mobile-phone'.")],
    sort: Sort = "relevance",
    min_price: MinPrice = None,
    max_price: MaxPrice = None,
    brand_code: Annotated[Code | None, Field(description="e.g. 'xiaomi'.")] = None,
    brand_ids: SameBrandIds = None,
    attributes: SameAttributes = None,
    colors: SameColors = None,
    seller_type: SellerType = None,
    fast_delivery: FastDelivery = False,
    ready_to_ship: ReadyToShip = False,
    in_stock_only: InStock = True,
    page: Page = 1,
) -> dict[str, Any]:
    """List one category's products with sort and filters (price in Toman), strict order.

    No text query. Filter ids: dk_filters(category_code=...).
    """
    path = f"/v1/categories/{category_code}/" + (f"brands/{brand_code}/" if brand_code else "") + "search/"
    params = {
        **listing_params(sort, min_price, max_price, brand_ids, in_stock_only, page),
        **filter_params(attributes, colors, seller_type, fast_delivery, ready_to_ship),
    }
    return listing((await fetch(path, params))["data"])


@tool("Browse a brand")
async def dk_brand_products(
    brand_code: Annotated[Code, Field(description="Lowercase English name, e.g. 'samsung'.")],
    sort: Sort = "relevance",
    min_price: MinPrice = None,
    max_price: MaxPrice = None,
    in_stock_only: InStock = True,
    page: Page = 1,
) -> dict[str, Any]:
    """List a brand's products with sort and price filters (Toman), plus the brand id for brand_ids.

    One brand in one category: dk_category_products(brand_code=...).
    """
    data = (
        await fetch(f"/v1/brands/{brand_code}/", listing_params(sort, min_price, max_price, None, in_stock_only, page))
    )["data"]
    b = data.get("brand") or {}
    result = {"brand": {"id": b.get("id"), "code": b.get("code"), "title": b.get("title_fa")}, **listing(data)}
    if in_stock_only:  # the brand listing still mixes in out_of_stock items with has_selling_stock
        result["products"] = [p for p in result["products"] if p["in_stock"]]
    return result


@tool("Seller profile and products")
async def dk_seller(
    seller_code: Annotated[
        str,
        Field(
            pattern=r"^[A-Za-z0-9]{3,12}$",
            description="dk_product offer seller_code, e.g. 'CGDG9'.",
        ),
    ],
    sort: Sort = "best_selling",
    in_stock_only: InStock = True,
    page: Page = 1,
) -> dict[str, Any]:
    """Get a seller's reputation (rating 0-5, on-time shipping, cancellations, returns) and products.

    Percentages are the share of good orders (100 = never late).
    """
    data = (await fetch(f"/v1/sellers/{seller_code}/", listing_params(sort, None, None, None, in_stock_only, page)))[
        "data"
    ]
    s = data.get("seller") or {}
    rating, stats, props = s.get("rating") or {}, s.get("statistics") or {}, s.get("properties") or {}
    return {
        "seller": {
            "code": s.get("code"),
            "title": s.get("title"),
            "rating": stars(rating.get("total_rate")),
            "rating_count": rating.get("total_count"),
            "grade": (s.get("grade") or {}).get("label"),
            "on_time_shipping_pct": stats.get("ship_on_time"),
            "no_cancellation_pct": stats.get("cancellation"),
            "no_return_pct": stats.get("return"),
            "member_for": s.get("registration_date"),
            "is_trusted": props.get("is_trusted"),
            "is_official": props.get("is_official"),
            "url": f"{SITE}/seller/{s.get('code') or seller_code}/",
        },
        **listing(data),
    }


@tool("Current deals")
async def dk_deals(
    store: Annotated[
        Literal["digikala", "supermarket"],
        Field(description="'supermarket' = Fresh grocery deals."),
    ] = "digikala",
    query: Annotated[str | None, Field(min_length=2, max_length=100, description="Narrow the deals.")] = None,
    sort: Annotated[
        Literal["biggest_discount", "cheapest", "most_expensive", "best_selling", "most_viewed", "newest"], Field()
    ] = "biggest_discount",
    min_price: MinPrice = None,
    max_price: MaxPrice = None,
    page: Page = 1,
) -> dict[str, Any]:
    """List today's Incredible Offers (flash deals), biggest discount first, in-stock only.

    deal_ends is Tehran time.
    """
    params = {**listing_params(sort, min_price, max_price, None, True, page), "q": query or ""}
    path = "/fresh/v1/incredible-offers/products/" if store == "supermarket" else "/v1/incredible-offers/products/"
    return listing((await fetch(path, params))["data"])


@tool("Best sellers")
async def dk_best_sellers(
    category_id: Annotated[
        int | None,
        Field(
            ge=1,
            description="Main category id (this tool's `categories`), e.g. 1 mobile. Leaf ids fail.",
        ),
    ] = None,
    limit: Annotated[int, Field(ge=1, le=50)] = 10,
) -> dict[str, Any]:
    """List current best sellers, overall or in one main category; also returns the main categories' ids for category_id."""
    try:
        data = (await fetch("/v1/best-selling/", {"category_id": category_id} if category_id else None))["data"]
    except ApiError as e:
        if e.status != 400:
            raise
        raise ApiError(
            f"category_id {category_id} is not a main category. Use a main category id (e.g. 1 mobile, "
            "5966 electronic-devices); call dk_best_sellers() or dk_categories() with no arguments for the list.",
            400,
        ) from e
    return {
        "products": [card(p) for p in data.get("products") or []][:limit],
        "categories": [
            {"id": c.get("id"), "code": c.get("code"), "title": c.get("title_fa")} for c in data.get("categories") or []
        ],
    }


@tool("Search groceries")
async def dk_fresh_search(
    query: Annotated[
        str | None,
        Field(min_length=2, max_length=100, description="Persian works best, e.g. 'شیر کم چرب'."),
    ] = None,
    category_code: Annotated[
        Code | None,
        Field(
            description="Instead of query: groceries, dairy, snacks, protein-foods, breakfast, beverages, warm-drinks, fruits-and-vegetables, personal-hygiene, baby-and-mother, home-hygiene, dried-fruit-nuts, ready-made-canned-food, condiments, frozen-food, salts-and-pickles, or a returned sub-category."
        ),
    ] = None,
    sort: Annotated[
        Literal["relevance", "cheapest", "most_expensive", "best_selling", "most_viewed", "newest", "buyers_pick"],
        Field(),
    ] = "relevance",
    min_price: MinPrice = None,
    max_price: MaxPrice = None,
    in_stock_only: InStock = True,
    page: Page = 1,
) -> dict[str, Any]:
    """Search or browse Digikala Fresh (supermarket). category_code beats query and also returns sub-categories."""
    params = listing_params(sort, min_price, max_price, None, in_stock_only, page)
    if category_code:
        data = (await fetch(f"/fresh/v1/categories/{category_code}/search/", params))["data"]
    elif query:
        data = (await fetch("/fresh/v1/search/", {"q": query, **params}))["data"]
    else:
        raise ApiError("Pass a query (e.g. 'شیر') or a category_code (e.g. 'dairy').")
    result = listing(data)
    if in_stock_only:  # Fresh keeps 'in_supply' items (no offer, no price) even with has_selling_stock
        result["products"] = [p for p in result["products"] if p["in_stock"]]
    # a query that hits nothing still lists every Fresh category, so only browsing returns them
    subs = (((data.get("filters") or {}).get("categories") or {}).get("options") or []) if category_code else []
    return {**result, "subcategories": [{"code": c.get("code"), "title": c.get("title_fa")} for c in subs]}


def listing_params(
    sort: str, min_price: int | None, max_price: int | None, brand_ids: list[int] | None, in_stock: bool, page: int
) -> dict[str, Any]:
    """Shared listing query; the API takes prices in Rial."""
    params: dict[str, Any] = {"page": page, "sort": SORTS[sort]}
    if in_stock:
        params["has_selling_stock"] = 1
    for i, b in enumerate(brand_ids or []):
        params[f"brands[{i}]"] = b
    return {**params, **_prices(min_price, max_price)}


def filter_params(
    attributes: dict[int, list[int]] | None,
    colors: list[int] | None,
    seller_type: str | None,
    fast_delivery: bool,
    ready_to_ship: bool,
) -> dict[str, Any]:
    """Facet filters in the site's query format (ids from dk_filters)."""
    params: dict[str, Any] = {}
    for attr, values in (attributes or {}).items():
        for i, v in enumerate(values):
            params[f"attributes[{attr}][{i}]"] = v
    for i, c in enumerate(colors or []):
        params[f"color_palettes[{i}]"] = c
    if seller_type:
        params["seller_types[0]"] = seller_type
    if fast_delivery:
        params["has_jet_shipment_by_seller_or_digikala"] = 1
    if ready_to_ship:
        params["has_ready_to_shipment"] = 1
    return params


def _prices(min_price: int | None, max_price: int | None) -> dict[str, int]:
    """Toman -> Rial price range. The API returns nothing for price[min] without price[max]."""
    if min_price is None and max_price is None:
        return {}
    return {"price[min]": (min_price or 0) * 10, "price[max]": (max_price if max_price is not None else 10**12) * 10}


def listing(data: dict[str, Any]) -> dict[str, Any]:
    pager = data.get("pager") or {}
    return {
        "total": pager.get("total_items"),
        "page": pager.get("current_page"),
        "total_pages": pager.get("total_pages"),
        "products": [card(p) for p in data.get("products") or []],
    }


def card(p: dict[str, Any]) -> dict[str, Any]:
    """Compact product card. Unsellable products have no default_variant ([] or null) and no price.

    Null fields, a zero discount and a zero rating count are left out (a listing repeats 20 cards);
    the link is SITE/product/dkp-<id>/ (INSTRUCTIONS) and the photo is only in dk_product.
    """
    v = p.get("default_variant") or {}
    price = v.get("price") or {}
    rating = p.get("rating") or {}
    discount = price.get("discount_percent") or 0
    c = {
        "id": p.get("id"),
        "title": p.get("title_fa"),
        "brand": (p.get("data_layer") or {}).get("brand"),
        "price": toman(price.get("selling_price")),
        "price_before_discount": toman(price.get("rrp_price")) if discount else None,
        "discount_pct": discount or None,
        "in_stock": p.get("status") == "marketable" and bool(price),
        "seller": (v.get("seller") or {}).get("title"),
        "rating": stars(rating.get("rate")),
        "rating_count": rating.get("count") or None,
    }
    if price.get("is_incredible") and price.get("time"):  # only flash-deal cards have it
        c["deal_ends"] = price["time"]
    return {k: x for k, x in c.items() if x is not None}


def image_url(img: dict[str, Any] | None) -> str | None:
    """First https URL of an API image ({"url": [...]}); the API serves a 300 px JPEG."""
    return next((u for u in (img or {}).get("url") or [] if u.startswith("https://")), None)


def toman(rial: int | None) -> int | None:
    """Digikala prices are Rial; the site shows Toman."""
    return rial // 10 if rial else None


def stars(rate100: float | None) -> float | None:
    """Product and seller ratings are 0-100; the site shows rate / 20 on 0-5 (0 = not rated)."""
    return math.floor(rate100 / 2 + 0.5) / 10 if rate100 else None  # half-up like the site: 87 -> 4.4


def norm(text: str) -> str:
    """Treat Arabic ي/ك as Persian ی/ک, Persian digits as ASCII and the half-space as a space."""
    text = text.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
    return text.replace("ي", "ی").replace("ك", "ک").replace("\u200c", " ").lower().strip()
