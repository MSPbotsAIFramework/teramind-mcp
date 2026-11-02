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

### Fixes (review-rework round, 2026-11-02)

Addressed the one must-fix (finding 1, structured per-call logging). Only this item was touched;
nothing else in the code or docs was changed.

- **`src/teramind_mcp/client.py`**: added `logging.getLogger(__name__)` (`teramind_mcp.client`).
  `get()`/`post()` now take a required keyword-only `tool: str`, threaded through to `_request`/
  `_handle`. One `logger.info("tool=%s status=%s code=%s", ...)` line per call that reaches this
  client: `status` is the upstream HTTP status code (or `network_error` for a request that never
  got a response after retries are exhausted), `code` is the same vocabulary as the error envelope
  (`ok` on 2xx/204, `not_found`, `unauthorized`, `rate_limited`, `invalid_argument`,
  `upstream_error`). Neither the instance host (`self._host`) nor the access token (`self._token`)
  is ever passed to a log call — verified both by code inspection and by a live request against the
  real `*.teramind.co` domain (see "Verification" below) with the token and host grepped for in the
  captured output.
- **`src/teramind_mcp/tools/{computers,agents,alerts,behavior}.py`**: all 10 tool call sites
  (`client.get(...)` / `client.post(...)`) updated to pass `tool="<the tool's own registered
  name>"`. No behavior change to any tool — purely passing an identifier through.
- **`src/teramind_mcp/__main__.py`**: added `logging.basicConfig(level=logging.INFO, ...)` at the
  top of `main()`. Without this, the INFO-level log calls above are silently dropped by Python's
  default last-resort handler (WARNING+ only) — i.e. the logging code would exist but nothing would
  ever reach stdout/stderr, which is the same operational gap under a different name. This was not
  explicitly called out in the review finding but is necessary for the fix to do anything in
  production; confirmed uvicorn's own `dictConfig` (invoked inside `uvicorn.run`) does not remove
  this handler (`disable_existing_loggers=False` is uvicorn's default).
- **Tests** (`tests/test_client.py`): the 6 pre-existing `TeramindClient.get(...)` call sites in
  this file needed the new required `tool=` keyword too (not a behavior change, just following the
  signature). Added two new tests: `test_successful_call_logs_tool_status_and_ok_code` and
  `test_error_call_logs_tool_status_and_error_code`, both using `caplog` to assert the exact
  `tool=...status=...code=...` fields are present in the log output, and that neither the fake
  token nor the fake host string appears anywhere in `caplog.text`.

**Verification** (`uv run pytest -v`, re-run on this fix):

```
37 passed, 1 warning in 0.78s
```

(35 from round 1 + 2 new logging tests = 37; no other test count changed.) `ruff check .`: all
checks passed (2 `E501` line-length violations introduced by the `tool="..."` additions were
wrapped). Chinese-text scan
(`grep -rnP '[\x{4e00}-\x{9fff}]' --exclude-dir=.git --exclude-dir=.venv .`) has exactly one hit —
`docs/tickets/PRD-21246-review.md:12`, the reviewer's own round-1 finding text quoting the SOP §14
checklist section's Chinese title ("日志与敏感信息") for citation. That line is the reviewer's
frozen record from round 1 and predates this round's changes; it is not introduced by this fix.
Flagging as a WARN per `REVIEW.md` §3 rather than editing someone else's review finding.

Live end-to-end check (not just the mocked unit tests): ran the server locally
(`uv run python -m teramind_mcp`, placeholder port), confirmed:
- `GET /health` → `200`.
- `POST /mcp tools/list` with no credential headers → `401` (unchanged).
- `POST /mcp tools/call teramind_list_computers` with `X-Teramind-Instance: evil.example.com` (SSRF
  guard) → in-band `invalid_argument` envelope, **no log line** — this path is rejected inside
  `TeramindClient.__init__` before `get`/`post` is ever called, so no `tool` name is available at
  that point; this is a known, disclosed scope boundary of this fix (the review's finding named
  `client.py`'s `_request`/`_handle`, which this path never reaches — no outbound call happens
  either, per TC-TMD-010).
- `POST /mcp tools/call teramind_list_computers` with `X-Teramind-Instance: acme.teramind.co`
  (real domain, placeholder/non-existent tenant, same precedent as round 1's Self-test "Live
  verification") → real upstream response ("Deleted instance") mapped to `upstream_error`, and the
  server's stdout captured exactly:
  `2026-11-02 22:45:17,568 INFO teramind_mcp.client tool=teramind_list_computers status=500
  code=upstream_error` — confirming the log line reaches the process's actual output, not just the
  test harness. Grepped the captured output for the placeholder token string: not present.

**Not changed**: `docs/tickets/PRD-21246.md` / nothing in the frozen main ticket doc — this round
only touches code, tests, and this review doc's Fixes section, per the review-rework rule.
README `Connector` section: unchanged (`git diff --name-only` confirms `README.md` is not in this
round's diff).

Next: next review round should re-check this file set against the must-fix above.
