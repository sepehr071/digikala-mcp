"""Digikala Plus plans, gold and coin prices, and location lookups."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field

from .catalog import toman
from .http import ApiError, fetch
from .registry import tool


@tool("Digikala Plus plans")
async def dk_plus_plans() -> dict[str, Any]:
    """List Digikala Plus membership plans (free shipments) with their price in Toman and benefits.

    Use when shipping cost matters: Plus members get a number of free deliveries per month
    (jet = same-day Tehran/Karaj, fresh = supermarket). Exact shipping fees are only shown at checkout.
    """
    data = (await fetch("/v1/digiplus/plans/"))["data"]
    return {
        "plans": [
            {
                "id": p.get("id"),
                "title": p.get("title"),
                "days": p.get("number_of_days"),
                "price": toman(p.get("total_payable_price")),
                "price_before_discount": toman(p.get("price")),
                "discount_pct": p.get("discount_percent") or 0,
                "free_shipments": p.get("free_shipment_count"),
                "fresh_free_shipments": p.get("fresh_free_shipment_count"),
                "jet_free_shipments": p.get("jet_free_shipment_count"),
                "note": (p.get("message") or {}).get("description"),
            }
            for p in data.get("plans") or []
        ],
        "benefits": [s.get("title") for s in data.get("services") or []],
    }


@tool("Gold and coin prices")
async def dk_gold_prices() -> dict[str, Any]:
    """Get Digikala's live 18k gold price per gram and gold coin prices, in Toman.

    gold18_day_change_pct is the change since the previous daily point; gold18_period_change_pct,
    low and high cover the ~3-month chart. Coins' change_pct is as Digikala shows it (its period
    is not documented). Coins with price null are not for sale right now.
    """
    coins = (await fetch("/v1/super-app/price-list/"))["data"]
    gold = (await fetch("/v1/super-app/price-chart/gold18/"))["data"]
    chart = gold.get("chart") or {}
    y = (chart.get("data") or {}).get("y") or []
    # Both endpoints already answer in Toman, unlike product prices.
    return {
        "gold18_per_gram": gold.get("last_price") or None,
        "gold18_day_change_pct": round((y[-1] / y[-2] - 1) * 100, 2) if len(y) > 1 and y[-2] else None,
        "gold18_period_change_pct": (chart.get("change") or {}).get("percentage"),
        "gold18_period_low": chart.get("min"),
        "gold18_period_high": chart.get("max"),
        "coins": [
            {
                "title": c.get("title"),
                "price": c.get("price") or None,
                "change_pct": (c.get("change") or {}).get("percentage"),
            }
            for c in coins.get("values") or []
        ],
        "updated": coins.get("updated_at"),
    }


@tool("Find location")
async def dk_location(
    address: Annotated[
        str | None,
        Field(
            min_length=2,
            max_length=200,
            description="Address or landmark in Persian, e.g. 'میدان ونک'. Latin text matches poorly.",
        ),
    ] = None,
    city: Annotated[
        str | None,
        Field(
            max_length=50,
            description="Persian city name; without it most addresses find nothing, e.g. 'تهران' or 'مشهد'.",
        ),
    ] = None,
    lat: Annotated[
        float | None, Field(ge=24, le=40, description="Latitude, to describe a point instead (Iran: ~25 to ~40).")
    ] = None,
    long: Annotated[float | None, Field(ge=44, le=64, description="Longitude, with lat.")] = None,
) -> dict[str, Any]:
    """Turn an address into coordinates, or coordinates into an address with Digikala's city_id and state_id.

    Pass address + city, or lat + long. Product prices are the
    same everywhere; location only matters for delivery options shown at checkout.
    """
    if lat is not None and long is not None:
        a = (await fetch("/v1/map/reverse-geo/", {"latitude": lat, "longitude": long}))["data"].get("address") or {}
        return {
            "address": a.get("address"),
            "city": a.get("city_name"),
            "city_id": a.get("city_id"),
            "province": a.get("state_name"),
            "state_id": a.get("state_id"),
        }
    if not address:
        raise ApiError("Pass an address (e.g. 'میدان ونک' with city 'تهران') or lat and long.")
    params = {"address": address, "city": city} if city else {"address": address}
    data = (await fetch("/v1/map/geo/", params))["data"]
    return {
        "places": [
            {"title": p.get("title"), "address": p.get("address"), "lat": p.get("latitude"), "long": p.get("longitude")}
            for p in data.get("addresses") or []
        ]
    }
