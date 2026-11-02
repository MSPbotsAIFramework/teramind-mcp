"""Token-economical JSON serialization and the shared client-side
pagination helper used by every teramind_list_* tool.

Compact serialization (no indent, ensure_ascii=False) and a hard character
cap are SOP §2.5 requirements; the pagination helper exists because none of
Teramind's in-scope list endpoints document native upstream pagination (see
docs/tickets/PRD-21246.md "Pagination note") — every list tool fetches the
full upstream list once and slices it the same way, so that slicing logic
lives here instead of being duplicated across tools/*.py.
"""

import json
from typing import Any, TypeVar

MAX_CHARS = 20_000
DEFAULT_LIMIT = 50
MAX_LIMIT = 200

T = TypeVar("T")


def _compact(data: Any) -> str:
    return json.dumps(data, separators=(",", ":"), ensure_ascii=False)


def dump_json_capped(data: Any, max_chars: int = MAX_CHARS) -> str:
    """Serialize compactly; if the result exceeds max_chars, truncate the
    largest list field (marking has_more) rather than ever return an
    unbounded blob.
    """
    s = _compact(data)
    if len(s) <= max_chars:
        return s

    if isinstance(data, dict):
        list_keys = [k for k, v in data.items() if isinstance(v, list)]
        if list_keys:
            key = max(list_keys, key=lambda k: len(_compact(data[k])))
            items = data[key]
            lo, hi = 0, len(items)
            while lo < hi:
                mid = (lo + hi + 1) // 2
                candidate = dict(data)
                candidate[key] = items[:mid]
                candidate["has_more"] = True
                if len(_compact(candidate)) <= max_chars:
                    lo = mid
                else:
                    hi = mid - 1
            candidate = dict(data)
            candidate[key] = items[:lo]
            candidate["has_more"] = True
            return _compact(candidate)

    # Not list-shaped and still too big — return a short notice instead of
    # a giant unbounded string.
    return _compact(
        {
            "error": {
                "code": "upstream_error",
                "message": (
                    f"Result too large ({len(s)} chars) to return in full; narrow the query."
                ),
                "retryable": False,
            }
        }
    )


def paginate(
    items: list[T], limit: int | None, cursor: int | None
) -> tuple[list[T], bool, int | None]:
    """Apply MCP-layer client-side pagination to an already-fetched upstream
    list response.

    `cursor` is an opaque offset into that list, not an upstream protocol —
    callers just pass back whatever `next_cursor` this returned. `limit` is
    clamped to [1, MAX_LIMIT]; a limit <= 0 is treated as DEFAULT_LIMIT.
    """
    effective_limit = limit if limit and limit > 0 else DEFAULT_LIMIT
    effective_limit = min(effective_limit, MAX_LIMIT)
    start = cursor if cursor and cursor > 0 else 0
    page = items[start : start + effective_limit]
    end = start + len(page)
    has_more = end < len(items)
    next_cursor = end if has_more else None
    return page, has_more, next_cursor
