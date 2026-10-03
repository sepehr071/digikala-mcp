import pytest

pytestmark = [pytest.mark.anyio, pytest.mark.live]


async def call(client, name, args):
    result = await client.call_tool(name, args)
    assert not result.is_error, result.content[0].text
    return result.structured_content


async def test_dk_plus_plans(client):
    data = await call(client, "dk_plus_plans", {})
    assert data["plans"] and all(p["price"] > 0 for p in data["plans"])


async def test_dk_gold_prices(client):
    data = await call(client, "dk_gold_prices", {})
    # Toman per gram of 18k gold; Rial would be 10x this range
    assert 1_000_000 < data["gold18_per_gram"] < 500_000_000
    assert abs(data["gold18_day_change_pct"]) < 10  # one day, not the ~3-month period


async def test_dk_location(client):
    places = await call(client, "dk_location", {"address": "میدان ونک", "city": "تهران"})
    assert places["places"] and 35 < places["places"][0]["lat"] < 36
    point = await call(client, "dk_location", {"lat": 35.7575, "long": 51.41})
    assert point["city_id"] and point["state_id"] == 9
