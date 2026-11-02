"""Monitored-user ("agent" in Teramind's own terminology) inventory tools (AC3)."""

from collections.abc import Callable
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from .._json import DEFAULT_LIMIT, dump_json_capped, paginate
from ..client import TeramindClient
from ..errors import TeramindError
from ._common import CURSOR_FIELD, LIMIT_FIELD, NOT_CONFIGURED


def register(mcp: FastMCP, client_factory: Callable[[], TeramindClient | None]) -> None:
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    async def teramind_list_agents(
        limit: Annotated[int, LIMIT_FIELD] = DEFAULT_LIMIT,
        cursor: Annotated[int, CURSOR_FIELD] = 0,
        fields: Annotated[
            str | None,
            Field(
                description=(
                    "Optional comma-separated extra fields to request from Teramind, "
                    'e.g. "department_id,status,position".'
                )
            ),
        ] = None,
    ) -> str:
        """List the tenant's monitored-user ("agent") inventory (id, name, email, online status)."""
        try:
            client = client_factory()
            if client is None:
                return NOT_CONFIGURED
            raw = await client.get("/tm-api/v1/agents", params={"fields": fields})
        except TeramindError as e:
            return e.to_envelope()
        rows = raw if isinstance(raw, list) else []
        page, has_more, next_cursor = paginate(rows, limit, cursor)
        return dump_json_capped({"agents": page, "has_more": has_more, "next_cursor": next_cursor})

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    async def teramind_get_agent(
        agent_id: Annotated[str, Field(description="Required agent id from teramind_list_agents.")],
        fields: Annotated[
            str | None,
            Field(description="Optional comma-separated extra fields to request from Teramind."),
        ] = None,
    ) -> str:
        """Get a single monitored user's ("agent") full detail record."""
        try:
            client = client_factory()
            if client is None:
                return NOT_CONFIGURED
            raw = await client.get(f"/tm-api/v1/agents/{agent_id}", params={"fields": fields})
        except TeramindError as e:
            return e.to_envelope()
        return dump_json_capped(raw)
