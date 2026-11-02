"""Monitored-computer inventory tools (AC1, AC2)."""

from collections.abc import Callable
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from .._json import DEFAULT_LIMIT, dump_json_capped, paginate
from ..client import TeramindClient
from ..errors import TeramindError
from ._common import CURSOR_FIELD, LIMIT_FIELD, NOT_CONFIGURED

_LIST_FIELDS = ("id", "uid", "name", "online", "department_id")


def register(mcp: FastMCP, client_factory: Callable[[], TeramindClient | None]) -> None:
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    async def teramind_list_computers(
        limit: Annotated[int, LIMIT_FIELD] = DEFAULT_LIMIT,
        cursor: Annotated[int, CURSOR_FIELD] = 0,
    ) -> str:
        """List the tenant's monitored-computer inventory (id, name, online status, department)."""
        try:
            client = client_factory()
            if client is None:
                return NOT_CONFIGURED
            raw = await client.get("/tm-api/computer", tool="teramind_list_computers")
        except TeramindError as e:
            return e.to_envelope()
        rows = [_project(c) for c in raw] if isinstance(raw, list) else []
        page, has_more, next_cursor = paginate(rows, limit, cursor)
        return dump_json_capped(
            {"computers": page, "has_more": has_more, "next_cursor": next_cursor}
        )

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    async def teramind_get_computer(
        computer_id: Annotated[
            str, Field(description="Required computer id from teramind_list_computers.")
        ],
    ) -> str:
        """Get a single monitored computer's full detail record."""
        try:
            client = client_factory()
            if client is None:
                return NOT_CONFIGURED
            raw = await client.get(f"/tm-api/computer/{computer_id}", tool="teramind_get_computer")
        except TeramindError as e:
            return e.to_envelope()
        return dump_json_capped(raw)


def _project(record: dict) -> dict:
    return {k: record.get(k) for k in _LIST_FIELDS if k in record}
