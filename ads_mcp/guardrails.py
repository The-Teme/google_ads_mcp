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

"""Security guardrails shared by every tool.

Two independent controls:

1. Account scoping — every customer_id / login_customer_id is normalised to
   10 digits, format-checked, and (optionally) checked against an allowlist
   (ADS_MCP_ALLOWED_CUSTOMER_IDS). Without an allowlist the credentials can
   reach every account in the MCC tree; this lets an operator pin the server
   to the accounts it is actually meant to touch.

2. Spend caps — budget and CPC-bid amounts are checked against ceilings
   (ADS_MCP_MAX_BUDGET_MICROS, ADS_MCP_MAX_CPC_BID_MICROS) so a model error or
   a prompt-injection cannot create a runaway budget. Set a cap to 0 to
   disable it.

All failures raise fastmcp ToolError, which is surfaced to the caller.
"""

from __future__ import annotations

import os
import re

from fastmcp.exceptions import ToolError

_CUSTOMER_ID_RE = re.compile(r"^\d{10}$")

# Defaults are deliberately ON. They are generous enough for most accounts and
# trivially raised via env var, but a default-off guardrail is no guardrail.
_DEFAULT_MAX_BUDGET_MICROS = 1_000_000_000  # 1,000.00 / day
_DEFAULT_MAX_CPC_BID_MICROS = 100_000_000  # 100.00


def _normalize_customer_id(value: str | None) -> str:
  """Strip dashes/whitespace so '123-456-7890' becomes '1234567890'."""
  return re.sub(r"[-\s]", "", value or "")


def _allowlist() -> set[str] | None:
  """Return the configured allowlist, or None when unset (allow-all)."""
  raw = os.getenv("ADS_MCP_ALLOWED_CUSTOMER_IDS", "").strip()
  if not raw:
    return None
  return {
      _normalize_customer_id(item) for item in raw.split(",") if item.strip()
  }


def validate_customer_id(value: str, field: str = "customer_id") -> str:
  """Normalise and validate a Google Ads customer ID.

  Args:
    value: The raw ID (digits, optionally dash-separated).
    field: Field name for error messages.

  Returns:
    The normalised 10-digit ID.

  Raises:
    ToolError: On bad format or when the ID is not in the allowlist.
  """
  normalized = _normalize_customer_id(value)
  if not _CUSTOMER_ID_RE.match(normalized):
    raise ToolError(
        f"Invalid {field} {value!r}: expected a 10-digit Google Ads customer "
        "ID (dashes allowed)."
    )
  allow = _allowlist()
  if allow is not None and normalized not in allow:
    raise ToolError(
        f"{field} {normalized} is not permitted. Add it to "
        "ADS_MCP_ALLOWED_CUSTOMER_IDS to allow access."
    )
  return normalized


def validate_accounts(
    customer_id: str,
    login_customer_id: str | None = None,
) -> tuple[str, str | None]:
  """Validate both account IDs at a tool's entry point.

  Returns:
    (normalised customer_id, normalised login_customer_id or None).
  """
  cid = validate_customer_id(customer_id, "customer_id")
  lcid = (
      validate_customer_id(login_customer_id, "login_customer_id")
      if login_customer_id
      else None
  )
  return cid, lcid


def _read_cap(env_var: str, default: int) -> int:
  """Read an integer micros cap from env. Empty/unset uses the default."""
  raw = os.getenv(env_var)
  if raw is None or raw.strip() == "":
    return default
  try:
    value = int(raw)
  except ValueError as e:
    raise ToolError(
        f"Invalid {env_var}={raw!r}: must be an integer number of micros."
    ) from e
  if value < 0:
    raise ToolError(f"Invalid {env_var}={raw!r}: must be >= 0 (0 disables).")
  return value


def check_budget_micros(amount_micros: int) -> None:
  """Reject negative or over-cap daily budgets.

  Cap is ADS_MCP_MAX_BUDGET_MICROS (default 1,000.00/day). Set to 0 to disable.
  """
  if amount_micros < 0:
    raise ToolError("amount_micros must be non-negative.")
  cap = _read_cap("ADS_MCP_MAX_BUDGET_MICROS", _DEFAULT_MAX_BUDGET_MICROS)
  if cap and amount_micros > cap:
    raise ToolError(
        f"Budget {amount_micros} micros ({amount_micros / 1_000_000:.2f}) "
        f"exceeds the cap of {cap} micros ({cap / 1_000_000:.2f}). Raise "
        "ADS_MCP_MAX_BUDGET_MICROS to allow more, or set it to 0 to disable."
    )


def check_bid_micros(bid_micros: int) -> None:
  """Reject negative or over-cap CPC bids.

  Cap is ADS_MCP_MAX_CPC_BID_MICROS (default 100.00). Set to 0 to disable.
  """
  if bid_micros < 0:
    raise ToolError("cpc_bid_micros must be non-negative.")
  cap = _read_cap("ADS_MCP_MAX_CPC_BID_MICROS", _DEFAULT_MAX_CPC_BID_MICROS)
  if cap and bid_micros > cap:
    raise ToolError(
        f"CPC bid {bid_micros} micros ({bid_micros / 1_000_000:.2f}) exceeds "
        f"the cap of {cap} micros ({cap / 1_000_000:.2f}). Raise "
        "ADS_MCP_MAX_CPC_BID_MICROS to allow more, or set it to 0 to disable."
    )


def check_target_cpa_micros(target_cpa_micros: int) -> None:
  """Reject negative or over-cap target CPA bids.

  A target CPA is the average amount you're willing to pay per conversion.
  It reuses the CPC-bid ceiling (ADS_MCP_MAX_CPC_BID_MICROS, default 100.00)
  since both are per-action amounts. Set the cap to 0 to disable.
  """
  if target_cpa_micros < 0:
    raise ToolError("target_cpa_micros must be non-negative.")
  cap = _read_cap("ADS_MCP_MAX_CPC_BID_MICROS", _DEFAULT_MAX_CPC_BID_MICROS)
  if cap and target_cpa_micros > cap:
    raise ToolError(
        f"Target CPA {target_cpa_micros} micros "
        f"({target_cpa_micros / 1_000_000:.2f}) exceeds the cap of {cap} "
        f"micros ({cap / 1_000_000:.2f}). Raise ADS_MCP_MAX_CPC_BID_MICROS to "
        "allow more, or set it to 0 to disable."
    )


# Target ROAS is a ratio (revenue / spend), e.g. 4.0 means $4 back per $1 spent.
# A wildly large value is almost always a typo (e.g. micros vs ratio confusion)
# and would effectively stop the campaign from spending, so we sanity-bound it.
_MAX_TARGET_ROAS = 1000.0


def check_target_roas(target_roas: float) -> None:
  """Reject a target ROAS that is non-positive or implausibly large."""
  if target_roas <= 0:
    raise ToolError("target_roas must be greater than 0.")
  if target_roas > _MAX_TARGET_ROAS:
    raise ToolError(
        f"target_roas {target_roas} is implausibly large (max "
        f"{_MAX_TARGET_ROAS}). It is a ratio such as 4.0 (= 400% return), not "
        "a micros value."
    )
