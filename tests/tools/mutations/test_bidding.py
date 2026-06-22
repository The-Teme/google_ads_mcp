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

"""Tests for the bidding-strategy helper."""

from ads_mcp.tools._ads_api import resource_types
from ads_mcp.tools.mutations import bidding
from fastmcp.exceptions import ToolError
import pytest


def _campaign():
  return resource_types.Campaign(name="x")


def test_maximize_clicks_sets_target_spend():
  c = _campaign()
  bidding.apply_bidding(c, "maximize_clicks")
  assert c._pb.HasField("target_spend")


def test_maximize_conversions_with_target_cpa():
  c = _campaign()
  bidding.apply_bidding(c, "MAXIMIZE_CONVERSIONS", target_cpa_micros=5_000_000)
  assert c.maximize_conversions.target_cpa_micros == 5_000_000


def test_target_cpa_requires_target():
  c = _campaign()
  with pytest.raises(ToolError):
    bidding.apply_bidding(c, "TARGET_CPA")


def test_target_roas_sets_value():
  c = _campaign()
  bidding.apply_bidding(c, "TARGET_ROAS", target_roas=4.0)
  assert c.target_roas.target_roas == 4.0


def test_target_roas_requires_target():
  c = _campaign()
  with pytest.raises(ToolError):
    bidding.apply_bidding(c, "TARGET_ROAS")


def test_invalid_strategy_rejected():
  c = _campaign()
  with pytest.raises(ToolError):
    bidding.apply_bidding(c, "NOT_A_STRATEGY")


def test_over_cap_target_cpa_rejected():
  c = _campaign()
  with pytest.raises(ToolError):
    # Default cap is 100.00 -> 100_000_000 micros.
    bidding.apply_bidding(c, "TARGET_CPA", target_cpa_micros=10**12)


def test_require_conversion_strategy_rejects_non_conversion():
  with pytest.raises(ToolError):
    bidding.require_conversion_strategy("MAXIMIZE_CLICKS", "Performance Max")


def test_require_conversion_strategy_accepts_conversion():
  # Should not raise.
  bidding.require_conversion_strategy("MAXIMIZE_CONVERSIONS", "Demand Gen")
