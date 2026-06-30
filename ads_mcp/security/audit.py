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

"""Append-only audit log of every tool call.

One JSON object per line is written to ~/.google_ads_mcp/audit.log (override
with ADS_MCP_AUDIT_LOG_PATH). The log captures reads and writes alike so the
operator can skim exactly what the agent did against the account — the "log and
review" mitigation.

Each record:
  {"ts": ISO-8601, "tool": str, "customer_id": str|None,
   "status": "ok"|"error"|"blocked", "detail": str, "args": {...}}

Tool arguments are stored for traceability. Google Ads tool arguments do not
carry OAuth tokens or secrets (those live in the credentials YAML / env), so
this does not widen token exposure; values are still truncated to keep the log
compact.
"""

from __future__ import annotations

import datetime
import json
import os
import pathlib
import threading
from typing import Any

_DEFAULT_PATH = pathlib.Path.home() / ".google_ads_mcp" / "audit.log"
_MAX_VALUE_LEN = 500

_lock = threading.Lock()


def _path() -> pathlib.Path:
  override = os.getenv("ADS_MCP_AUDIT_LOG_PATH")
  return pathlib.Path(override) if override else _DEFAULT_PATH


def _truncate(value: Any) -> Any:
  """Shortens long string values so the log stays readable."""
  if isinstance(value, str) and len(value) > _MAX_VALUE_LEN:
    return value[:_MAX_VALUE_LEN] + f"...<+{len(value) - _MAX_VALUE_LEN} chars>"
  return value


def _sanitize(arguments: dict[str, Any] | None) -> dict[str, Any]:
  if not arguments:
    return {}
  return {k: _truncate(v) for k, v in arguments.items()}


def log(
    tool_name: str,
    arguments: dict[str, Any] | None,
    status: str,
    detail: str = "",
) -> None:
  """Appends one record to the audit log. Never raises.

  Args:
    tool_name: The tool that was invoked.
    arguments: The tool's keyword arguments.
    status: "ok", "error", or "blocked".
    detail: Optional extra context (e.g. an error or guardrail message).
  """
  args = arguments or {}
  record = {
      "ts": datetime.datetime.now(datetime.UTC).isoformat(),
      "tool": tool_name,
      "customer_id": args.get("customer_id"),
      "status": status,
      "detail": _truncate(detail) if detail else "",
      "args": _sanitize(args),
  }
  line = json.dumps(record, default=str, ensure_ascii=False)
  try:
    path = _path()
    with _lock:
      path.parent.mkdir(parents=True, exist_ok=True)
      with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
  except OSError:
    # Auditing must never break the actual tool call; swallow write failures.
    pass
