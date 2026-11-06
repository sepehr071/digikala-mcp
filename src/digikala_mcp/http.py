"""Shared async HTTP client for the Digikala API.

Every tool goes through `fetch`, which caps concurrency, passes the CDN cookie challenge
and turns HTTP and body-level failures into `ToolError` messages the model can act on.
"""

from __future__ import annotations

import asyncio
import os
import random
import re
import time
from typing import Any

import httpx
from httpx_curl_cffi import AsyncCurlTransport
from mcp.server.mcpserver.exceptions import ToolError

API = "https://api.digikala.com"
SITE = "https://www.digikala.com"

HEADERS = {
    # User-Agent, sec-ch-ua and TLS come from the impersonated Chrome profile (see _get_client).
    "Accept": "application/json",
    "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.8",
    "Origin": SITE,
    "x-web-client": "desktop",
    "x-web-client-id": "web",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "priority": "u=1, i",
    # price-chart answers 429 to every call without it; the site sends it everywhere anyway.
    "Referer": f"{SITE}/",
}

MAX_CONCURRENCY = 2
JITTER = (0.15, 0.6)  # seconds before each uncached call, unless it is a lone one (see QUIET_SECONDS)
QUIET_SECONDS = 2
MAX_RETRIES = 2
MAX_RETRY_WAIT = 10  # cap for Retry-After and backoff, seconds
# Agents often repeat a call (search, then the same search with one more filter); prices move slowly enough
# that a short cache saves Digikala and the user time. ponytail: unbounded age-ordered dict, trimmed by size.
CACHE_SECONDS = 120
CACHE_SIZE = 300
RETRY_DELAY = 0.5

_transport: httpx.AsyncBaseTransport | None = None
_client: httpx.AsyncClient | None = None
_limit: asyncio.Semaphore | None = None
_proxy_index = 0
_retired: set[asyncio.Task] = set()
_browser_lock: asyncio.Lock | None = None
_cleared: tuple[httpx.AsyncClient, float] | None = None
_in_flight = 0
_last_active = float("-inf")  # monotonic time the last upstream request started or ended
_cache: dict[tuple[str, tuple[tuple[str, Any], ...]], tuple[float, Any]] = {}


class _XhrTransport(AsyncCurlTransport):
    """The Chrome profile sends navigation-only headers; a None value makes curl drop them (API calls are XHR)."""

    def _create_request_params(self, req: httpx.Request) -> dict[str, Any]:
        p = super()._create_request_params(req)
        p["headers"] = [*p["headers"], (b"upgrade-insecure-requests", None), (b"sec-fetch-user", None)]
        return p


class ApiError(ToolError):
    """A failed upstream call. `status` is the HTTP (or body) status, or None for network errors."""

    def __init__(self, message: str, status: int | None = None, retry_after: float | None = None):
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after


def set_transport(transport: httpx.AsyncBaseTransport | None) -> None:
    """Swap the transport (tests use httpx.MockTransport). Drops the current client."""
    global _transport, _client, _limit, _proxy_index, _browser_lock, _cleared
    _transport, _client, _limit, _proxy_index, _browser_lock, _cleared = transport, None, None, 0, None, None
    _cache.clear()


async def _same_host(r: httpx.Response) -> None:
    """Refuse a redirect off api.digikala.com (the CDN cookie challenge redirects to the same URL)."""
    if r.has_redirect_location and r.url.join(r.headers["location"]).host != httpx.URL(API).host:
        raise ApiError(f"{httpx.URL(API).host} redirected to another host; refused.")


def _proxies() -> list[str]:
    """DIGIKALA_MCP_PROXY: one proxy URL, or a comma-separated list used one at a time."""
    return [p.strip() for p in os.environ.get("DIGIKALA_MCP_PROXY", "").split(",") if p.strip()]


# Plain CDN error pages are not challenges: an unknown brand/category answers a bare 403 HTML page.
_CHALLENGE = re.compile(r"just a moment|captcha|challenge|arvan|attention required|enable javascript", re.I)


def _is_challenge(r: httpx.Response) -> bool:
    """A bot-check page: 403/429/503 with an HTML body that carries a known challenge marker."""
    return (
        r.status_code in (403, 429, 503)
        and "html" in r.headers.get("content-type", "") + r.text[:20].lower()
        and bool(_CHALLENGE.search(r.text[:5000]))
    )


def _next_proxy(client: httpx.AsyncClient) -> None:
    """Sticky pool: move to the next proxy after a block or connect error; the next call rebuilds the client.

    Only the client that failed may rotate: a slower request that failed on an old client must not skip a good proxy.
    The old client is closed late because other requests may still be using it.
    """
    global _client, _limit, _proxy_index
    if len(_proxies()) < 2 or client is not _client:
        return
    _client, _limit, _proxy_index = None, None, _proxy_index + 1
    t = asyncio.create_task(_close_later(client))
    _retired.add(t)
    t.add_done_callback(_retired.discard)


async def _close_later(client: httpx.AsyncClient) -> None:
    await asyncio.sleep(30)  # longer than the 20 s request timeout
    await client.aclose()


def _get_client() -> tuple[httpx.AsyncClient, asyncio.Semaphore]:
    global _client, _limit
    if _client is None:
        # The DigiCDN edge first answers 307 + Set-Cookie digicdn_cookie to the same URL; the
        # client's cookie jar plus follow_redirects passes it. System proxies are ignored unless
        # the user opts in with DIGIKALA_MCP_PROXY. curl_cffi presents Chrome's TLS/HTTP2 fingerprint and
        # default headers; cookies and redirects stay with httpx. The proxy goes to the transport (a
        # client-level proxy would be ignored once a transport is given).
        proxies = _proxies()
        _client = httpx.AsyncClient(
            transport=_transport
            or _XhrTransport(
                impersonate="chrome",
                default_headers=True,
                proxy=proxies[_proxy_index % len(proxies)] if proxies else None,
                max_connections=2 * MAX_CONCURRENCY,
            ),
            headers=HEADERS,
            timeout=20,
            limits=httpx.Limits(max_connections=2 * MAX_CONCURRENCY),
            follow_redirects=True,
            event_hooks={"response": [_same_host]},
            trust_env=False,
        )
        _limit = asyncio.Semaphore(MAX_CONCURRENCY)
    assert _limit is not None
    return _client, _limit


async def fetch(path: str, params: dict[str, Any] | None = None, cache: bool = True) -> Any:
    """GET an api.digikala.com path (e.g. '/v1/search/') and return the parsed JSON body.

    The body `status` is authoritative: HTTP 200 with `{"status": 404}` raises ApiError too.
    Successful bodies are reused for CACHE_SECONDS (unless cache=False); callers must not mutate them.
    A timeout, network error, 5xx or 429 is retried up to MAX_RETRIES times with jittered exponential backoff,
    or after Retry-After when sent (every call is an idempotent GET). Other 4xx (403 too) are never retried.
    """
    key = (path, tuple(sorted((params or {}).items())))
    hit = _cache.get(key) if cache else None
    if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
        return hit[1]
    for attempt in range(MAX_RETRIES + 1):
        try:
            body = await _get(path, params)
            break
        except ApiError as e:
            if attempt == MAX_RETRIES or (e.status is not None and e.status < 500 and e.status != 429):
                raise
            wait = e.retry_after if e.retry_after is not None else RETRY_DELAY * 2**attempt * random.uniform(1, 1.5)
            await asyncio.sleep(min(wait, MAX_RETRY_WAIT))
    if not cache:
        return body
    _cache.pop(key, None)
    _cache[key] = (time.monotonic(), body)
    if len(_cache) > CACHE_SIZE:
        del _cache[next(iter(_cache))]  # oldest entry
    return body


async def _send(client: httpx.AsyncClient, limit: asyncio.Semaphore, path: str, params: dict[str, Any] | None):
    host = httpx.URL(API).host
    try:
        async with limit:
            global _in_flight, _last_active
            # a lone call (nothing sent for QUIET_SECONDS) goes out at once; bursts keep the jitter
            if _in_flight or time.monotonic() - _last_active < QUIET_SECONDS:
                await asyncio.sleep(random.uniform(*JITTER))
            _in_flight += 1
            try:
                return await client.get(API + path, params=params)
            finally:
                _in_flight -= 1
                _last_active = time.monotonic()
    except httpx.TimeoutException as e:
        raise ApiError(f"{host} did not answer in time. Try again in a moment.") from e
    except httpx.TooManyRedirects as e:
        _next_proxy(client)
        raise ApiError(f"{host} kept redirecting (CDN cookie challenge failed). Try again in a moment.") from e
    except httpx.RequestError as e:
        if isinstance(e, httpx.ConnectError | httpx.ProxyError):
            _next_proxy(client)
        raise ApiError(f"Could not reach {host} ({type(e).__name__}). Check the internet connection.") from e


async def _browser_cookies(proxy: str | None) -> list[dict[str, Any]]:
    """Open the home page in headless patchright, wait for the challenge to clear, return the cookies."""
    try:
        from patchright.async_api import async_playwright
    except ImportError as e:
        raise ApiError(
            "Digikala served a bot-check page. Install the browser extra (`pip install digikala-mcp[browser]`, or "
            "`uvx --with patchright==1.63.0 digikala-mcp`) and run `patchright install chromium`.",
            403,
        ) from e
    u = httpx.URL(proxy) if proxy else None
    opts = u and {"server": f"{u.scheme}://{u.host}:{u.port}", "username": u.username, "password": u.password}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, proxy=opts)
        try:
            page = await browser.new_page()
            await page.goto(SITE, wait_until="domcontentloaded", timeout=30_000)
            await page.wait_for_function(
                "!/just a moment|access denied|attention required|arvancloud/i.test(document.title)", timeout=30_000
            )
            return await browser.contexts[0].cookies()
        finally:
            await browser.close()


async def _clear_challenge(client: httpx.AsyncClient) -> None:
    """Rung 2: let a real browser pass the bot check once and share its cookies with the httpx jar."""
    global _browser_lock, _cleared
    _browser_lock = _browser_lock or asyncio.Lock()
    async with _browser_lock:  # one browser at a time; callers that waited reuse the cookies just fetched
        if _cleared and _cleared[0] is client and time.monotonic() - _cleared[1] < 30:
            return
        proxies = _proxies()
        try:
            cookies = await _browser_cookies(proxies[_proxy_index % len(proxies)] if proxies else None)
        except ApiError:
            raise
        except Exception as e:
            raise ApiError(f"Digikala bot check was not cleared by the browser ({type(e).__name__}).", 403) from e
        for c in cookies:
            client.cookies.set(c["name"], c["value"], domain=c["domain"], path=c["path"])
        _cleared = (client, time.monotonic())


async def _get(path: str, params: dict[str, Any] | None) -> Any:
    client, limit = _get_client()
    host = httpx.URL(API).host
    r = await _send(client, limit, path, params)
    if _is_challenge(r):
        _next_proxy(client)
        client, limit = _get_client()
        await _clear_challenge(client)
        r = await _send(client, limit, path, params)  # one retry; a second block is final
        if _is_challenge(r):
            _next_proxy(client)
    try:
        body = r.json()
    except ValueError as e:
        if r.status_code >= 400:
            raise ApiError(_status_message(r.status_code, host, r.text[:200]), r.status_code, _retry_after(r)) from e
        raise ApiError(f"{host} returned a non-JSON response (HTTP {r.status_code}).", r.status_code) from e
    code = r.status_code if r.status_code >= 400 else body.get("status") if isinstance(body, dict) else None
    if isinstance(code, int) and code >= 300:
        raise ApiError(_status_message(code, host, _error_text(body)), code, _retry_after(r))
    return body


def _retry_after(r: httpx.Response) -> float | None:
    """Seconds from a numeric Retry-After on a 429/503, else None (HTTP-date form is ignored)."""
    v = r.headers.get("retry-after", "")
    return float(v) if r.status_code in (429, 503) and v.replace(".", "", 1).isdigit() else None


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
