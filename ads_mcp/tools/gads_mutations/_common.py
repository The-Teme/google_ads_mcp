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

"""Shared helpers for the approval-gated gads_* mutation tools.

Design (per the user's chosen wiring):
  * Every mutating tool stages its change through the existing
    approval workflow — it calls ``propose(...)`` and returns a change_id.
    Nothing hits the Google Ads API until ``approve_change(change_id)`` runs
    the stored executor.
  * In addition (per the spec), each tool accepts ``validate_only`` which,
    when the change is approved, runs the mutate as a Google Ads API
    ``validateOnly`` dry-run (no persistence) and returns ``validated_only``.
  * Created entities default to PAUSED.

This module re-exports the low-level mutation helpers and adds result
formatting + light input validation shared across the gads_ mutation modules.
"""

from __future__ import annotations

from typing import Any

# Re-exported from the existing mutation helpers so gads_ modules have one
# import surface.
from ads_mcp.tools.mutations.common import _get_client  # noqa: F401
from ads_mcp.tools.mutations.common import _handle_google_ads_error  # noqa: F401
from ads_mcp.tools.mutations.common import _resolve_enum  # noqa: F401
from fastmcp.exceptions import ToolError

# Annotation presets matching the spec's R / D / I shorthand.
# Create: not read-only, not destructive, not idempotent.
ANN_CREATE = {
    "readOnlyHint": False,
    "destructiveHint": False,
    "idempotentHint": False,
}
# Update: not read-only, not destructive, idempotent.
ANN_UPDATE = {
    "readOnlyHint": False,
    "destructiveHint": False,
    "idempotentHint": True,
}
# Status change: not read-only, destructive (can REMOVE), idempotent.
ANN_STATUS = {
    "readOnlyHint": False,
    "destructiveHint": True,
    "idempotentHint": True,
}
# Dismiss-like: not read-only, not destructive, idempotent.
ANN_DISMISS = {
    "readOnlyHint": False,
    "destructiveHint": False,
    "idempotentHint": True,
}


def build_request(
    client: Any,
    request_type: str,
    customer_id: str,
    operations: list[Any],
    validate_only: bool = False,
    partial_failure: bool = False,
) -> Any:
  """Builds a Mutate*Request, setting validate_only / partial_failure.

  The Google Ads mutate service methods take these flags on the request
  object, not as kwargs — so every gads_ executor builds its request here.
  partial_failure is mutually exclusive with validate_only and is only
  applied when validate_only is False.
  """
  request = client.get_type(request_type)
  request.customer_id = customer_id
  request.operations.extend(operations)
  request.validate_only = validate_only
  if partial_failure and not validate_only:
    request.partial_failure = True
  return request


def require_digits(value: str, name: str) -> str:
  """Validates that an ID is digits-only and returns it as a string."""
  s = str(value).strip()
  if not s.isdigit():
    raise ToolError(f"{name} must be digits only, got {value!r}.")
  return s


def normalize_date(value: str | None, name: str) -> str | None:
  """Validates a YYYY-MM-DD date and returns it in the API's YYYYMMDD form."""
  if value is None:
    return None
  v = value.strip()
  digits = v.replace("-", "")
  if len(digits) != 8 or not digits.isdigit():
    raise ToolError(f"{name} must be in YYYY-MM-DD format, got {value!r}.")
  return digits


def single_result(response: Any, validate_only: bool) -> dict[str, Any]:
  """Formats the result of a single-operation mutate."""
  if validate_only:
    return {"validated_only": True, "resource_name": None}
  return {"resource_name": response.results[0].resource_name}


def multi_result(response: Any, validate_only: bool) -> dict[str, Any]:
  """Formats the result of a multi-operation mutate, surfacing partial failures."""
  if validate_only:
    return {"validated_only": True, "resource_names": []}
  out: dict[str, Any] = {
      "resource_names": [r.resource_name for r in response.results]
  }
  pf = getattr(response, "partial_failure_error", None)
  if pf is not None and getattr(pf, "code", 0) != 0:
    out["partial_failure"] = pf.message
  return out
