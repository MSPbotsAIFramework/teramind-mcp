# PRD-21246 · Code review

## Round 1 · 2026-11-02 · reviewed dev/PRD-21246 @ a22b7ca (base main @ b95db34)

Verdict: changes requested

### Findings

1. [must-fix] `src/teramind_mcp/client.py` (whole file, see also `tools/*.py`) — the tech design's
   Non-functional section (`docs/tickets/PRD-21246.md:360-362`, "Observability") commits to: "log
   tool name, upstream status code, and error `code` (never the access token or full response
   body) per call", and the SOP §14 checklist ("日志与敏感信息") lists structured logging with a
   request id as a delivery item. There is no logging implementation anywhere in the repository —
   `grep -rn "logging\|logger" src/` returns nothing, and the only `print()` in the codebase
   (`src/teramind_mcp/__main__.py:37`) is a one-time startup banner, not per-request. Uvicorn's
   default access log (unconfigured here) would at best print `POST /mcp -> 200` for every call
   regardless of which of the 10 tools ran or what `error.code` came back, which does not satisfy
   the design's own commitment. For a connector whose stated purpose is insider-threat/security
   monitoring, and whose own "Security" NFR calls this "the main risk surface of the whole ticket",
   having no way to trace which tool was called, with what upstream status, and whether it failed,
   is a real operational gap for whoever runs this in production — and it is not disclosed anywhere
   in Self-test or Handoff as a known limitation (which would at minimum need a WARN entry per
   `REVIEW.md` §3). Fix: add structured logging per tool call (tool name, upstream HTTP status code,
   error `code` when present) in `client.py`'s `_request`/`_handle` and/or at the tool layer in
   `tools/*.py`, explicitly excluding the instance host and access token from any log line, and note
   the format in the Self-test section.

No other findings — code quality, test quality, SSRF-guard correctness (instance-host regex has no
bypass found: `evil.example.com`, `teramind.co.evil.com`, and label-prefix tricks like
`notteramind.co` were checked by hand and are all correctly rejected), credential isolation
(`contextvars`, reset in `finally`, no module-level credential state), error-envelope vocabulary,
pagination/token-economy limits (`DEFAULT_LIMIT=50`, `MAX_LIMIT=200`, 20,000-char cap), README
Connector-section verbatim match, and the English-only / no-Chinese check all held up under review.
`uv run pytest` reproduced locally: 35/35 pass, matching the Self-test section exactly.
