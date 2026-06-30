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

"""Observability layer for the Google Ads MCP server.

The hard limits (budget/CPC ceilings, customer-ID allowlist, format checks)
are enforced per-tool in ``ads_mcp.guardrails``. This package adds the
"log and review" mitigation on top of that enforcement:

  audit       – append-only JSONL log of every tool call (reads + writes).
  middleware  – a FastMCP middleware that writes the audit record for every
                tool uniformly, including the original direct-execute tools,
                not just the gated propose_* ones.
"""
