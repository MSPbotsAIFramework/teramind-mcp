from collections.abc import Callable

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from .auth import get_credentials
from .client import TeramindClient
from .settings import Settings

INSTRUCTIONS = (
    "Teramind is an insider-threat / employee-monitoring product. This connector "
    "is read-only: it lets an agent pull a tenant's monitored-computer and "
    'monitored-user ("agent") inventory, security alerts Teramind\'s rule engine '
    "raised in a time window (plus human-readable names for the rule ids behind "
    "them), and the behavior-policy configuration (policies, the entity groups "
    "they apply to, and the anomaly-rule catalog they're built from) that defines "
    "what counts as risky behavior for that tenant. Typical flow: "
    "teramind_list_alerts for a time window, then teramind_describe_alert_rules "
    "on the returned rule_ids to explain what each alert means, then "
    "teramind_list_behavior_policies / teramind_get_behavior_policy to see the "
    'policy a rule belongs to. teramind_list_computers / teramind_get_computer '
    "and teramind_list_agents / teramind_get_agent answer who/what is being "
    "monitored. No configuration, write, or delete tools exist in this service — "
    "it cannot change a tenant's Teramind setup."
)


def get_client_from_context() -> TeramindClient | None:
    """Resolve the active TeramindClient for the current request context.

    Returns None only if no credentials reached the contextvar at all — in
    normal operation CredentialsMiddleware already rejects that case with an
    HTTP 401 before any tool runs, so this is a defensive fallback, not the
    primary guard. An invalid (non-*.teramind.co) instance host is a
    different case: TeramindClient's constructor raises InvalidArgumentError,
    which the caller (each tool, inside its try/except TeramindError) turns
    into the in-band error envelope — see client.py.
    """
    creds = get_credentials()
    if not creds:
        return None
    instance, token = creds
    return TeramindClient(instance, token)


def create_mcp_server(settings: Settings) -> FastMCP:
    """Build the FastMCP server instance and register all Teramind tools."""
    # DNS-rebinding protection is a browser-oriented safeguard that rejects
    # non-localhost Host headers with 421. Disable it — this service runs
    # behind an internal gateway, never directly on the public internet.
    mcp = FastMCP(
        name="teramind-mcp",
        instructions=INSTRUCTIONS,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        stateless_http=True,
        json_response=True,
    )

    client_factory: Callable[[], TeramindClient | None] = get_client_from_context

    from .tools import agents, alerts, behavior, computers

    computers.register(mcp, client_factory)
    agents.register(mcp, client_factory)
    alerts.register(mcp, client_factory)
    behavior.register(mcp, client_factory)

    return mcp
