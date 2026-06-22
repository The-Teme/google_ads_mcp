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

"""Shared bidding-strategy helper for campaign mutation tools.

Different campaign types require different standard bidding strategies. Search
defaults to MAXIMIZE_CLICKS (TargetSpend); Shopping/Demand Gen/Performance Max
require conversion-based strategies. This module centralises the logic so every
campaign builder attaches a valid, guardrail-checked strategy in one place.

A strategy is selected by a case-insensitive string. Optional target values are
validated against the spend guardrails before being applied.
"""

from __future__ import annotations

from ads_mcp.guardrails import check_target_cpa_micros
from ads_mcp.guardrails import check_target_roas
from ads_mcp.tools._ads_api import common_types
from fastmcp.exceptions import ToolError

# Strategy name -> human description, used for error messages and summaries.
SUPPORTED_BIDDING_STRATEGIES = {
    "MAXIMIZE_CLICKS": "Maximize clicks (TargetSpend)",
    "MAXIMIZE_CONVERSIONS": "Maximize conversions (optional target CPA)",
    "MAXIMIZE_CONVERSION_VALUE": "Maximize conversion value (optional tROAS)",
    "TARGET_CPA": "Target CPA",
    "TARGET_ROAS": "Target ROAS",
    "TARGET_CPM": "Target CPM (reach)",
    "MANUAL_CPC": "Manual CPC",
}

# Conversion-based strategies, exposed so callers (e.g. Performance Max) can
# reject non-conversion strategies that the channel does not allow.
CONVERSION_BIDDING_STRATEGIES = frozenset(
    {
        "MAXIMIZE_CONVERSIONS",
        "MAXIMIZE_CONVERSION_VALUE",
        "TARGET_CPA",
        "TARGET_ROAS",
    }
)


def apply_bidding(
    campaign,
    bidding_strategy: str,
    *,
    target_cpa_micros: int | None = None,
    target_roas: float | None = None,
) -> None:
  """Attaches a standard bidding strategy to a Campaign proto in place.

  Args:
    campaign: A resource_types.Campaign proto (modified in place).
    bidding_strategy: One of SUPPORTED_BIDDING_STRATEGIES (case-insensitive).
    target_cpa_micros: Required for TARGET_CPA; optional for
      MAXIMIZE_CONVERSIONS. Ignored otherwise.
    target_roas: Required for TARGET_ROAS; optional for
      MAXIMIZE_CONVERSION_VALUE. Ignored otherwise. A ratio such as 4.0.

  Raises:
    ToolError: On an unknown strategy or a missing/invalid target value.
  """
  key = (bidding_strategy or "").strip().upper()
  if key not in SUPPORTED_BIDDING_STRATEGIES:
    valid = ", ".join(SUPPORTED_BIDDING_STRATEGIES)
    raise ToolError(
        f"Invalid bidding_strategy {bidding_strategy!r}. Valid values: {valid}."
    )

  if key == "MAXIMIZE_CLICKS":
    campaign.target_spend = common_types.TargetSpend()
  elif key == "MAXIMIZE_CONVERSIONS":
    max_conv = common_types.MaximizeConversions()
    if target_cpa_micros is not None:
      check_target_cpa_micros(target_cpa_micros)
      max_conv.target_cpa_micros = target_cpa_micros
    campaign.maximize_conversions = max_conv
  elif key == "MAXIMIZE_CONVERSION_VALUE":
    max_val = common_types.MaximizeConversionValue()
    if target_roas is not None:
      check_target_roas(target_roas)
      max_val.target_roas = target_roas
    campaign.maximize_conversion_value = max_val
  elif key == "TARGET_CPA":
    if target_cpa_micros is None:
      raise ToolError("target_cpa_micros is required for TARGET_CPA bidding.")
    check_target_cpa_micros(target_cpa_micros)
    campaign.target_cpa = common_types.TargetCpa(
        target_cpa_micros=target_cpa_micros
    )
  elif key == "TARGET_ROAS":
    if target_roas is None:
      raise ToolError("target_roas is required for TARGET_ROAS bidding.")
    check_target_roas(target_roas)
    campaign.target_roas = common_types.TargetRoas(target_roas=target_roas)
  elif key == "TARGET_CPM":
    campaign.target_cpm = common_types.TargetCpm()
  elif key == "MANUAL_CPC":
    campaign.manual_cpc = common_types.ManualCpc()


def require_conversion_strategy(bidding_strategy: str, channel: str) -> None:
  """Raises if the strategy is not conversion-based for the given channel."""
  key = (bidding_strategy or "").strip().upper()
  if key not in CONVERSION_BIDDING_STRATEGIES:
    valid = ", ".join(sorted(CONVERSION_BIDDING_STRATEGIES))
    raise ToolError(
        f"{channel} campaigns require a conversion-based bidding strategy. "
        f"Got {bidding_strategy!r}; valid values: {valid}."
    )
