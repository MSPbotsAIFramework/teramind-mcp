# teramind-mcp

Stateless HTTP MCP service for the [Teramind Dashboard API](https://apidoc.dev.teramind.co/). Exposes a tenant's Teramind data as MCP tools so AI assistants can review computer/user inventory, security alerts, and behavior-policy configuration for insider-threat monitoring — without opening the Teramind console.

This is a from-scratch, clean-room implementation built from Teramind's publicly published API documentation. It is **read-only v1**: there are no tools that can create, update, or delete anything in a tenant's Teramind account (see "Known limitations" below for why).

<div align="center">

## MSPbots Connector

**The MCP Gateway built for MSPs: visible, controlled, and your data stays where it belongs.**

[**Get started at connect.mspbots.ai →**](https://connect.mspbots.ai)

</div>

---

MSPbots Connector gives your AI clients one MCP URL to reach your entire MSP stack (RMM, PSA, documentation, security, finance), and gives you control over who can call which tool and a record of everything that was called.

**Hosted service: [connect.mspbots.ai](https://connect.mspbots.ai)** · Free to use.

### Why Connector

![MSPbots Connector](https://stgoss.mspbots.ai/files/mcp/mspbots-mcp.png)

| | |
|---|---|
| **Visible** | Every tool call is logged: who, which vendor, when. Usage dashboard, CSV export, SIEM streaming. |
| **Controlled** | Role-based, per-tool allowlist. Deny by default. |
| **Protected** | Credentials encrypted per record. AI clients never see your vendor passwords or tokens. |
| **MSP-native** | Built for the MSP stack only: RMM, PSA, documentation, security, finance. |

### Quick start

1. **Sign up** at [connect.mspbots.ai](https://connect.mspbots.ai).
2. **Connect your vendors.** Pick from 150+ connectors and authorize each one on the vendor's own page, or bring your own API keys. No extra vendor accounts needed.
3. **Set access.** Create roles and decide which tools each role may call. Nothing is allowed until you allow it.
4. **Add your MCP URL to your AI client.** Copy the URL from your Connector dashboard into Claude, ChatGPT, Cursor, VS Code, Gemini, Codex, or any MCP-capable client.
5. **Ask your AI to do real work**, and watch every call appear in the audit log.

### Features

**Unified gateway**
- One MCP URL for all your AI clients
- 150+ connectors across the MSP stack
- Custom MCP servers supported, free
- Authorization happens on each vendor's own page; the AI never sees passwords or tokens
- Bring your own credentials: use the vendor API keys you already have
- Multiple accounts per app; connect once, reuse across AI clients
- Tool search: finds the right action for the task
- One sign-in; vendor credentials are injected behind the scenes and OAuth tokens refresh automatically

**Visibility**
- Audit log for every tool call (who, which vendor, when)
- Usage dashboard: call volume, top vendors, error rate, per-user activity
- Export audit logs to CSV, or stream to Loki, Graylog, or LogScale (SIEM)
- Optional recording of tool arguments and result summaries (off by default, enabled per organization)

**Control**
- Per-role, per-tool allowlist, deny by default
- owner / admin / member roles
- SCIM provisioning with Entra ID, Okta, JumpCloud, and Google Workspace

**Security**
- Credentials encrypted one record at a time (AES-256-GCM, per-record key)
- AI clients authenticate with OAuth 2.1 + PKCE
- Vendor responses are scanned for prompt-injection patterns and returned as structured data. This is one layer of defense, not a guarantee against every attack.
- Static egress IP for customer firewall and API allowlisting

### Pricing

**Free.**

Links: [connect.mspbots.ai](https://connect.mspbots.ai) · [mspbots.ai](https://mspbots.ai)

---

## Authentication headers

Every `/mcp` request must carry both of the following headers. There is no environment-variable fallback — a request missing either header is rejected with `401` before any tool runs.

| Header | Required | Meaning | Where to get it |
|---|---|---|---|
| `X-Teramind-Instance` | Yes | The tenant's own Teramind instance host, e.g. `acme.teramind.co`. Teramind's API is per-instance — there is no shared/global endpoint. Must end in `.teramind.co`; any other host is rejected with a structured `invalid_argument` error (SSRF guard — see "Known limitations"). | The URL the tenant uses to sign in to their Teramind dashboard. |
| `X-Teramind-Access-Token` | Yes | Teramind access token, sent upstream as the `x-access-token` header. | Teramind dashboard → **Administrator → Access Tokens**. |

## Tool List

All ten tools are read-only (`readOnlyHint=true`) — this service has no tool that can change a tenant's Teramind configuration, computers, users, or policies.

| Tool | Description | Key parameters |
|---|---|---|
| `teramind_list_computers` | List the monitored-computer inventory | `limit`, `cursor` |
| `teramind_get_computer` | Get a single computer's full detail record | `computer_id` |
| `teramind_list_agents` | List the monitored-user ("agent") inventory | `limit`, `cursor`, `fields` |
| `teramind_get_agent` | Get a single monitored user's full detail record | `agent_id`, `fields` |
| `teramind_list_alerts` | List alerts raised in a time window | `period_start`, `period_end`, `limit`, `cursor` |
| `teramind_describe_alert_rules` | Get the human-readable name/description for alert rule ids | `rule_ids` |
| `teramind_list_behavior_policies` | List behavior policies | `limit`, `cursor` |
| `teramind_get_behavior_policy` | Get a single behavior policy's full record | `policy_id` |
| `teramind_list_behavior_groups` | List the entity groups behavior policies are organized under | `limit`, `cursor` |
| `teramind_list_anomaly_rules` | List the anomaly-rule catalog behavior policies are built from | `limit`, `cursor` |

### Pagination

None of the upstream list endpoints document native pagination in Teramind's published API collection, so pagination is applied at the MCP layer: the full upstream list is fetched once, then truncated to `limit` (default 50, hard cap 200) with `has_more` / `next_cursor` in the response. `cursor` is an opaque offset into that fetched list — pass back whatever `next_cursor` a prior call returned.

### Errors

Every tool returns either its result or a structured error envelope — never an unhandled exception:

```json
{"error": {"code": "invalid_argument", "message": "...", "retryable": false}}
```

`code` is one of `not_configured`, `unauthorized`, `not_found`, `invalid_argument`, `rate_limited`, `upstream_error`. `retryable` tells the caller whether retrying is worth it.

## Known limitations

- **Read-only v1.** No tool here can create/update/delete computers, agents, policies, or anomaly rules, even though Teramind's API exposes some of those operations. The ticket this connector was built for only asked to "review" data; write/delete tools are a materially larger scope (threat model, audit logging, destructive-action gating) that would need a separate design.
- **Instance-host allow-list is `*.teramind.co` only.** A tenant running a self-hosted/custom-domain Teramind instance is not supported in v1 — such a host is rejected with `invalid_argument` rather than silently allowed. This is a deliberate SSRF guard, not an oversight; extending the allow-list needs a real self-hosted-tenant case to design against.
- **No test account during development.** This connector's unit/integration tests run entirely against a mocked Teramind API (the shapes in this README and in the code are taken from Teramind's own published Postman collection). End-to-end verification against a real Teramind instance is pending a real account; see `docs/tickets/PRD-21246.md` "Test strategy" for what is and isn't covered by that.

## Local development

```bash
uv sync
uv run pytest
```

Run the server locally and exercise it with `curl` (replace the header values with your own test tenant's):

```bash
uv run python -m teramind_mcp
curl -s -X POST http://localhost:8080/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -H 'X-Teramind-Instance: acme.teramind.co' \
  -H 'X-Teramind-Access-Token: <your test token>' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

## Docker

```bash
docker build --platform linux/amd64 -t teramind-mcp:dev .
docker run --rm -p 8080:8080 teramind-mcp:dev
```

## License

Apache-2.0. Copyright MSPbots.ai.
