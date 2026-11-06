"""Tools about one Digikala product: offers, price history, reviews, Q&A, alternatives, specs, installments."""

from __future__ import annotations

import asyncio
from itertools import pairwise
from typing import Annotated, Any, Literal

from pydantic import Field

from .catalog import InStock, Page, Sort, card, image_url, listing, listing_params, stars, toman
from .http import SITE, ApiError, fetch
from .registry import tool

ProductId = Annotated[int, Field(ge=1, le=10**9)]  # INSTRUCTIONS: the number in dkp-<id>

FullText = Annotated[bool, Field(description="No text cuts.")]

ANSWERS_PER_QUESTION = 2
TEXT_CHARS = 300  # a few reviews and answers are essays; keep a page of 20 small
PROCON_ITEMS, PROCON_CHARS = 5, 80


@tool("Product details and offers")
async def dk_product(
    product_id: ProductId,
    max_offers: Annotated[int, Field(ge=1, le=50)] = 15,
    include_specs: Annotated[bool, Field()] = True,
) -> dict[str, Any]:
    """Get one product's price, stock, rating, specs and every seller's offer (cheapest first).

    An offer is one color/size from one seller; stock_left only when low; ships_by 'jet' = same-day
    Tehran/Karaj. lowest_price_30d can be a one-day dip (dk_price_history's lowest_2_days is steadier).
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
    offers = sorted((_offer(v) for v in p.get("variants") or []), key=lambda o: o.get("price") or float("inf"))
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
        "images": [u for u in map(image_url, (p.get("images") or {}).get("list") or []) if u][:4],
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
    """Get ~30 days of daily buy-box prices (Toman) per color/variant, with lowest and highest.

    `lowest_2_days` is the lowest price held two days in a row (`lowest` can be a one-day dip). Days are Jalali.
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
                "lowest_2_days": held_low(prices),
                "highest": max(prices, default=None),
                "days": days,
            }
        )
    return {"today": data.get("today"), "variants": variants}


def held_low(prices: list[int]) -> int | None:
    """Lowest price that held on two days in a row: a one-day dip (a flash sale, a mispriced offer) is skipped.

    Seen 2026-10-05: one color of 20109389 sold for 28.4M on one day, while every other day of the month was 33.2M+.
    """
    return min((max(a, b) for a, b in pairwise(prices)), default=None)


@tool("Product reviews")
async def dk_reviews(
    product_id: ProductId,
    sort: Annotated[Literal["most_helpful", "newest", "buyers_first"], Field()] = "most_helpful",
    page: Page = 1,
    limit: Annotated[int, Field(ge=1, le=20, description="Of the page's 20.")] = 10,
    full_text: FullText = False,
) -> dict[str, Any]:
    """Read customer reviews: stars 1-5 (null = none), text, pros/cons, verified buyer flag.

    Texts are cut to 300 characters, pros/cons to 5 of 80 (full_text=true: whole).
    """
    chars, procon_chars, procon_items = (None, None, None) if full_text else (TEXT_CHARS, PROCON_CHARS, PROCON_ITEMS)
    api_sort = {"most_helpful": "default", "newest": "newest", "buyers_first": "buyers"}[sort]
    data = (await fetch(f"/v1/rate-review/products/{product_id}/", {"page": page, "sort": api_sort}))["data"]
    pager = data.get("pager") or {}
    reviews = []
    for c in (data.get("comments") or [])[:limit]:
        item = c.get("purchased_item") or {}
        reactions = c.get("reactions") or {}
        review = {
            "rating": c.get("rate") or None,
            "text": _cut(c.get("body") or "", chars),
            "pros": [_cut(x, procon_chars) for x in (c.get("advantages") or [])[:procon_items]],
            "cons": [_cut(x, procon_chars) for x in (c.get("disadvantages") or [])[:procon_items]],
            "date": c.get("created_at"),
            "verified_buyer": bool(c.get("is_buyer")),
            "likes": reactions.get("likes"),
            "dislikes": reactions.get("dislikes"),
            "seller": (item.get("seller") or {}).get("title"),
            "variant": (item.get("color") or {}).get("title"),
        }
        reviews.append({k: v for k, v in review.items() if v is not None and v != []})
    return {
        "total": pager.get("total_items"),
        "page": pager.get("current_page"),
        "total_pages": pager.get("total_pages"),
        "reviews": reviews,
    }


@tool("Product questions and answers")
async def dk_questions(
    product_id: ProductId,
    sort: Annotated[Literal["newest", "most_answered"], Field()] = "most_answered",
    page: Page = 1,
    full_text: FullText = False,
) -> dict[str, Any]:
    """Read customers' questions (20 per page) with up to 2 answers each (answered_by: buyer, seller, ...).

    Texts are cut to 300 characters (full_text=true: whole).
    """
    chars = None if full_text else TEXT_CHARS
    api_sort = {"newest": "created_at", "most_answered": "answers"}[sort]
    data = (await fetch(f"/v1/product/{product_id}/questions/", {"page": page, "sort": api_sort}))["data"]
    pager = data.get("pager") or {}
    return {
        "total": pager.get("total_items"),
        "page": pager.get("current_page"),
        "total_pages": pager.get("total_pages"),
        "questions": [
            {
                "text": _cut(q.get("text"), chars),
                "date": q.get("created_at"),
                "answer_count": q.get("answer_count"),
                "answers": [
                    {
                        "text": _cut(a.get("text"), chars),
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
    """List products similar to one (same kind, other models and brands); sort='cheapest' for cheaper ones."""
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
        Field(min_length=2, max_length=4, description="Same kind, e.g. [20109389, 20110013]."),
    ],
) -> dict[str, Any]:
    """Compare 2-4 products side by side: price and rating, then the spec rows where they differ.

    A `specs` row's `values` follow `products` order (null = no such spec); identical rows fold into `same_specs`.
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


SHORTLIST_KEYS = (
    "id",
    "title",
    "image",
    "price",
    "price_before_discount",
    "discount_pct",
    "in_stock",
    "rating",
    "rating_count",
)


@tool("Re-check a shortlist")
async def dk_shortlist(
    product_ids: Annotated[
        list[int],
        Field(min_length=1, max_length=10, description="e.g. [20109389, 20110013]."),
    ],
) -> dict[str, Any]:
    """Re-price up to 10 products in one call: price, cheapest offer, stock, rating and 30-day low (Toman).

    `low_30d` is the lowest price held two days in a row, `vs_30d_low_pct` today's price above it.
    """
    # the history is only an extra: a failed chart leaves low_30d null instead of dropping the product
    found, charts = await asyncio.gather(
        asyncio.gather(
            *(dk_product(pid, max_offers=1, include_specs=False) for pid in product_ids), return_exceptions=True
        ),
        asyncio.gather(*(dk_price_history(pid) for pid in product_ids), return_exceptions=True),
    )
    rows, errors = [], []
    for pid, p, chart in zip(product_ids, found, charts, strict=True):
        if isinstance(p, ApiError):
            errors.append({"id": pid, "error": str(p)})
            continue
        if isinstance(p, BaseException):
            raise p
        offer = (p["offers"] or [{}])[0]
        lows = [] if isinstance(chart, BaseException) else [v["lowest_2_days"] for v in chart["variants"]]
        low = min((x for x in lows if x), default=None)
        rows.append(
            {
                **{k: p[k] for k in SHORTLIST_KEYS if k in p},
                "cheapest_offer": offer.get("price"),
                "cheapest_seller": offer.get("seller"),
                "offers_count": p["offers_count"],
                "low_30d": low,
                "vs_30d_low_pct": round(100 * (p["price"] - low) / low) if p.get("price") and low else None,
                "lowest_one_day_30d": p["lowest_price_30d"],
                "url": p["url"],
            }
        )
    return {"products": rows, "errors": errors}


@tool("Installment plans")
async def dk_installments(product_id: ProductId) -> dict[str, Any]:
    """Get the Digipay credit-line offers for a product, in Toman.

    A plan is a fixed credit line repaid in `months` installments, not sized to the product price:
    never present it as "this product for X a month".
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
    if not plans:  # since 2026-10-05 every product answers no items, and the product page shows no credit box either
        return {"plans": [], "note": "Digikala offers no Digipay credit plan for this product right now."}
    return {"plans": list(plans.values())}


def _cut(text: str | None, chars: int | None) -> str | None:
    return text if not text or chars is None or len(text) <= chars else text[:chars] + "…"


def _offer(v: dict[str, Any]) -> dict[str, Any]:
    price, seller = v.get("price") or {}, v.get("seller") or {}
    shipping = v.get("shipment_methods") or {}
    discount = price.get("discount_percent") or 0
    offer = {
        "variant_id": v.get("id"),
        "variant": " / ".join(t["value"].get("title") for t in v.get("themes") or [] if t.get("value")) or None,
        "price": toman(price.get("selling_price")),
        "price_before_discount": toman(price.get("rrp_price")) if discount else None,
        "discount_pct": discount or None,
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
    return {k: x for k, x in offer.items() if x is not None}  # like cards: no nulls, no zero discount
