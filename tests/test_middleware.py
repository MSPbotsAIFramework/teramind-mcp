"""Credentials middleware tests (TC-TMD-009): missing-header 401 with both
required headers listed, and the per-request contextvar correctly isolates
one request's values from the next.
"""

import asyncio

from starlette.testclient import TestClient

from teramind_mcp.__main__ import _build_http_app
from teramind_mcp.auth import CredentialsMiddleware, get_credentials
from teramind_mcp.server import create_mcp_server
from teramind_mcp.settings import Settings


def _make_app():
    settings = Settings()
    mcp = create_mcp_server(settings)
    return _build_http_app(mcp, settings)


def test_health_is_local_and_does_not_require_credentials():
    app = _make_app()
    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


def test_missing_credentials_returns_401_with_required_headers_listed():
    app = _make_app()
    with TestClient(app) as client:
        resp = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            headers={"Accept": "application/json, text/event-stream"},
        )
        assert resp.status_code == 401
        body = resp.json()
        assert body["required_headers"] == [
            "X-Teramind-Instance",
            "X-Teramind-Access-Token",
        ]


def test_missing_one_of_two_headers_still_returns_401():
    # Confirms both headers are independently required, not just "at least one".
    app = _make_app()
    with TestClient(app) as client:
        resp = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            headers={
                "Accept": "application/json, text/event-stream",
                "X-Teramind-Instance": "acme.teramind.co",
                # X-Teramind-Access-Token intentionally omitted
            },
        )
        assert resp.status_code == 401
        assert "X-Teramind-Access-Token" in resp.json()["required_headers"]


def test_all_headers_present_reaches_request_context_and_resets_after():
    # Directly exercises the middleware's contextvar plumbing without a full
    # MCP protocol round-trip: confirms the header values that arrive on the
    # request are exactly what get_credentials() sees, and that they are
    # reset afterward (no leakage to the next request).
    seen = {}

    async def fake_app(scope, receive, send):
        seen["creds"] = get_credentials()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = CredentialsMiddleware(fake_app)

    async def run():
        scope = {
            "type": "http",
            "path": "/mcp",
            "headers": [
                (b"x-teramind-instance", b"acme.teramind.co"),
                (b"x-teramind-access-token", b"test-token-123"),
            ],
        }

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        sent = []

        async def send(message):
            sent.append(message)

        await middleware(scope, receive, send)

    asyncio.run(run())
    assert seen["creds"] == ("acme.teramind.co", "test-token-123")
    # After the request completes, the contextvar must be reset — a fresh
    # get() outside any request context sees no leftover credential.
    assert get_credentials() is None


def test_non_mcp_path_bypasses_credential_check():
    seen = {"called": False}

    async def fake_app(scope, receive, send):
        seen["called"] = True
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = CredentialsMiddleware(fake_app)

    async def run():
        scope = {"type": "http", "path": "/health", "headers": []}

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            pass

        await middleware(scope, receive, send)

    asyncio.run(run())
    assert seen["called"] is True
