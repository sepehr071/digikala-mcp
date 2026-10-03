import pytest
from conftest import fixture

pytestmark = pytest.mark.anyio


async def test_dk_plus_plans(client, api):
    api["/v1/digiplus/plans/"] = fixture("plus_plans.json")
    data = (await client.call_tool("dk_plus_plans", {})).structured_content
    three = data["plans"][1]
    # 9,000,000 Rial - 4,010,000 Rial discount = 499,000 Toman, as on the Plus page
    assert three["price"] == 499000 and three["price_before_discount"] == 900000 and three["discount_pct"] == 45
    assert three["days"] == 93 and three["free_shipments"] == 12
    assert data["benefits"][0] == "ارسال رایگان"


async def test_dk_gold_prices(client, api):
    api["/v1/super-app/price-list/"] = fixture("gold_list.json")
    gold = fixture("gold18.json")
    gold["data"]["chart"]["data"] = {"y": [25679800, 26185800, 26072500]}  # the real chart has ~97 daily points
    api["/v1/super-app/price-chart/gold18/"] = gold
    data = (await client.call_tool("dk_gold_prices", {})).structured_content
    # already Toman: not divided by 10
    assert data["gold18_per_gram"] == 26072500 and data["gold18_period_low"] == 25679800
    # the API's change is over the whole chart; the day change is from the previous point
    assert data["gold18_period_change_pct"] == 1.53 and data["gold18_day_change_pct"] == -0.43
    assert data["coins"][0] == {"title": "سکه امامی", "price": 266317700, "change_pct": -0.49}
    assert data["coins"][1]["price"] is None  # not for sale


async def test_dk_location_geocode(client, api):
    api["/v1/map/geo/"] = fixture("geo.json")
    data = (await client.call_tool("dk_location", {"address": "میدان ونک", "city": "تهران"})).structured_content
    assert data["places"][0] == {"title": "م. ونک", "address": "تهران،م. ونک", "lat": 35.757535, "long": 51.40994}
    assert api.calls[0].url.params["city"] == "تهران"


async def test_dk_location_reverse(client, api):
    api["/v1/map/reverse-geo/"] = fixture("reverse_geo.json")
    data = (await client.call_tool("dk_location", {"lat": 35.7575, "long": 51.41})).structured_content
    assert data == {"address": "م. ونک", "city": "تهران", "city_id": 1698, "province": "تهران", "state_id": 9}
    assert api.calls[0].url.params["latitude"] == "35.7575"


async def test_dk_location_needs_input(client, api):
    result = await client.call_tool("dk_location", {"city": "تهران"})
    assert result.is_error and not api.calls
    outside = await client.call_tool("dk_location", {"lat": 48.85, "long": 2.35})
    assert outside.is_error and not api.calls
