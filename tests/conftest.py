import json
from pathlib import Path

import httpx
import pytest
from mcp import Client

from digikala_mcp import catalog, http
from digikala_mcp.server import mcp

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def fresh_http_client():
    """The shared httpx client is bound to one event loop; each test gets a new loop and an empty category cache."""
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
        yield c
