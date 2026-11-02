"""The structured error envelope and Teramind-domain exception hierarchy.

Every tool call either succeeds (returns its result) or returns this fixed
envelope as its string result — tools never raise to the MCP protocol layer
(SOP §4.1). `code` is drawn from the SOP's fixed, limited vocabulary so an
agent can branch on it; `retryable` tells the agent whether retrying makes
sense.
"""

import json
from typing import Any

_VALID_CODES = {
    "not_configured",
    "unauthorized",
    "not_found",
    "invalid_argument",
    "rate_limited",
    "upstream_error",
}


def error_envelope(code: str, message: str, retryable: bool) -> str:
    if code not in _VALID_CODES:
        raise ValueError(f"unknown error envelope code: {code!r}")
    payload: dict[str, Any] = {"error": {"code": code, "message": message, "retryable": retryable}}
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


class TeramindError(Exception):
    """Base class for domain errors that map 1:1 onto the error envelope.

    Subclasses fix `code` and `retryable`; callers only ever need to supply
    `message`. Every TeramindError instance can turn itself into the wire
    envelope via `to_envelope()`.
    """

    code = "upstream_error"
    retryable = True

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)

    def to_envelope(self) -> str:
        return error_envelope(self.code, self.message, self.retryable)


class UnauthorizedError(TeramindError):
    code = "unauthorized"
    retryable = False


class NotFoundError(TeramindError):
    code = "not_found"
    retryable = False


class InvalidArgumentError(TeramindError):
    code = "invalid_argument"
    retryable = False


class RateLimitedError(TeramindError):
    code = "rate_limited"
    retryable = True


class UpstreamError(TeramindError):
    code = "upstream_error"
    retryable = True
