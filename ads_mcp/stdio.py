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

"""The stdio entrypoint for the Google Ads API MCP.

Same tool registration as server.py, but runs the stdio transport (no network
port) — the preferred entrypoint for single-user local use. Startup messages go
to stderr so stdout stays a clean MCP channel.
"""

import asyncio
import os
import sys

from ads_mcp.coordinator import mcp_server
from ads_mcp.scripts.generate_views import update_views_yaml
from ads_mcp.tools import accounts
from ads_mcp.tools import docs
from ads_mcp.tools import mcc
from ads_mcp.tools import reporting
from ads_mcp.tools._utils import verify_credentials_or_exit
from ads_mcp.tools.mutations import approval  # always register approval tools
import dotenv

dotenv.load_dotenv()

# ---------------------------------------------------------------------------
# Always-on tools (read + approval workflow)
# ---------------------------------------------------------------------------
tools = [reporting, accounts, docs, mcc, approval]

# ---------------------------------------------------------------------------
# Mutation tools (opt-in via env var)
# ---------------------------------------------------------------------------
if os.getenv("ADS_MCP_ENABLE_MUTATIONS", "false").lower() == "true":
  from ads_mcp.tools.mutations import preview  # diff/preview tools
  from ads_mcp.tools.mutations import gated_campaign  # propose_* tools
  from ads_mcp.tools.mutations import gated_asset  # propose_* asset tools
  from ads_mcp.tools.mutations import gated_campaign_types  # propose_* campaigns

  tools.extend([preview, gated_campaign, gated_asset, gated_campaign_types])

  # Original direct-execute tools bypass the approval flow and are therefore
  # OFF by default. Set ADS_MCP_DIRECT_MUTATIONS=true to opt back in.
  if os.getenv("ADS_MCP_DIRECT_MUTATIONS", "false").lower() == "true":
    from ads_mcp.tools.mutations import budget  # pylint: disable=ungrouped-imports
    from ads_mcp.tools.mutations import campaign  # pylint: disable=ungrouped-imports
    from ads_mcp.tools.mutations import ad_group  # pylint: disable=ungrouped-imports
    from ads_mcp.tools.mutations import ad  # pylint: disable=ungrouped-imports
    from ads_mcp.tools.mutations import criterion  # pylint: disable=ungrouped-imports
    from ads_mcp.tools.mutations import asset  # pylint: disable=ungrouped-imports
    from ads_mcp.tools.mutations import campaign_types  # pylint: disable=ungrouped-imports

    tools.extend(
        [budget, campaign, ad_group, ad, criterion, asset, campaign_types]
    )


def main():
  """Initializes and runs the MCP server over stdio."""
  asyncio.run(update_views_yaml())  # Check and update docs resource
  verify_credentials_or_exit()  # Check Google Ads credentials
  print("mcp server starting...", file=sys.stderr)
  mcp_server.run(
      transport="stdio",
      show_banner=False,
  )  # Initialize and run the server


if __name__ == "__main__":
  main()
