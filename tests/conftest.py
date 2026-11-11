import json
from pathlib import Path

import httpx
import pytest
from mcp import Client

from digikala_mcp import catalog, http
from digikala_mcp.server import mcp

FIXTURES = Path(__file__).parent / "fixtures"


def assert_images(data, tool=""):
    """Every product card (has in_stock and url) carries an absolute https `image`; returns how many cards."""
    if isinstance(data, list):
        return sum(assert_images(x, tool) for x in data)
    if not isinstance(data, dict):
        return 0
    here = 0
    if "in_stock" in data and "url" in data:
        assert str(data.get("image")).startswith("https://"), (tool, data.get("id"), data.get("image"))
        here = 1
    return here + sum(assert_images(v, tool) for v in data.values())


SEARCH = "/discovery/api/v2/search"


def v2(body):
    """Wrap an old /v1/search/ fixture body in the v2 search envelope (search_v2.json is a real one)."""
    d = body["data"]
    items = [{"type": "product", "data": p} for p in d.get("products") or []]
    listing = {"type": "vertical_product_listing", "data": {**d, "widgets": items}}
    return {"status": 200, "data": {"widgets": [listing]}}


def fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def fresh_http_client(monkeypatch):
    """The shared httpx client is bound to one event loop; each test gets a new loop and an empty category cache."""
    monkeypatch.setattr(http, "RETRY_DELAY", 0)
    monkeypatch.setattr(http, "JITTER", (0, 0))
    http.set_transport(None)
    catalog._tree = None
    yield
    http.set_transport(None)
    catalog._tree = None


@pytest.fixture
def api():
    """Route table for a fake upstream: api["/path"] = JSON body, or a callable(request) -> httpx.Response.

    Keys match the URL path only (host ignored). Unknown paths return 404. Every
    request is appended to api.calls so tests can assert on query params.
    """

    class Routes(dict):
        calls: list[httpx.Request]

    routes = Routes()
    routes.calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        routes.calls.append(request)
        target = routes.get(request.url.path)
        if target is None:
            return httpx.Response(404, json={"error": "no fake route"})
        if callable(target):
            return target(request)
        return httpx.Response(200, json=target)

    http.set_transport(httpx.MockTransport(handler))
    return routes


@pytest.fixture
async def client():
    async with Client(mcp, raise_exceptions=True) as c:
        call_tool = c.call_tool

        async def checked(*args, **kwargs):
            result = await call_tool(*args, **kwargs)
            if not result.is_error:
                result.structured_content = json.loads(result.content[0].text)
                assert_images(result.structured_content, args[0])
            return result

        c.call_tool = checked
        yield c
