# Security guide

This MCP server can mutate live Google Ads accounts. The controls below reduce
the blast radius of a confused agent, a prompt-injection attack, or a bad
argument. Layers in **bold** are enforced in code; the rest are operational
steps you take when you deploy.

## Defense layers in this server

### 1. Read-only by default
Mutation tools are only registered when `ADS_MCP_ENABLE_MUTATIONS=true`. With it
unset the server exposes reporting, account listing, and docs only — no way to
change anything.

### 2. Human-in-the-loop approvals
With mutations enabled, only the approval-gated tools are registered by default:
every change goes through `propose_* → list_pending_changes → approve_change`.
Nothing hits the Ads API until `approve_change` runs. **The human gate is your
MCP client's per-tool permission prompt** — configure the client so that
`approve_change` requires an explicit human confirmation, and never auto-approve
it. The approval-bypassing direct-execute tools stay off unless you opt in with
`ADS_MCP_DIRECT_MUTATIONS=true`.

### 3. Account-level guardrails (enforced per tool)
`ads_mcp/guardrails.py` validates and normalizes every
`customer_id` / `login_customer_id` / `mcc_id` and enforces hard limits at the
entry of every reporting, MCC, mutation, `propose_*`, and `preview_*` tool —
**before** any change is staged or run:

| Env var | Effect |
|---|---|
| `ADS_MCP_ALLOWED_CUSTOMER_IDS` | Comma-separated customer IDs the server may touch (dashes ignored). Any other `customer_id`/`login_customer_id` is refused. Unset = all reachable accounts. **Strongly recommended.** |
| `ADS_MCP_MAX_BUDGET_MICROS` | Rejects any budget create/update whose `amount_micros` exceeds this. Default `1000000000` (1,000.00/day). Set to `0` to disable. |
| `ADS_MCP_MAX_CPC_BID_MICROS` | Rejects any CPC bid above this. Default `100000000` (100.00). Set to `0` to disable. |

Customer IDs must be 10 digits and are format-checked; negative amounts are
rejected. Also set budget caps / shared budgets **inside Google Ads itself** so
even a raised ceiling can't overspend.

### 4. Audit log
Every tool call (reads and writes) is appended as one JSON line to
`~/.google_ads_mcp/audit.log` (override with `ADS_MCP_AUDIT_LOG_PATH`), with
timestamp, tool, customer ID, arguments (truncated), and outcome (`ok`/`error`).
This is written by `SecurityMiddleware`, which wraps every tool uniformly. Skim
the log regularly, especially early on. Logging failures never break a tool
call.

### 5. Untrusted content tagging
`execute_gaql` results are third-party data (ad copy, competitor names, etc.).
The response includes a `_security_notice` marking the rows as untrusted data,
not instructions. Still: **do not** run scraped/external content in the same
session that has live mutation tools loaded.

### 6. Auth gate for HTTP transport
The `streamable-http` transport exposes a network port and **refuses to start
without an auth provider** unless you set `ADS_MCP_ALLOW_INSECURE_HTTP=true`.
Host/port default to `127.0.0.1:8000`. For single-user local use, prefer the
stdio entrypoint (`run-mcp-server-stdio`, i.e. `-m ads_mcp.stdio`), which opens
no network port.

### 7. Error masking
The server runs with `mask_error_details=True`, so raw API errors (which can
echo request internals) are not leaked back through the tool channel.

## Operational checklist (do these when you deploy)

- [ ] **Scope OAuth narrowly.** Use a dedicated Google user with access only to
      the specific Ads account(s) you automate — not your whole MCC. Prefer a
      read-only scope when you only need reporting.
- [ ] **Protect tokens.** Keep `developer_token`, `client_secret`, and
      `refresh_token` in the credentials YAML or env / a secret manager. The
      YAML is git-ignored — never commit it. Don't paste tokens into prompts.
- [ ] **Prefer the stdio entrypoint.** `run-mcp-server-stdio` opens no network
      port. Only use `streamable-http` behind auth
      (`FASTMCP_SERVER_AUTH_GOOGLE_*` / `USE_GOOGLE_OAUTH_ACCESS_TOKEN`) on a
      trusted network.
- [ ] **Sandbox the process.** Run in the project venv at minimum, ideally a
      container, and restrict outbound network to Google's API domains so a
      compromised server can't exfiltrate.
- [ ] **Pin the version.** This is a fork of the upstream Google Ads MCP. Pin to
      a reviewed commit, read diffs before upgrading, and note the Ads API
      version (`v24`).
- [ ] **Set guardrail env vars** (`ADS_MCP_ALLOWED_CUSTOMER_IDS`,
      `ADS_MCP_MAX_BUDGET_MICROS`, `ADS_MCP_MAX_CPC_BID_MICROS`) and
      account-level budget caps in Google Ads.
- [ ] **Review the audit log** periodically.

## Quickstart: locked-down local config

```bash
export ADS_MCP_ENABLE_MUTATIONS=true
export ADS_MCP_DIRECT_MUTATIONS=false          # gated approvals only
export ADS_MCP_ALLOWED_CUSTOMER_IDS=1234567890 # only this account
export ADS_MCP_MAX_BUDGET_MICROS=50000000      # $50/day ceiling
export ADS_MCP_MAX_CPC_BID_MICROS=2000000      # $2.00 max CPC
# run via the stdio entrypoint (run-mcp-server-stdio / -m ads_mcp.stdio)
# audit log -> ~/.google_ads_mcp/audit.log
```
