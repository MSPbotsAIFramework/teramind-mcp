from pydantic import Field

from .._json import DEFAULT_LIMIT, MAX_LIMIT
from ..errors import error_envelope

# Returned only when no credentials reached the request context at all.
# Normal operation never reaches this path — CredentialsMiddleware already
# 401s a request missing either header before any tool runs — so this is a
# defensive fallback, not the primary guard (see server.py).
NOT_CONFIGURED = error_envelope(
    "not_configured",
    "No Teramind credentials in request context. Send the X-Teramind-Instance "
    "and X-Teramind-Access-Token headers.",
    False,
)

# Shared Field() objects for every teramind_list_* tool's limit/cursor
# parameters -- one definition instead of repeating the same description in
# every tools/*.py file.
LIMIT_FIELD = Field(
    description=f"Max rows to return (default {DEFAULT_LIMIT}, hard cap {MAX_LIMIT})."
)
CURSOR_FIELD = Field(
    description="Opaque offset from a prior call's next_cursor; 0 for the first page."
)
