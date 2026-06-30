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

"""FastMCP middleware that writes the audit log for every tool call.

The hard limits (budget/CPC ceilings, customer-ID allowlist, format checks) are
already enforced inside each tool via ``ads_mcp.guardrails``; a tool that
violates a limit raises before its body runs, and that surfaces here as a
failed call. This middleware's job is the orthogonal "log and review" layer:
record one audit line per tool invocation — reads, writes, and rejections
alike — in a single place so it covers every tool uniformly without touching
each one.
"""

from __future__ import annotations

from ads_mcp.security import audit
from fastmcp.server.middleware import Middleware


class SecurityMiddleware(Middleware):
  """Appends an audit record for every tool call, whatever its outcome."""

  async def on_call_tool(self, context, call_next):
    message = context.message
    tool_name = getattr(message, "name", "<unknown>")
    arguments = getattr(message, "arguments", None) or {}

    try:
      result = await call_next(context)
    except Exception as exc:  # pylint: disable=broad-except
      # Covers guardrail rejections and Ads API errors alike.
      audit.log(tool_name, arguments, "error", str(exc))
      raise

    audit.log(tool_name, arguments, "ok")
    return result
