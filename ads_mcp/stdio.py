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

"""The stdio entry point for the Google Ads API MCP.

Tool registration is shared with the HTTP server: importing ``ads_mcp.server``
runs the same @mcp.tool decorators (read-only tools always-on, plus the
approval-gated mutation tools when ADS_MCP_ENABLE_MUTATIONS=true), so both
transports expose an identical tool set. This module only differs in the
transport it runs (stdio vs streamable-http).
"""

import asyncio
import sys

# Importing the server module performs ALL tool registrations as a side effect
# (via the @mcp.tool decorators in each tools module). Centralising it here
# keeps the two entry points from drifting apart.
import ads_mcp.server  # noqa: F401  pylint: disable=unused-import
from ads_mcp.coordinator import mcp_server
from ads_mcp.scripts.generate_views import update_views_yaml
from ads_mcp.tools._utils import get_ads_client
import dotenv

dotenv.load_dotenv()


def main():
  """Initializes and runs the MCP server."""
  asyncio.run(update_views_yaml())  # Check and update docs resource
  get_ads_client()  # Check Google Ads credentials
  print("mcp server starting...", file=sys.stderr)
  mcp_server.run(
      transport="stdio",
      show_banner=False,
  )  # Initialize and run the server


if __name__ == "__main__":
  main()
