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

"""Approval workflow tools for Google Ads mutations.

All mutation tools in this server stage changes as 'pending' rather than
executing them immediately. This module provides three tools:

  list_pending_changes()          – See what is waiting for approval.
  approve_change(change_id)       – Execute a staged change.
  reject_change(change_id)        – Discard a staged change.

And a Python-level helper used by other mutation modules:

  propose(tool_name, customer_id, summary, params, executor)

  The executor is a zero-argument callable that, when called, performs the
  actual Google Ads API mutation and returns a dict result.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ads_mcp.coordinator import mcp_server as mcp
from ads_mcp.state.pending_store import make_change, store
from fastmcp.exceptions import ToolError


# ---------------------------------------------------------------------------
# Python-level helper called by other mutation modules
# ---------------------------------------------------------------------------

def propose(
    tool_name: str,
    customer_id: str,
    summary: str,
    params: dict[str, Any],
    executor: Callable[[], Any],
) -> dict[str, Any]:
  """Stage a mutation as a pending change and return a preview dict.

  This is the single choke-point that all mutation tools call instead of
  hitting the Google Ads API directly.

  Args:
    tool_name:   Name of the originating tool (e.g. "create_search_campaign").
    customer_id: The Google Ads customer ID being modified.
    summary:     A plain-English description of what the change will do.
    params:      The raw tool arguments for audit-trail purposes.
    executor:    Zero-argument callable that performs the actual mutation.
                 It is stored in-process (not serialised to JSON) and
                 invoked by approve_change().

  Returns:
    A dict with change_id, summary, status="pending", and instructions
    for the LLM / user on how to approve or reject.
  """
  change = make_change(tool_name, customer_id, summary, params)
  store.add(change)

  # Keep the executor in a separate in-process registry so it survives
  # across tool calls in the same server session without leaking to JSON.
  _executor_registry[change.change_id] = executor

  return {
      "change_id": change.change_id,
      "status": "pending",
      "summary": summary,
      "customer_id": customer_id,
      "tool": tool_name,
      "created_at": change.created_at,
      "instructions": (
          f"Change staged. Call approve_change('{change.change_id}') to "
          f"execute, or reject_change('{change.change_id}') to discard."
      ),
  }


# In-process registry: change_id → callable. Not persisted to disk.
_executor_registry: dict[str, Callable[[], Any]] = {}


# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------

@mcp.tool()
def list_pending_changes(
    status: str = "pending",
) -> list[dict[str, Any]]:
  """Lists staged Google Ads changes awaiting review.

  Args:
    status: Filter by status. One of: "pending", "approved", "rejected".
            Defaults to "pending".

  Returns:
    List of change records ordered newest-first.
  """
  valid = ("pending", "approved", "rejected")
  if status not in valid:
    raise ToolError(f"Invalid status {status!r}. Choose from: {valid}")

  changes = store.list_all(status=status)  # type: ignore[arg-type]
  return [
      {
          "change_id": c.change_id,
          "tool": c.tool_name,
          "customer_id": c.customer_id,
          "summary": c.summary,
          "status": c.status,
          "created_at": c.created_at,
          "result": c.result,
          "error": c.error,
      }
      for c in changes
  ]


@mcp.tool()
def approve_change(change_id: str) -> dict[str, Any]:
  """Approves and executes a staged Google Ads change.

  Looks up the pending change by ID, runs the stored mutation against the
  Google Ads API, and marks the change as 'approved' with the API result.

  Args:
    change_id: The 8-character ID returned when the change was staged.

  Returns:
    Dict with change_id, status="approved", and the API result (e.g. the
    resource_name of the created/updated object).
  """
  change = store.get(change_id)
  if not change:
    raise ToolError(
        f"No change found with ID '{change_id}'. "
        "Use list_pending_changes() to see available changes."
    )
  if change.status != "pending":
    raise ToolError(
        f"Change '{change_id}' is already {change.status!r} and cannot be approved."
    )

  executor = _executor_registry.get(change_id)
  if executor is None:
    raise ToolError(
        f"Executor for change '{change_id}' not found in this server session. "
        "This can happen if the server was restarted after the change was staged. "
        "Please reject this change and re-submit the mutation."
    )

  try:
    result = executor()
  except Exception as exc:  # pylint: disable=broad-except
    store.set_status(change_id, "rejected", error=str(exc))
    _executor_registry.pop(change_id, None)
    raise ToolError(
        f"Mutation failed: {exc}. Change marked as rejected."
    ) from exc

  store.set_status(change_id, "approved", result=result)
  _executor_registry.pop(change_id, None)

  return {
      "change_id": change_id,
      "status": "approved",
      "tool": change.tool_name,
      "customer_id": change.customer_id,
      "summary": change.summary,
      "result": result,
  }


@mcp.tool()
def reject_change(change_id: str, reason: str = "") -> dict[str, Any]:
  """Rejects and discards a staged Google Ads change without executing it.

  Args:
    change_id: The 8-character ID of the pending change.
    reason:    Optional reason for rejection (stored in the audit trail).

  Returns:
    Dict confirming the rejection.
  """
  change = store.get(change_id)
  if not change:
    raise ToolError(f"No change found with ID '{change_id}'.")
  if change.status != "pending":
    raise ToolError(
        f"Change '{change_id}' is already {change.status!r} and cannot be rejected."
    )

  error_msg = f"Rejected by user. {reason}".strip() if reason else "Rejected by user."
  store.set_status(change_id, "rejected", error=error_msg)
  _executor_registry.pop(change_id, None)

  return {
      "change_id": change_id,
      "status": "rejected",
      "summary": change.summary,
      "reason": reason,
  }
