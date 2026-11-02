"""Behavior-policy configuration tools (AC6): policies, the entity groups
they apply to, and the anomaly-rule catalog they're built from."""

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
    async def teramind_list_behavior_policies(
        limit: Annotated[int, LIMIT_FIELD] = DEFAULT_LIMIT,
        cursor: Annotated[int, CURSOR_FIELD] = 0,
    ) -> str:
        """List the tenant's behavior policies (each assigns anomaly rules to an entity group)."""
        try:
            client = client_factory()
            if client is None:
                return NOT_CONFIGURED
            raw = await client.get("/tm-api/behavior-policy")
        except TeramindError as e:
            return e.to_envelope()
        rows = raw if isinstance(raw, list) else []
        page, has_more, next_cursor = paginate(rows, limit, cursor)
        return dump_json_capped(
            {"policies": page, "has_more": has_more, "next_cursor": next_cursor}
        )

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    async def teramind_get_behavior_policy(
        policy_id: Annotated[
            str, Field(description="Required policy id from teramind_list_behavior_policies.")
        ],
    ) -> str:
        """Get a single behavior policy's full record, including its rule definition."""
        try:
            client = client_factory()
            if client is None:
                return NOT_CONFIGURED
            raw = await client.get(f"/tm-api/behavior-policy/{policy_id}")
        except TeramindError as e:
            return e.to_envelope()
        return dump_json_capped(raw)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    async def teramind_list_behavior_groups(
        limit: Annotated[int, LIMIT_FIELD] = DEFAULT_LIMIT,
        cursor: Annotated[int, CURSOR_FIELD] = 0,
    ) -> str:
        """List the entity groups behavior policies are organized under."""
        try:
            client = client_factory()
            if client is None:
                return NOT_CONFIGURED
            raw = await client.get("/tm-api/behavior-group")
        except TeramindError as e:
            return e.to_envelope()
        rows = raw if isinstance(raw, list) else []
        page, has_more, next_cursor = paginate(rows, limit, cursor)
        return dump_json_capped(
            {"groups": page, "has_more": has_more, "next_cursor": next_cursor}
        )

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    async def teramind_list_anomaly_rules(
        limit: Annotated[int, LIMIT_FIELD] = DEFAULT_LIMIT,
        cursor: Annotated[int, CURSOR_FIELD] = 0,
    ) -> str:
        """List the catalog of anomaly rules behavior policies are built from."""
        try:
            client = client_factory()
            if client is None:
                return NOT_CONFIGURED
            raw = await client.get("/tm-api/behavior-rule")
        except TeramindError as e:
            return e.to_envelope()
        rows = raw if isinstance(raw, list) else []
        page, has_more, next_cursor = paginate(rows, limit, cursor)
        return dump_json_capped(
            {"rules": page, "has_more": has_more, "next_cursor": next_cursor}
        )

