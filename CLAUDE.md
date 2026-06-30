# Google Ads MCP Server

## Project Overview
The **Google Ads MCP Server** is a Python implementation of the Model Context Protocol (MCP) that bridges Large Language Models (LLMs), such as Claude, with the Google Ads API. It allows users to interact with their Google Ads accounts using natural language queries to retrieve campaigns, metrics, and other data.

This is a security-hardened fork of the upstream Google Ads MCP. See `SECURITY.md` for the full defense model (read-only by default, human-in-the-loop approval workflow, account allowlist, budget/CPC caps, audit log).

It exposes several MCP tools and resources:
*   **Always-on read-only tools:**
    *   `execute_gaql`: Execute Google Ads Query Language queries.
    *   `list_accessible_accounts`: List accessible customer IDs.
    *   `list_mcc_child_accounts` / `get_account_hierarchy` / `get_account_summary`: MCC navigation.
    *   `get_gaql_doc`: Retrieve GAQL grammar documentation.
    *   `get_reporting_view_doc`: Retrieve documentation for specific reporting views (e.g., campaign, ad_group).
*   **Mutation tools (only when `ADS_MCP_ENABLE_MUTATIONS=true`):**
    *   Approval-gated by default: `propose_*` → `list_pending_changes` → `approve_change` / `reject_change`.
    *   Covers budgets, Search / Display / Shopping / Demand Gen / Video / Performance Max campaigns, ad groups, ads, criteria, and assets.
    *   Direct-execute equivalents stay OFF unless `ADS_MCP_DIRECT_MUTATIONS=true`.
*   **Resources:**
    *   `resource://Google_Ads_Query_Language`: GAQL guide.
    *   `resource://Google_Ads_API_Reporting_Views`: Overview of reporting views.
    *   `resource://views/{view}`: Detailed metadata for specific views.

## Tech Stack
*   **Language:** Python 3.12+
*   **Package Manager:** `uv`
*   **Key Libraries:**
    *   `fastmcp`: For building the MCP server.
    *   `google-ads`: Official Google Ads API client.
    *   `mcp`: Core MCP library.
    *   `pytest`: Testing framework.
*   **Tooling:**
    *   `pyink`: Auto-formatter (Google style).
    *   `pylint`: Linter.

## Project Structure
*   `ads_mcp/`: Main source code directory.
    *   `server.py`: HTTP (`streamable-http`) entry point — hardened, auth-gated.
    *   `stdio.py`: stdio entry point — no network port, preferred for local use.
    *   `coordinator.py`: Server coordinator / `mcp_server` instance.
    *   `guardrails.py`: Customer-ID validation, account allowlist, budget/CPC caps.
    *   `security/`: `SecurityMiddleware` (audit log, untrusted-content tagging).
    *   `tools/`: Specific MCP tools implementation.
        *   `reporting.py`: `execute_gaql` and reporting tools.
        *   `accounts.py` / `mcc.py`: Account listing and MCC navigation.
        *   `docs.py`: Documentation tools exposing `context/` files.
        *   `mutations/`: Approval-gated and direct-execute write tools.
    *   `context/`: Context resources.
        *   `GAQL.md`: GAQL grammar documentation.
        *   `views/`: YAML definitions for reporting views.
*   `tests/`: Test suite mirroring the source structure.
*   `pyproject.toml`: Project configuration and dependencies.
*   `SECURITY.md`: Security model and operational checklist.

## Setup & Development

### Prerequisites
*   Python 3.12 or higher.
*   `uv` installed (`pip install uv` or via other methods).
*   **Credentials:** A `google-ads.yaml` file is required for authentication. This file should contain `client_id`, `client_secret`, `refresh_token`, and `developer_token`.

### Installation
Sync dependencies using `uv`:

```bash
uv pip sync
# OR just
uv sync
```

### Key Commands

**Run the Server:**
For local single-user use, prefer the stdio entry point (no network port):
```bash
uv run -m ads_mcp.stdio
```
The HTTP transport (`uv run -m ads_mcp.server`) opens a network port and refuses
to start without an auth provider unless `ADS_MCP_ALLOW_INSECURE_HTTP=true`.

**Run Tests:**
Execute the test suite using `pytest`:
```bash
uv run pytest
```

**Formatting:**
Format code using `pyink` (enforces Google Style):
```bash
uv run pyink .
```

**Linting:**
Check for errors using `pylint`:
```bash
uv run pylint ads_mcp tests
```

## Development Conventions
*   **Style Guide:** Follow the **Google Python Style Guide**.
    *   **Indentation:** 2 spaces (no tabs).
    *   **Line Length:** 79 characters.
    *   **Vertical Alignment:** Align wrapped elements vertically or use a hanging 4-space indent.
*   **Testing:**
    *   Write test cases using the Python built-in `unittest` module.
    *   Run tests using `pytest`.
    *   **MCP Tool Testing:** When testing functions decorated with `@mcp.tool()`, access the underlying function via the `.fn` attribute (e.g., `api.tool_name.fn()`).
    *   New features must include corresponding tests.
*   **Environment Variables:**
    *   `GOOGLE_ADS_CREDENTIALS`: Path to the `google-ads.yaml` file (defaults to `$ROOT_DIR/google-ads.yaml`).
    *   `USE_GOOGLE_OAUTH_ACCESS_TOKEN`: Set to enable Google OAuth token verification.
    *   `ADS_MCP_ENABLE_MUTATIONS`: `true` to register write tools (default off, read-only).
    *   `ADS_MCP_DIRECT_MUTATIONS`: `true` to register approval-bypassing direct-execute tools (default off).
    *   `ADS_MCP_ALLOWED_CUSTOMER_IDS`: Comma-separated customer-ID allowlist (strongly recommended).
    *   `ADS_MCP_MAX_BUDGET_MICROS` / `ADS_MCP_MAX_CPC_BID_MICROS`: Hard caps on budget and CPC.
    *   See `SECURITY.md` for the full list and the locked-down local config.
