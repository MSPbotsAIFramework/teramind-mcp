"""Alert tools (AC4, AC5)."""

from collections.abc import Callable
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from .._json import DEFAULT_LIMIT, dump_json_capped, paginate
from ..client import TeramindClient
from ..errors import InvalidArgumentError, TeramindError
from ._common import CURSOR_FIELD, LIMIT_FIELD, NOT_CONFIGURED

_MAX_RULE_IDS = 100


def register(mcp: FastMCP, client_factory: Callable[[], TeramindClient | None]) -> None:
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    async def teramind_list_alerts(
        period_start: Annotated[
            str, Field(description="Required ISO 8601 start of the alert window.")
        ],
        period_end: Annotated[
            str, Field(description="Required ISO 8601 end of the alert window.")
        ],
        limit: Annotated[int, LIMIT_FIELD] = DEFAULT_LIMIT,
        cursor: Annotated[int, CURSOR_FIELD] = 0,
    ) -> str:
        """List alerts raised in a window: triggering rule, agent, computer, and timestamp."""
        if not period_start or not period_end:
            return InvalidArgumentError(
                "period_start and period_end are both required"
            ).to_envelope()
        try:
            client = client_factory()
            if client is None:
                return NOT_CONFIGURED
            raw = await client.get(
                "/tm-api/v1/alerts",
                tool="teramind_list_alerts",
                params={"periodStart": period_start, "periodEnd": period_end},
            )
        except TeramindError as e:
            return e.to_envelope()
        rows = raw if isinstance(raw, list) else []
        page, has_more, next_cursor = paginate(rows, limit, cursor)
        return dump_json_capped({"alerts": page, "has_more": has_more, "next_cursor": next_cursor})

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    async def teramind_describe_alert_rules(
        rule_ids: Annotated[
            list[int],
            Field(
                description=(
                    f"Required list of alert rule ids to describe, max {_MAX_RULE_IDS} per call."
                )
            ),
        ],
    ) -> str:
        """Get the human-readable name/description for one or more alert rule ids."""
        if not rule_ids:
            return InvalidArgumentError("rule_ids must be a non-empty list").to_envelope()
        if len(rule_ids) > _MAX_RULE_IDS:
            return InvalidArgumentError(
                f"rule_ids must have at most {_MAX_RULE_IDS} entries"
            ).to_envelope()
        try:
            client = client_factory()
            if client is None:
                return NOT_CONFIGURED
            raw = await client.post(
                "/tm-api/v1/alerts/descriptions",
                tool="teramind_describe_alert_rules",
                json_body={"ids": rule_ids},
            )
        except TeramindError as e:
            return e.to_envelope()
        if isinstance(raw, list):
            descriptions = raw
        elif isinstance(raw, dict):
            descriptions = raw.get("descriptions", [])
        else:
            descriptions = []
        return dump_json_capped({"descriptions": descriptions})
