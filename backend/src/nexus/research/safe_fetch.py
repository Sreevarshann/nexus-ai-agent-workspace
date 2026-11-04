"""SSRF-hardened HTTP fetching for untrusted URLs.

Defences:
* only http/https on default-ish ports, no credentials in URLs
* hostname resolved once; every resolved address must be globally routable (blocks loopback, RFC1918,
  link-local/cloud metadata, CGNAT, multicast, reserved, IPv4-mapped IPv6)
* the connection is pinned to the validated IP (with SNI/Host set to the original name), which defeats
  DNS rebinding between check and use
* redirects are followed manually and every hop is re-validated
* bounded response size and total time; robots.txt is honoured
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx

from nexus.config import get_settings

ALLOWED_PORTS = {None, 80, 443, 8080, 8443}
MAX_REDIRECTS = 5


class FetchBlocked(Exception):
    """The URL targets a disallowed destination."""


class FetchFailed(Exception):
    """The destination was allowed but the request failed."""


@dataclass
class FetchResult:
    url: str
    final_url: str
    status: int
    content_type: str
    body: bytes
    truncated: bool
    elapsed_ms: int


def _ip_allowed(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def validate_url(url: str) -> tuple[str, str, int | None]:
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https"):
        raise FetchBlocked(f"Scheme '{parts.scheme}' is not allowed")
    if not parts.hostname:
        raise FetchBlocked("URL has no host")
    if parts.username or parts.password:
        raise FetchBlocked("Credentials in URLs are not allowed")
    try:
        port = parts.port
    except ValueError as e:
        raise FetchBlocked("Invalid port") from e
    if port not in ALLOWED_PORTS:
        raise FetchBlocked(f"Port {port} is not allowed")
    host = parts.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise FetchBlocked("Local hostnames are not allowed")
    return parts.scheme, host, port


async def resolve_public(host: str, port: int | None) -> str:
    """Resolve ``host`` and return one address, refusing if ANY address is non-public."""
    allow_private = get_settings().allow_private_fetch
    try:
        literal = ipaddress.ip_address(host)
        if not allow_private and not _ip_allowed(literal):
            raise FetchBlocked(f"Address {host} is not publicly routable")
        return host
    except ValueError:
        pass
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise FetchFailed(f"DNS resolution failed for {host}") from e
    addrs = {str(info[4][0]) for info in infos}
    if not addrs:
        raise FetchFailed(f"No addresses for {host}")
    if not allow_private:
        for a in addrs:
            if not _ip_allowed(ipaddress.ip_address(a.split("%")[0])):
                raise FetchBlocked(f"{host} resolves to non-public address {a}")
    return sorted(addrs)[0]


_robots_cache: dict[str, tuple[float, RobotFileParser | None]] = {}


async def _robots_allows(client: httpx.AsyncClient, scheme: str, host: str, port: int | None, url: str) -> bool:
    origin = f"{scheme}://{host}" + (f":{port}" if port else "")
    cached = _robots_cache.get(origin)
    if cached is None or time.time() - cached[0] > 3600:
        parser: RobotFileParser | None = None
        try:
            res = await _single(client, f"{origin}/robots.txt", max_bytes=200_000)
            if res.status == 200:
                parser = RobotFileParser()
                parser.parse(res.body.decode("utf-8", errors="replace").splitlines())
        except (FetchFailed, FetchBlocked):
            parser = None  # unreachable robots.txt: no stated restriction
        _robots_cache[origin] = (time.time(), parser)
        cached = _robots_cache[origin]
    parser = cached[1]
    return True if parser is None else parser.can_fetch(get_settings().user_agent, url)


async def _single(client: httpx.AsyncClient, url: str, max_bytes: int) -> FetchResult:
    scheme, host, port = validate_url(url)
    ip = await resolve_public(host, port)
    parts = urlsplit(url)
    ip_host = f"[{ip}]" if ":" in ip else ip
    pinned = urlunsplit((scheme, ip_host + (f":{port}" if port else ""), parts.path or "/", parts.query, ""))
    headers = {"Host": host + (f":{port}" if port else "")}
    started = time.perf_counter()
    try:
        req = client.build_request("GET", pinned, headers=headers, extensions={"sni_hostname": host})
        resp = await client.send(req, stream=True)
    except httpx.TimeoutException as e:
        raise FetchFailed("Request timed out") from e
    except httpx.HTTPError as e:
        raise FetchFailed(f"{type(e).__name__}: {e}") from e
    body = bytearray()
    truncated = False
    final_url = url
    try:
        if 300 <= resp.status_code < 400:
            final_url = urljoin(url, resp.headers.get("location", ""))
        else:
            async for chunk in resp.aiter_bytes():
                body.extend(chunk)
                if len(body) > max_bytes:
                    truncated = True
                    del body[max_bytes:]
                    break
    finally:
        await resp.aclose()
    return FetchResult(
        url=url,
        final_url=final_url,
        status=resp.status_code,
        content_type=resp.headers.get("content-type", ""),
        body=bytes(body),
        truncated=truncated,
        elapsed_ms=int((time.perf_counter() - started) * 1000),
    )


async def safe_fetch(url: str, max_bytes: int | None = None, check_robots: bool = True) -> FetchResult:
    s = get_settings()
    max_bytes = max_bytes or s.fetch_max_bytes
    timeout = httpx.Timeout(s.fetch_timeout_s, connect=5.0)
    headers = {"User-Agent": s.user_agent, "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.5"}
    async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=False) as client:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            scheme, host, port = validate_url(current)
            if check_robots and not await _robots_allows(client, scheme, host, port, current):
                raise FetchBlocked("Disallowed by the site's robots.txt")
            try:
                res = await asyncio.wait_for(_single(client, current, max_bytes), timeout=s.fetch_timeout_s * 2)
            except TimeoutError as e:
                raise FetchFailed("Request timed out") from e
            if 300 <= res.status < 400 and res.final_url != current:
                current = res.final_url  # re-validated at the top of the loop
                continue
            res.url, res.final_url = url, current
            return res
    raise FetchFailed("Too many redirects")
