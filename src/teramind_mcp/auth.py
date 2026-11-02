"""Per-request credential extraction for the Teramind MCP service.

Two headers carry the tenant's Teramind credentials on every /mcp request
(see README "Authentication headers"):

- X-Teramind-Instance: the tenant's own Teramind instance host
  (e.g. acme.teramind.co). Teramind's API is per-instance — there is no
  shared/global endpoint.
- X-Teramind-Access-Token: the vendor's own bearer-style access token,
  sent upstream as the x-access-token header (see client.py).

Both are required; this server has no environment-variable fallback for
either (SOP §3.1 — credentials only ever come from the request). Missing
either header is treated as "missing credentials" and rejected with HTTP
401, per SOP §3.2 — that is the one credential failure mode that is an
HTTP-level rejection rather than an in-band tool error.

The instance-host SSRF guard (rejecting anything that is not a
*.teramind.co host) deliberately does NOT live here. AC7 requires a
disallowed host to come back as an in-band `invalid_argument` tool result,
not an HTTP-level rejection — see client.py's `validate_instance_host`,
which runs at the point an outbound URL is actually built, inside the
normal tool try/except that produces the error envelope.
"""

import contextvars

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

INSTANCE_HEADER = "X-Teramind-Instance"
TOKEN_HEADER = "X-Teramind-Access-Token"

# Per-request credential isolation via contextvars (SOP §3.3). CredentialsMiddleware
# sets this before the MCP handler runs and resets it in a finally block.
# Python asyncio copies context per task, so concurrent requests are isolated
# (AC10) — see tests/test_client.py for the isolation test.
_credentials_var: contextvars.ContextVar[tuple[str, str] | None] = contextvars.ContextVar(
    "teramind_credentials", default=None
)


def get_credentials() -> tuple[str, str] | None:
    """Return (instance_host, access_token) for the current request, or
    None outside of any request context."""
    return _credentials_var.get()


class CredentialsMiddleware:
    """ASGI middleware: reads the two required headers off every /mcp
    request and stores them in the per-request contextvar. 401s if either
    is missing; does not validate the instance host (see module docstring).
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if not path.startswith("/mcp"):
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        instance = request.headers.get(INSTANCE_HEADER.lower())
        token = request.headers.get(TOKEN_HEADER.lower())
        if not instance or not token:
            response = JSONResponse(
                {
                    "error": "Missing credentials",
                    "message": (
                        f"This server requires the {INSTANCE_HEADER} and "
                        f"{TOKEN_HEADER} headers."
                    ),
                    "required_headers": [INSTANCE_HEADER, TOKEN_HEADER],
                },
                status_code=401,
            )
            await response(scope, receive, send)
            return

        ctx_token = _credentials_var.set((instance, token))
        try:
            await self.app(scope, receive, send)
        finally:
            _credentials_var.reset(ctx_token)
