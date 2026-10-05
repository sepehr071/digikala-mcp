"""Shared async HTTP client for the Digikala API.

Every tool goes through `fetch`, which caps concurrency, passes the CDN cookie challenge
and turns HTTP and body-level failures into `ToolError` messages the model can act on.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

import httpx
from mcp.server.mcpserver.exceptions import ToolError

API = "https://api.digikala.com"
SITE = "https://www.digikala.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0",
    "Accept": "application/json",
    # price-chart answers 429 to every call without it; the site sends it everywhere anyway.
    "Referer": f"{SITE}/",
}

MAX_CONCURRENCY = 4
# Agents often repeat a call (search, then the same search with one more filter); prices move slowly enough
# that a short cache saves Digikala and the user time. ponytail: unbounded age-ordered dict, trimmed by size.
CACHE_SECONDS = 120
CACHE_SIZE = 300

_transport: httpx.AsyncBaseTransport | None = None
_client: httpx.AsyncClient | None = None
_limit: asyncio.Semaphore | None = None
_cache: dict[tuple[str, tuple[tuple[str, Any], ...]], tuple[float, Any]] = {}


class ApiError(ToolError):
    """A failed upstream call. `status` is the HTTP (or body) status, or None for network errors."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def set_transport(transport: httpx.AsyncBaseTransport | None) -> None:
    """Swap the transport (tests use httpx.MockTransport). Drops the current client."""
    global _transport, _client, _limit
    _transport, _client, _limit = transport, None, None
    _cache.clear()


def _get_client() -> tuple[httpx.AsyncClient, asyncio.Semaphore]:
    global _client, _limit
    if _client is None:
        # The DigiCDN edge first answers 307 + Set-Cookie digicdn_cookie to the same URL; the
        # client's cookie jar plus follow_redirects passes it. System proxies are ignored unless
        # the user opts in with DIGIKALA_MCP_PROXY.
        _client = httpx.AsyncClient(
            transport=_transport,
            headers=HEADERS,
            timeout=20,
            follow_redirects=True,
            trust_env=False,
            proxy=os.environ.get("DIGIKALA_MCP_PROXY") or None,
        )
        _limit = asyncio.Semaphore(MAX_CONCURRENCY)
    assert _limit is not None
    return _client, _limit


async def fetch(path: str, params: dict[str, Any] | None = None) -> Any:
    """GET an api.digikala.com path (e.g. '/v1/search/') and return the parsed JSON body.

    The body `status` is authoritative: HTTP 200 with `{"status": 404}` raises ApiError too.
    Successful bodies are reused for CACHE_SECONDS; callers must not mutate them.
    """
    key = (path, tuple(sorted((params or {}).items())))
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
        return hit[1]
    body = await _get(path, params)
    _cache.pop(key, None)
    _cache[key] = (time.monotonic(), body)
    if len(_cache) > CACHE_SIZE:
        del _cache[next(iter(_cache))]  # oldest entry
    return body


async def _get(path: str, params: dict[str, Any] | None) -> Any:
    client, limit = _get_client()
    host = httpx.URL(API).host
    try:
        async with limit:
            r = await client.get(API + path, params=params)
    except httpx.TimeoutException as e:
        raise ApiError(f"{host} did not answer in time. Try again in a moment.") from e
    except httpx.TooManyRedirects as e:
        raise ApiError(f"{host} kept redirecting (CDN cookie challenge failed). Try again in a moment.") from e
    except httpx.RequestError as e:
        raise ApiError(f"Could not reach {host} ({type(e).__name__}). Check the internet connection.") from e

    try:
        body = r.json()
    except ValueError as e:
        if r.status_code >= 400:
            raise ApiError(_status_message(r.status_code, host, r.text[:200]), r.status_code) from e
        raise ApiError(f"{host} returned a non-JSON response (HTTP {r.status_code}).", r.status_code) from e
    code = r.status_code if r.status_code >= 400 else body.get("status") if isinstance(body, dict) else None
    if isinstance(code, int) and code >= 300:
        raise ApiError(_status_message(code, host, _error_text(body)), code)
    return body


def _status_message(code: int, host: str, detail: str) -> str:
    if code == 401:
        return f"{host} wants a logged-in user for this (status 401). This server only reads public data."
    if code == 403:
        return (
            f"{host} refused the request (HTTP 403). Digikala answers 403 for an unknown category or brand "
            "code: check it with dk_categories, dk_suggest or dk_product's brand_code. If every dk_ tool fails "
            "this way, your IP is blocked: turn off VPN/proxy, or set DIGIKALA_MCP_PROXY to a proxy with an Iranian IP."
        )
    if code == 404:
        return f"Not found on {host} (status 404). Check the product id / category, brand or seller code."
    if code == 429:
        return f"{host} is rate limiting requests (HTTP 429). Wait a minute before retrying."
    if code >= 500:
        return f"{host} had a server error (HTTP {code}). Try again later."
    return f"{host} rejected the request (status {code}): {detail}"


def _error_text(body: Any) -> str:
    if isinstance(body, dict):
        err = body.get("message") or body.get("error_msg") or body.get("error") or body.get("redirect_url") or body
        return str(err)[:300]
    return str(body)[:300]
