"""TeramindClient unit tests: URL building, the SSRF instance-host guard
(TC-TMD-010), retry/backoff on 429/5xx (TC-TMD-011, TC-TMD-012), status
-> error-code mapping, and structured per-call logging (PRD-21246 review
round 1 must-fix) — all via respx, no real network calls.
"""

import httpx
import pytest
import respx

from teramind_mcp.client import TeramindClient, validate_instance_host
from teramind_mcp.errors import (
    InvalidArgumentError,
    NotFoundError,
    RateLimitedError,
    UnauthorizedError,
    UpstreamError,
)


def test_validate_instance_host_accepts_teramind_subdomain():
    assert validate_instance_host("acme.teramind.co") == "acme.teramind.co"


@pytest.mark.parametrize(
    "host",
    ["evil.example.com", "teramind.co.evil.com", "not-teramind", "", "http://acme.teramind.co"],
)
def test_validate_instance_host_rejects_non_teramind_hosts(host):
    with pytest.raises(InvalidArgumentError):
        validate_instance_host(host)


def test_client_rejects_invalid_instance_host_at_construction_time():
    # TC-TMD-010: the guard must run before any outbound request can be
    # built -- constructing the client with a bad host is already enough to
    # raise, with no respx mock registered at all (so any accidental
    # outbound call would fail loudly, not silently succeed).
    with pytest.raises(InvalidArgumentError):
        TeramindClient("evil.example.com", "tok")


@respx.mock
async def test_get_builds_correct_url_and_header():
    route = respx.get("https://acme.teramind.co/tm-api/computer").mock(
        return_value=httpx.Response(200, json=[{"id": 1, "name": "WS-1"}])
    )
    client = TeramindClient("acme.teramind.co", "tok-abc")
    result = await client.get("/tm-api/computer", tool="teramind_list_computers")

    assert route.called
    assert route.calls.last.request.headers["x-access-token"] == "tok-abc"
    assert result == [{"id": 1, "name": "WS-1"}]


@respx.mock
async def test_404_raises_not_found():
    respx.get("https://acme.teramind.co/tm-api/computer/missing").mock(
        return_value=httpx.Response(404, json={"message": "not found"})
    )
    client = TeramindClient("acme.teramind.co", "tok")
    with pytest.raises(NotFoundError):
        await client.get("/tm-api/computer/missing", tool="teramind_get_computer")


@respx.mock
async def test_401_raises_unauthorized():
    respx.get("https://acme.teramind.co/tm-api/computer").mock(
        return_value=httpx.Response(401, json={"message": "bad token"})
    )
    client = TeramindClient("acme.teramind.co", "bad-tok")
    with pytest.raises(UnauthorizedError):
        await client.get("/tm-api/computer", tool="teramind_list_computers")


@respx.mock
async def test_503_raises_upstream_error_retryable(monkeypatch):
    # TC-TMD-011. Collapse the backoff sleep so the test doesn't actually wait.
    import teramind_mcp.client as client_module

    async def _no_sleep(_seconds):
        return None

    monkeypatch.setattr(client_module.asyncio, "sleep", _no_sleep)

    route = respx.get("https://acme.teramind.co/tm-api/computer").mock(
        return_value=httpx.Response(503, json={"message": "down"})
    )
    client = TeramindClient("acme.teramind.co", "tok")
    with pytest.raises(UpstreamError) as exc_info:
        await client.get("/tm-api/computer", tool="teramind_list_computers")

    assert exc_info.value.retryable is True
    # Retried _MAX_RETRIES + 1 times total before giving up.
    assert route.call_count == 4


@respx.mock
async def test_429_retries_then_succeeds(monkeypatch):
    # TC-TMD-012 (retry branch): first call 429 with Retry-After, second succeeds.
    import teramind_mcp.client as client_module

    async def _no_sleep(_seconds):
        return None

    monkeypatch.setattr(client_module.asyncio, "sleep", _no_sleep)

    route = respx.get("https://acme.teramind.co/tm-api/computer")
    route.side_effect = [
        httpx.Response(429, headers={"Retry-After": "0"}, json={"message": "slow down"}),
        httpx.Response(200, json=[{"id": 1}]),
    ]
    client = TeramindClient("acme.teramind.co", "tok")
    result = await client.get("/tm-api/computer", tool="teramind_list_computers")

    assert result == [{"id": 1}]
    assert route.call_count == 2


@respx.mock
async def test_429_on_every_attempt_raises_rate_limited(monkeypatch):
    # TC-TMD-012 (exhausted branch): every attempt returns 429.
    import teramind_mcp.client as client_module

    async def _no_sleep(_seconds):
        return None

    monkeypatch.setattr(client_module.asyncio, "sleep", _no_sleep)

    respx.get("https://acme.teramind.co/tm-api/computer").mock(
        return_value=httpx.Response(429, json={"message": "slow down"})
    )
    client = TeramindClient("acme.teramind.co", "tok")
    with pytest.raises(RateLimitedError) as exc_info:
        await client.get("/tm-api/computer", tool="teramind_list_computers")

    assert exc_info.value.retryable is True


@respx.mock
async def test_successful_call_logs_tool_status_and_ok_code(caplog):
    respx.get("https://acme.teramind.co/tm-api/computer").mock(
        return_value=httpx.Response(200, json=[{"id": 1}])
    )
    client = TeramindClient("acme.teramind.co", "secret-token-value")
    with caplog.at_level("INFO", logger="teramind_mcp.client"):
        await client.get("/tm-api/computer", tool="teramind_list_computers")

    assert any(
        "tool=teramind_list_computers" in r.message
        and "status=200" in r.message
        and "code=ok" in r.message
        for r in caplog.records
    )
    assert "secret-token-value" not in caplog.text
    assert "acme.teramind.co" not in caplog.text


@respx.mock
async def test_error_call_logs_tool_status_and_error_code(caplog):
    respx.get("https://acme.teramind.co/tm-api/computer/missing").mock(
        return_value=httpx.Response(404, json={"message": "not found"})
    )
    client = TeramindClient("acme.teramind.co", "secret-token-value")
    with caplog.at_level("INFO", logger="teramind_mcp.client"):
        with pytest.raises(NotFoundError):
            await client.get("/tm-api/computer/missing", tool="teramind_get_computer")

    assert any(
        "tool=teramind_get_computer" in r.message
        and "status=404" in r.message
        and "code=not_found" in r.message
        for r in caplog.records
    )
    assert "secret-token-value" not in caplog.text
    assert "acme.teramind.co" not in caplog.text
