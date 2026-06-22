# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""The server for the Google Ads API MCP.

Tool groups
-----------
Always-on (read-only):
  reporting   – execute_gaql
  accounts    – list_accessible_accounts
  docs        – GAQL / reporting view documentation
  mcc         – list_mcc_child_accounts, get_account_hierarchy, get_account_summary

Approval workflow (always-on):
  approval    – list_pending_changes, approve_change, reject_change

Mutation tools (enabled when ADS_MCP_ENABLE_MUTATIONS=true):
  preview          – preview_* diff tools (read-only, no API writes)
  gated_campaign   – propose_* tools that stage changes for approval
  budget / campaign / ad_group / ad / criterion  – original direct-execute
                     tools from the upstream repo (still available for
                     power users who want them; they bypass the approval flow)

  Note: direct-execute tools bypass the approval flow. They are OFF by
  default (approval-only). Set ADS_MCP_DIRECT_MUTATIONS=true to register
  them for power users who explicitly want them.
"""

import asyncio
import os

from ads_mcp.coordinator import mcp_server
from ads_mcp.scripts.generate_views import update_views_yaml
from ads_mcp.tools import accounts
from ads_mcp.tools import docs
from ads_mcp.tools import gads_accounts
from ads_mcp.tools import gads_reads
from ads_mcp.tools import mcc
from ads_mcp.tools import performance
from ads_mcp.tools import reporting
from ads_mcp.tools._utils import get_ads_client
from ads_mcp.tools.mutations import approval  # always register approval tools
import dotenv
from fastmcp.server.auth.providers.google import GoogleProvider
from fastmcp.server.auth.providers.google import GoogleTokenVerifier

dotenv.load_dotenv()

# ---------------------------------------------------------------------------
# Always-on tools (read + approval workflow)
# ---------------------------------------------------------------------------
tools = [
    reporting,
    accounts,
    docs,
    mcc,
    performance,
    gads_accounts,
    gads_reads,
    approval,
]

# ---------------------------------------------------------------------------
# Mutation tools (opt-in via env var)
# ---------------------------------------------------------------------------
if os.getenv("ADS_MCP_ENABLE_MUTATIONS", "false").lower() == "true":
  from ads_mcp.tools.mutations import preview       # diff/preview tools
  from ads_mcp.tools.mutations import gated_campaign  # propose_* tools

  tools.extend([preview, gated_campaign])

  # Approval-gated gads_* mutation tools (spec sections 3-7). These route
  # through the same propose()/approve_change() workflow and add per-tool
  # validate_only dry-runs and paused-by-default creation.
  from ads_mcp.tools.gads_mutations import structure        # §3
  from ads_mcp.tools.gads_mutations import budgets_bidding   # §6
  from ads_mcp.tools.gads_mutations import ads_creatives     # §4
  from ads_mcp.tools.gads_mutations import keywords_targeting  # §5
  from ads_mcp.tools.gads_mutations import recommendations   # §7 apply/dismiss

  tools.extend([
      structure,
      budgets_bidding,
      ads_creatives,
      keywords_targeting,
      recommendations,
  ])

  # Original direct-execute tools bypass the approval flow and are therefore
  # OFF by default. Set ADS_MCP_DIRECT_MUTATIONS=true to opt back in.
  if os.getenv("ADS_MCP_DIRECT_MUTATIONS", "false").lower() == "true":
    from ads_mcp.tools.mutations import budget     # pylint: disable=ungrouped-imports
    from ads_mcp.tools.mutations import campaign   # pylint: disable=ungrouped-imports
    from ads_mcp.tools.mutations import ad_group   # pylint: disable=ungrouped-imports
    from ads_mcp.tools.mutations import ad         # pylint: disable=ungrouped-imports
    from ads_mcp.tools.mutations import criterion  # pylint: disable=ungrouped-imports

    tools.extend([budget, campaign, ad_group, ad, criterion])

# ---------------------------------------------------------------------------
# Auth (optional)
# ---------------------------------------------------------------------------
if os.getenv("USE_GOOGLE_OAUTH_ACCESS_TOKEN"):
  mcp_server.auth = GoogleTokenVerifier()

if os.getenv("FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_ID") and os.getenv(
    "FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_SECRET"
):
  base_url = os.getenv("FASTMCP_SERVER_BASE_URL", "http://localhost:8000")
  mcp_server.auth = GoogleProvider(
      client_id=os.getenv("FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_ID"),
      base_url=base_url,
      required_scopes=["https://www.googleapis.com/auth/adwords"],
  )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
  """Initializes and runs the MCP server."""
  asyncio.run(update_views_yaml())
  get_ads_client()

  # The streamable-http transport exposes a network port. Refuse to start
  # without an auth provider unless the operator explicitly opts into an
  # insecure (e.g. trusted-localhost-only) deployment. Without this guard an
  # unauthenticated port grants full control of the Google Ads account.
  auth_configured = getattr(mcp_server, "auth", None) is not None
  allow_insecure = (
      os.getenv("ADS_MCP_ALLOW_INSECURE_HTTP", "false").lower() == "true"
  )
  if not auth_configured and not allow_insecure:
    raise SystemExit(
        "Refusing to start streamable-http without authentication.\n"
        "Configure Google OAuth (FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_ID +\n"
        "FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_SECRET, or "
        "USE_GOOGLE_OAUTH_ACCESS_TOKEN),\n"
        "or for a trusted local-only setup set "
        "ADS_MCP_ALLOW_INSECURE_HTTP=true\n"
        "(and keep the host bound to 127.0.0.1). For single-user local use, "
        "prefer the stdio entrypoint (run-mcp-server-stdio)."
    )

  host = os.getenv("FASTMCP_SERVER_HOST", "127.0.0.1")
  port = int(os.getenv("FASTMCP_SERVER_PORT", "8000"))
  print(f"mcp server starting on {host}:{port} ...")
  mcp_server.run(
      transport="streamable-http",
      host=host,
      port=port,
      show_banner=False,
  )


if __name__ == "__main__":
  main()
