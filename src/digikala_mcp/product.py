"""Tools about one Digikala product: offers, price history, reviews, Q&A, alternatives, specs, installments."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field

from .catalog import InStock, Page, Sort, card, listing, listing_params, stars, toman
from .http import SITE, ApiError, fetch
from .registry import tool

ProductId = Annotated[
    int,
    Field(
        ge=1,
        le=10**9,
        description="Digikala product id, the number in 'dkp-<id>' (from dk_search etc.), e.g. 20109389.",
    ),
]

ANSWERS_PER_QUESTION = 2
TEXT_CHARS = 300  # a few reviews and answers are essays; keep a page of 20 small


@tool("Product details and offers")
async def dk_product(
    product_id: ProductId,
    max_offers: Annotated[int, Field(ge=1, le=50, description="Max seller offers to return, cheapest first.")] = 15,
    include_specs: Annotated[bool, Field(description="Include the specification table.")] = True,
) -> dict[str, Any]:
    """Get one product's price, stock, rating, specs and every seller's offer (cheapest first).

    Each offer is one color/size from one seller, with price in Toman, stock_left (only
    shown when low), warranty, seller rating 0-5 and shipping (ships_by: 'digikala',
    'jet' = same-day in Tehran/Karaj, 'seller'; free_shipping when the seller ships free). lowest_price_30d helps judge today's price;
    dk_price_history has the daily curve. Exact shipping cost is only known at checkout.
    Grocery items come from the supermarket store (store='supermarket'): its price can differ
    from the main-store price that dk_search, dk_compare and dk_price_history show.
    """
    store = "digikala"
    try:
        p = (await fetch(f"/product/v1/products/{product_id}/"))["data"]["product"]
    except ApiError as e:
        if e.status != 301:
            raise
        # Fresh (supermarket) products live on their own service; the main one answers status 301.
        p = (await fetch(f"/fresh/v1/product/{product_id}/"))["data"]["product"]
        store = "supermarket"
    if p.get("is_inactive"):
        raise ApiError(
            f"Product {product_id} does not exist or is no longer listed. Find it again with dk_search.", 404
        )
    offers = sorted((_offer(v) for v in p.get("variants") or []), key=lambda o: o["price"] or float("inf"))
    brand, category = p.get("brand") or {}, p.get("category") or {}
    result = {
        **card(p),
        "store": store,
        "title_en": p.get("title_en"),
        "brand_id": brand.get("id"),
        "brand_code": brand.get("code"),
        "category": {"id": category.get("id"), "code": category.get("code"), "title": category.get("title_fa")},
        "lowest_price_30d": toman((p.get("properties") or {}).get("min_price_in_last_month")),
        "colors": [c.get("title") for c in p.get("colors") or []],
        "comments_count": p.get("comments_count"),
        "questions_count": p.get("questions_count"),
        "offers_count": len(offers),
        "offers": offers[:max_offers],
    }
    if store == "supermarket":  # where the main service's 301 points
        result["url"] = f"{SITE}/supermarket/product/{product_id}/"
    if include_specs:
        result["specs"] = {
            g.get("title"): {
                a.get("title"): ", ".join(str(x).strip() for x in a.get("values") or [])
                for a in g.get("attributes") or []
            }
            for g in p.get("specifications") or []
        }
    return result


@tool("Price history")
async def dk_price_history(product_id: ProductId) -> dict[str, Any]:
    """Get about 30 days of daily buy-box prices (Toman) per color/variant, with lowest and highest.

    Use to answer "is this a good price right now?". Days are Jalali (YYYY/MM/DD); days when
    the variant was not for sale are left out. An unknown id gives no variants; check it with dk_product.
    """
    data = (await fetch(f"/v1/product/{product_id}/price-chart/"))["data"]
    variants = []
    for c in data.get("price_chart") or []:
        days = [
            {"day": h.get("day"), "price": toman(h.get("selling_price"))}
            for h in c.get("history") or []
            if h.get("is_marketable") and h.get("selling_price")
        ]
        prices = [d["price"] for d in days]
        variants.append(
            {
                "variant": c.get("title"),
                "last_price": prices[-1] if prices else None,
                "lowest": min(prices, default=None),
                "highest": max(prices, default=None),
                "days": days,
            }
        )
    return {"today": data.get("today"), "variants": variants}


@tool("Product reviews")
async def dk_reviews(
    product_id: ProductId,
    sort: Annotated[
        Literal["most_helpful", "newest", "buyers_first"], Field(description="Order of the reviews.")
    ] = "most_helpful",
    page: Page = 1,
) -> dict[str, Any]:
    """Read customer reviews of a product: stars 1-5 (null = no stars given), text, pros/cons, verified buyer flag.

    20 per page. The overall rating (0-5) is in dk_product. Long texts are cut to 300 characters.
    An unknown id gives no reviews; check it with dk_product.
    """
    api_sort = {"most_helpful": "default", "newest": "newest", "buyers_first": "buyers"}[sort]
    data = (await fetch(f"/v1/rate-review/products/{product_id}/", {"page": page, "sort": api_sort}))["data"]
    pager = data.get("pager") or {}
    reviews = []
    for c in data.get("comments") or []:
        item = c.get("purchased_item") or {}
        reactions = c.get("reactions") or {}
        text = c.get("body") or ""
        reviews.append(
            {
                "rating": c.get("rate") or None,
                "text": _cut(text),
                "pros": c.get("advantages") or [],
                "cons": c.get("disadvantages") or [],
                "date": c.get("created_at"),
                "verified_buyer": bool(c.get("is_buyer")),
                "likes": reactions.get("likes"),
                "dislikes": reactions.get("dislikes"),
                "seller": (item.get("seller") or {}).get("title"),
                "variant": (item.get("color") or {}).get("title"),
            }
        )
    return {
        "total": pager.get("total_items"),
        "page": pager.get("current_page"),
        "total_pages": pager.get("total_pages"),
        "reviews": reviews,
    }


@tool("Product questions and answers")
async def dk_questions(
    product_id: ProductId,
    sort: Annotated[Literal["newest", "most_answered"], Field(description="Order of the questions.")] = "most_answered",
    page: Page = 1,
) -> dict[str, Any]:
    """Read customers' questions about a product and up to 2 answers each (answered_by: buyer, seller, ...).

    20 questions per page; long texts are cut to 300 characters. Use for practical doubts
    (compatibility, size, registration).
    """
    api_sort = {"newest": "created_at", "most_answered": "answers"}[sort]
    data = (await fetch(f"/v1/product/{product_id}/questions/", {"page": page, "sort": api_sort}))["data"]
    pager = data.get("pager") or {}
    return {
        "total": pager.get("total_items"),
        "page": pager.get("current_page"),
        "total_pages": pager.get("total_pages"),
        "questions": [
            {
                "text": _cut(q.get("text")),
                "date": q.get("created_at"),
                "answer_count": q.get("answer_count"),
                "answers": [
                    {
                        "text": _cut(a.get("text")),
                        "answered_by": a.get("type"),
                        "likes": (a.get("reactions") or {}).get("likes"),
                    }
                    for a in (q.get("answers") or [])[:ANSWERS_PER_QUESTION]
                ],
            }
            for q in data.get("questions") or []
        ],
    }


@tool("Similar products")
async def dk_similar(
    product_id: ProductId,
    sort: Sort = "relevance",
    in_stock_only: InStock = True,
    page: Page = 1,
) -> dict[str, Any]:
    """List products similar to one product (same kind, other models and brands).

    Use sort='cheapest' for cheaper alternatives. Compare two or more with dk_compare.
    """
    try:
        data = (
            await fetch(
                f"/v1/products/{product_id}/similar/", listing_params(sort, None, None, None, in_stock_only, page)
            )
        )["data"]
    except ApiError as e:
        if e.status != 400:  # the API answers 400 "empty <ARRAY>" for an unknown id
            raise
        raise ApiError(f"Product {product_id} not found. Check the product id with dk_product.", 404) from e
    return listing(data)


@tool("Compare products")
async def dk_compare(
    product_ids: Annotated[
        list[int],
        Field(min_length=2, max_length=4, description="2-4 product ids of the same kind, e.g. [20109389, 20110013]."),
    ],
) -> dict[str, Any]:
    """Compare 2-4 products side by side: price and rating, then the spec rows where they differ.

    `values` in each `specs` row follow the order of `products`; null means the product has no
    such spec. Rows where every product has the same value are folded into `same_specs`
    ("group / name" -> value). Works best for products of the same category. Unknown ids are
    left out and listed in `missing_ids`.
    """
    params = {f"product_ids[{i}]": pid for i, pid in enumerate(product_ids)}
    items = (await fetch("/v1/product/compare/", params))["data"]["compare_products"]
    rows: dict[tuple[str, str], list[str | None]] = {}
    for i, item in enumerate(items):
        for g in item.get("attribute_groups") or []:
            for a in g.get("attributes") or []:
                row = rows.setdefault((g.get("title"), a.get("title")), [None] * len(items))
                row[i] = ", ".join(str(x).strip() for x in a.get("values") or []) or None
    products = [card(item.get("product") or {}) for item in items]
    same = {k: v[0] for k, v in rows.items() if len(items) > 1 and v[0] is not None and v.count(v[0]) == len(v)}
    return {
        "products": products,
        "missing_ids": [pid for pid in product_ids if pid not in {p["id"] for p in products}],
        "specs": [{"group": g, "name": n, "values": v} for (g, n), v in rows.items() if (g, n) not in same],
        "same_specs": {f"{g} / {n}": v for (g, n), v in same.items()},
    }


@tool("Installment plans")
async def dk_installments(product_id: ProductId) -> dict[str, Any]:
    """Get the Digipay credit-line offers available when buying a product, in Toman.

    Each plan is a fixed credit line (credit_amount), repaid in `months` installments of
    monthly_repayment; it is not sized to the product price (the credit can be larger), so do
    not present it as "this product for X a month". Get the price from dk_product. How the
    credit and the price combine at checkout is unconfirmed. Needs Digipay approval. An unknown
    id gives no plans; check it with dk_product.
    """
    data = (await fetch(f"/v1/product/{product_id}/digipay-credit/"))["data"]
    plans: dict[tuple[Any, ...], dict[str, Any]] = {}
    for variant_id, x in (data.get("items") or {}).items():
        key = (x.get("installment_amount"), x.get("installment_count"), x.get("credit_amount"))
        plan = plans.setdefault(
            key,
            {
                "credit_amount": toman(x.get("credit_amount")),
                "monthly_repayment": toman(x.get("installment_amount")),
                "months": x.get("installment_count"),
                "variant_ids": [],
            },
        )
        plan["variant_ids"].append(int(variant_id))
    return {"plans": list(plans.values())}


def _cut(text: str | None) -> str | None:
    return text if not text or len(text) <= TEXT_CHARS else text[:TEXT_CHARS] + "…"


def _offer(v: dict[str, Any]) -> dict[str, Any]:
    price, seller = v.get("price") or {}, v.get("seller") or {}
    shipping = v.get("shipment_methods") or {}
    return {
        "variant_id": v.get("id"),
        "variant": " / ".join(t["value"].get("title") for t in v.get("themes") or [] if t.get("value")) or None,
        "price": toman(price.get("selling_price")),
        "price_before_discount": toman(price.get("rrp_price")),
        "discount_pct": price.get("discount_percent") or 0,
        "stock_left": price.get("marketable_stock"),
        "seller": seller.get("title"),
        "seller_code": seller.get("code"),
        "seller_rating": stars((seller.get("rating") or {}).get("total_rate")),
        "warranty": (v.get("warranty") or {}).get("title_fa"),
        "shipping": shipping.get("description"),
        "ships_by": [s.get("type") or s.get("title") for s in shipping.get("providers") or []],
        "free_shipping": any((s.get("price") or {}).get("is_free") for s in shipping.get("providers") or []),
        "lead_time_days": v.get("lead_time"),
    }
