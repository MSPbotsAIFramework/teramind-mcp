"""Tool-level tests: tools/list snapshot (10 tools, readOnlyHint), and one
tools/call test per AC/TC pairing the design doc lists, against a
respx-mocked Teramind API — no real network calls, no real vendor account.
"""

import asyncio

import httpx
import pytest
import respx

from teramind_mcp.auth import _credentials_var
from teramind_mcp.server import create_mcp_server
from teramind_mcp.settings import Settings

BASE = "https://acme.teramind.co"

EXPECTED_TOOL_NAMES = {
    "teramind_list_computers",
    "teramind_get_computer",
    "teramind_list_agents",
    "teramind_get_agent",
    "teramind_list_alerts",
    "teramind_describe_alert_rules",
    "teramind_list_behavior_policies",
    "teramind_get_behavior_policy",
    "teramind_list_behavior_groups",
    "teramind_list_anomaly_rules",
}


@pytest.fixture
def mcp():
    return create_mcp_server(Settings())


async def _call_with_creds(mcp, instance, token, tool_name, arguments):
    ctx_token = _credentials_var.set((instance, token))
    try:
        return await mcp.call_tool(tool_name, arguments)
    finally:
        _credentials_var.reset(ctx_token)


def _text(result) -> str:
    content, _ = result
    return content[0].text


# -- tools/list snapshot -----------------------------------------------------


async def test_tools_list_snapshot(mcp):
    tools = await mcp.list_tools()

    names = {t.name for t in tools}
    assert names == EXPECTED_TOOL_NAMES
    assert len(tools) == 10
    for tool in tools:
        assert tool.description, f"{tool.name} is missing a description"
        assert len(tool.description) <= 500, f"{tool.name} description exceeds 500 chars"

    read_only_tools = {
        "teramind_list_computers",
        "teramind_get_computer",
        "teramind_list_agents",
        "teramind_get_agent",
        "teramind_list_alerts",
        "teramind_describe_alert_rules",
        "teramind_list_behavior_policies",
        "teramind_get_behavior_policy",
        "teramind_list_behavior_groups",
        "teramind_list_anomaly_rules",
    }
    for tool in tools:
        if tool.name in read_only_tools:
            assert tool.annotations is not None
            assert tool.annotations.readOnlyHint is True

    get_computer = next(t for t in tools if t.name == "teramind_get_computer")
    assert set(get_computer.inputSchema.get("required", [])) == {"computer_id"}

    list_alerts = next(t for t in tools if t.name == "teramind_list_alerts")
    assert set(list_alerts.inputSchema.get("required", [])) == {"period_start", "period_end"}


# -- computers (TC-TMD-001, TC-TMD-002, TC-TMD-003) --------------------------


@respx.mock
async def test_list_computers_returns_inventory(mcp):
    """TC-TMD-001 / AC1."""
    respx.get(f"{BASE}/tm-api/computer").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"id": 1, "uid": "u1", "name": "WS-1", "online": True, "department_id": "d1"},
                {"id": 2, "uid": "u2", "name": "WS-2", "online": False},
            ],
        )
    )

    result = await _call_with_creds(
        mcp, "acme.teramind.co", "tok", "teramind_list_computers", {}
    )
    text = _text(result)
    assert '"computers"' in text
    assert '"WS-1"' in text
    assert '"WS-2"' in text
    assert '"has_more":false' in text


@respx.mock
async def test_list_computers_truncates_with_has_more(mcp):
    """TC-TMD-002 / AC9."""
    rows = [{"id": i, "name": f"WS-{i}", "online": True} for i in range(5)]
    respx.get(f"{BASE}/tm-api/computer").mock(return_value=httpx.Response(200, json=rows))

    result = await _call_with_creds(
        mcp, "acme.teramind.co", "tok", "teramind_list_computers", {"limit": 2}
    )
    text = _text(result)
    assert '"has_more":true' in text
    assert '"next_cursor":2' in text


@respx.mock
async def test_get_computer_returns_detail(mcp):
    """TC-TMD-003 / AC2 (found branch)."""
    respx.get(f"{BASE}/tm-api/computer/42").mock(
        return_value=httpx.Response(
            200, json={"id": 42, "uid": "u42", "account_id": "acc1", "name": "WS-42"}
        )
    )

    result = await _call_with_creds(
        mcp, "acme.teramind.co", "tok", "teramind_get_computer", {"computer_id": "42"}
    )
    text = _text(result)
    assert '"id":42' in text
    assert '"account_id":"acc1"' in text


@respx.mock
async def test_get_computer_not_found(mcp):
    """TC-TMD-003 / AC2 (not-found branch)."""
    respx.get(f"{BASE}/tm-api/computer/999").mock(
        return_value=httpx.Response(404, json={"message": "no such computer"})
    )

    result = await _call_with_creds(
        mcp, "acme.teramind.co", "tok", "teramind_get_computer", {"computer_id": "999"}
    )
    text = _text(result)
    assert '"code":"not_found"' in text


# -- agents (TC-TMD-004) ------------------------------------------------------


@respx.mock
async def test_list_agents_returns_inventory(mcp):
    """TC-TMD-004 / AC3 (list)."""
    respx.get(f"{BASE}/tm-api/v1/agents").mock(
        return_value=httpx.Response(
            200,
            json=[{"agent_id": "a1", "name": "Jane Doe", "email_address": "jane@acme.com"}],
        )
    )

    result = await _call_with_creds(mcp, "acme.teramind.co", "tok", "teramind_list_agents", {})
    text = _text(result)
    assert '"agents"' in text
    assert '"jane@acme.com"' in text


@respx.mock
async def test_get_agent_returns_detail(mcp):
    """TC-TMD-004 / AC3 (get)."""
    respx.get(f"{BASE}/tm-api/v1/agents/a1").mock(
        return_value=httpx.Response(
            200, json={"agent_id": "a1", "name": "Jane Doe", "online": True}
        )
    )

    result = await _call_with_creds(
        mcp, "acme.teramind.co", "tok", "teramind_get_agent", {"agent_id": "a1"}
    )
    text = _text(result)
    assert '"agent_id":"a1"' in text


# -- alerts (TC-TMD-005, TC-TMD-006, TC-TMD-007) -----------------------------


@respx.mock
async def test_list_alerts_returns_window(mcp):
    """TC-TMD-005 / AC4."""
    route = respx.get(f"{BASE}/tm-api/v1/alerts").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "al1",
                    "timestamp": "2026-11-01T00:00:00Z",
                    "agent": {"id": "a1", "name": "Jane"},
                    "computer": {"id": "c1", "name": "WS-1"},
                    "rule_id": 7,
                }
            ],
        )
    )

    result = await _call_with_creds(
        mcp,
        "acme.teramind.co",
        "tok",
        "teramind_list_alerts",
        {"period_start": "2026-11-01T00:00:00Z", "period_end": "2026-11-02T00:00:00Z"},
    )
    assert route.called
    assert route.calls.last.request.url.params["periodStart"] == "2026-11-01T00:00:00Z"
    text = _text(result)
    assert '"rule_id":7' in text


@respx.mock
async def test_list_alerts_requires_period_start(mcp):
    """TC-TMD-006 / AC4."""
    with respx.mock(assert_all_called=False) as mock:
        route = mock.get(f"{BASE}/tm-api/v1/alerts")
        result = await _call_with_creds(
            mcp,
            "acme.teramind.co",
            "tok",
            "teramind_list_alerts",
            {"period_start": "", "period_end": "2026-11-02T00:00:00Z"},
        )
        assert not route.called
    text = _text(result)
    assert '"code":"invalid_argument"' in text


@respx.mock
async def test_describe_alert_rules_returns_names(mcp):
    """TC-TMD-007 / AC5."""
    route = respx.post(f"{BASE}/tm-api/v1/alerts/descriptions").mock(
        return_value=httpx.Response(
            200, json=[{"id": 7, "name": "Large file upload", "description": "..."}]
        )
    )

    result = await _call_with_creds(
        mcp, "acme.teramind.co", "tok", "teramind_describe_alert_rules", {"rule_ids": [7]}
    )
    assert route.called
    text = _text(result)
    assert '"Large file upload"' in text


# -- behavior policies (TC-TMD-008) ------------------------------------------


@respx.mock
async def test_list_behavior_policies(mcp):
    """TC-TMD-008 / AC6."""
    respx.get(f"{BASE}/tm-api/behavior-policy").mock(
        return_value=httpx.Response(
            200, json=[{"behavior_policy_id": "p1", "behavior_group_id": "g1"}]
        )
    )
    result = await _call_with_creds(
        mcp, "acme.teramind.co", "tok", "teramind_list_behavior_policies", {}
    )
    assert '"policies"' in _text(result)


@respx.mock
async def test_get_behavior_policy(mcp):
    """TC-TMD-008 / AC6."""
    respx.get(f"{BASE}/tm-api/behavior-policy/p1").mock(
        return_value=httpx.Response(200, json={"behavior_policy_id": "p1", "rules": []})
    )
    result = await _call_with_creds(
        mcp, "acme.teramind.co", "tok", "teramind_get_behavior_policy", {"policy_id": "p1"}
    )
    assert '"behavior_policy_id":"p1"' in _text(result)


@respx.mock
async def test_list_behavior_groups(mcp):
    """TC-TMD-008 / AC6."""
    respx.get(f"{BASE}/tm-api/behavior-group").mock(
        return_value=httpx.Response(200, json=[{"behavior_group_id": "g1", "name": "Default"}])
    )
    result = await _call_with_creds(
        mcp, "acme.teramind.co", "tok", "teramind_list_behavior_groups", {}
    )
    assert '"groups"' in _text(result)


@respx.mock
async def test_list_anomaly_rules(mcp):
    """TC-TMD-008 / AC6."""
    respx.get(f"{BASE}/tm-api/behavior-rule").mock(
        return_value=httpx.Response(200, json=[{"behavior_rule_id": "r1", "name": "Exfiltration"}])
    )
    result = await _call_with_creds(
        mcp, "acme.teramind.co", "tok", "teramind_list_anomaly_rules", {}
    )
    assert '"rules"' in _text(result)


# -- SSRF guard at the tool layer (TC-TMD-010) -------------------------------


async def test_invalid_instance_host_rejected_before_any_outbound_call(mcp):
    """TC-TMD-010 / AC7."""
    with respx.mock(assert_all_called=False) as mock:
        route = mock.get(url__regex=r".*")
        result = await _call_with_creds(
            mcp, "evil.example.com", "tok", "teramind_list_computers", {}
        )
        assert not route.called
    text = _text(result)
    assert '"code":"invalid_argument"' in text


# -- upstream failure mapping at the tool layer (TC-TMD-011) -----------------


@respx.mock
async def test_upstream_503_returns_upstream_error_envelope(mcp, monkeypatch):
    """TC-TMD-011 / AC8."""
    import teramind_mcp.client as client_module

    async def _no_sleep(_seconds):
        return None

    monkeypatch.setattr(client_module.asyncio, "sleep", _no_sleep)

    respx.get(f"{BASE}/tm-api/computer").mock(
        return_value=httpx.Response(503, json={"message": "down"})
    )
    result = await _call_with_creds(
        mcp, "acme.teramind.co", "tok", "teramind_list_computers", {}
    )
    text = _text(result)
    assert '"code":"upstream_error"' in text
    assert '"retryable":true' in text


# -- multi-tenant isolation (TC-TMD-013, mocked variant; live variant needs a
#    real vendor account and is not required to gate 6b) --------------------


@respx.mock
async def test_concurrent_requests_do_not_cross_tenants(mcp):
    """TC-TMD-013 / AC10 (mocked variant)."""
    route_a = respx.get("https://tenant-a.teramind.co/tm-api/computer").mock(
        return_value=httpx.Response(200, json=[{"id": "a-only"}])
    )
    route_b = respx.get("https://tenant-b.teramind.co/tm-api/computer").mock(
        return_value=httpx.Response(200, json=[{"id": "b-only"}])
    )

    result_a, result_b = await asyncio.gather(
        _call_with_creds(mcp, "tenant-a.teramind.co", "token-a", "teramind_list_computers", {}),
        _call_with_creds(mcp, "tenant-b.teramind.co", "token-b", "teramind_list_computers", {}),
    )

    assert route_a.calls.last.request.headers["x-access-token"] == "token-a"
    assert route_b.calls.last.request.headers["x-access-token"] == "token-b"

    text_a, text_b = _text(result_a), _text(result_b)
    assert "a-only" in text_a and "b-only" not in text_a and "token-b" not in text_a
    assert "b-only" in text_b and "a-only" not in text_b and "token-a" not in text_b
