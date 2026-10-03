import httpx
import pytest
from conftest import fixture

pytestmark = pytest.mark.anyio


async def test_all_tools_are_read_only(client):
    tools = (await client.list_tools()).tools
    assert len(tools) == 20
    for t in tools:
        assert t.name.startswith("dk_"), t.name
        assert t.annotations.read_only_hint is True, t.name
        assert t.description and t.title, t.name


async def test_cdn_cookie_challenge_is_followed(client, api):
    """api.digikala.com first answers 307 + digicdn_cookie to the same URL; the cookie jar passes it."""

    def challenge(request):
        if "digicdn_cookie=abc" not in request.headers.get("cookie", ""):
            return httpx.Response(
                307, headers={"Location": str(request.url), "Set-Cookie": "digicdn_cookie=abc; Path=/"}
            )
        return httpx.Response(200, json=fixture("autocomplete.json"))

    api["/v1/autocomplete/"] = challenge
    result = await client.call_tool("dk_suggest", {"query": "samsung"})
    assert not result.is_error
    assert len(api.calls) == 2
    assert api.calls[1].headers["Referer"] == "https://www.digikala.com/"


async def test_body_status_is_authoritative(client, api):
    api["/v1/autocomplete/"] = {"status": 401}
    result = await client.call_tool("dk_suggest", {"query": "samsung"})
    assert result.is_error and "status 401" in result.content[0].text


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (httpx.Response(404, json={"status": 404}), "Not found"),
        (httpx.Response(403, text="<html>Access Denied ... Error code : 403</html>"), "unknown category or brand"),
        (httpx.Response(429, json={"status": 429}), "rate limiting"),
        (httpx.Response(503, text="<html>down</html>"), "server error"),
        (httpx.Response(400, json={"status": 400, "message": "not main category"}), "not a main category"),
        (httpx.Response(200, text="<html>maintenance</html>"), "non-JSON"),
    ],
)
async def test_upstream_errors_are_actionable(client, api, response, message):
    api["/v1/best-selling/"] = lambda r: response
    result = await client.call_tool("dk_best_sellers", {"category_id": 11})
    assert result.is_error and message in result.content[0].text


async def test_network_error(client, api):
    def boom(request):
        raise httpx.ConnectError("refused", request=request)

    api["/v1/digiplus/plans/"] = boom
    result = await client.call_tool("dk_plus_plans", {})
    assert result.is_error and "Could not reach api.digikala.com" in result.content[0].text
