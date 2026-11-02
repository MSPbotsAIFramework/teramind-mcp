"""Thin async httpx client for the Teramind Dashboard API.

Built clean-room from Teramind's published Postman collection
(https://apidoc.dev.teramind.co/, collection id 12825404, publish id
TW74jRAB, fetched 2026-11-02) — see docs/tickets/PRD-21246.md "Data & API
contract" for the per-tool endpoint mapping this wraps.
"""

import asyncio
import re
from typing import Any

import httpx

from .errors import (
    InvalidArgumentError,
    NotFoundError,
    RateLimitedError,
    TeramindError,
    UnauthorizedError,
    UpstreamError,
)

_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_MAX_RETRIES = 3
_MAX_BACKOFF_SECONDS = 20.0

# SSRF guard (see auth.py module docstring): only Teramind-owned hosts may
# ever be used to build an outbound URL. A tenant-configured custom-domain
# allow-list for self-hosted instances is a documented v1 limitation, not
# implemented here — see docs/tickets/PRD-21246.md "Decisions made by DEV01".
_INSTANCE_HOST_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?\.teramind\.co$", re.IGNORECASE)

# One shared connection pool for the process lifetime. It holds no
# credentials of its own — every call passes its own Authorization-equivalent
# header per request — so sharing it across tenants/requests is safe; the
# contextvar in auth.py is what actually keeps tenants apart (SOP §3.3/§3.4).
_http_client: httpx.AsyncClient | None = None


def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=_TIMEOUT)
    return _http_client


def validate_instance_host(host: str) -> str:
    """Return host unchanged if it is a valid *.teramind.co hostname.

    Raises InvalidArgumentError otherwise. Must run before any outbound URL
    is built — TC-TMD-010 requires zero outbound requests for a disallowed
    host, which this satisfies by running inside TeramindClient.__init__,
    before any _request() call can happen.
    """
    candidate = host.strip()
    if not _INSTANCE_HOST_RE.match(candidate):
        raise InvalidArgumentError(
            f"X-Teramind-Instance must be a *.teramind.co host, got {candidate!r}"
        )
    return candidate


class TeramindClient:
    """One instance per request — holds only what the caller passed in, and
    nothing outlives the request that created it (SOP §3.3/§3.4).
    """

    def __init__(self, instance_host: str, access_token: str):
        self._host = validate_instance_host(instance_host)
        self._token = access_token

    def _base_url(self) -> str:
        return f"https://{self._host}"

    def _headers(self) -> dict[str, str]:
        return {"x-access-token": self._token, "Accept": "application/json"}

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return await self._request("GET", path, params=_clean(params))

    async def post(self, path: str, json_body: Any = None) -> Any:
        return await self._request("POST", path, json_body=json_body)

    async def _request(
        self, method: str, path: str, params: dict | None = None, json_body: Any = None
    ) -> Any:
        client = _get_http_client()
        url = f"{self._base_url()}{path}"
        headers = self._headers()

        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                resp = await client.request(
                    method, url, headers=headers, params=params, json=json_body
                )
            except httpx.RequestError as e:
                last_exc = e
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(min(2**attempt, _MAX_BACKOFF_SECONDS))
                    continue
                raise UpstreamError(f"{e or type(e).__name__} (url={url})") from e

            if resp.status_code in _RETRYABLE_STATUS and attempt < _MAX_RETRIES:
                await asyncio.sleep(self._retry_delay(resp, attempt))
                continue

            return self._handle(resp)

        # Unreachable in practice (the loop above always returns or raises),
        # but keeps type checkers happy and guards against future edits.
        if last_exc:
            raise UpstreamError(str(last_exc)) from last_exc
        raise UpstreamError("request failed with no response")

    def _retry_delay(self, resp: httpx.Response, attempt: int) -> float:
        retry_after = resp.headers.get("Retry-After")
        if retry_after:
            try:
                return min(float(retry_after), _MAX_BACKOFF_SECONDS)
            except ValueError:
                pass
        return min(2**attempt, _MAX_BACKOFF_SECONDS)

    def _handle(self, resp: httpx.Response) -> Any:
        if resp.status_code == 204:
            return {}
        try:
            body = resp.json()
        except ValueError:
            body = {"raw_response": resp.text}

        if resp.status_code in (401, 403):
            raise UnauthorizedError(_extract_message(body, resp.status_code))
        if resp.status_code == 404:
            raise NotFoundError(_extract_message(body, resp.status_code))
        if resp.status_code == 429:
            raise RateLimitedError(_extract_message(body, resp.status_code))
        if resp.status_code in (400, 422):
            raise InvalidArgumentError(_extract_message(body, resp.status_code))
        if resp.status_code >= 400:
            raise UpstreamError(_extract_message(body, resp.status_code))
        return body


def _clean(params: dict | None) -> dict:
    if not params:
        return {}
    return {k: v for k, v in params.items() if v is not None}


def _extract_message(body: Any, status_code: int) -> str:
    if isinstance(body, dict):
        for key in ("message", "error", "detail"):
            value = body.get(key)
            if isinstance(value, str):
                return value
    return f"Teramind API returned {status_code}"


__all__ = [
    "TeramindClient",
    "TeramindError",
    "validate_instance_host",
]
