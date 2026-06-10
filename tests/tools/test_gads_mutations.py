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

"""Tests for the approval-gated gads_* mutation tools and shared helpers.

These exercise input validation and the propose() hand-off without touching
the Google Ads API (the staged executor is only run on approval).
"""

from unittest import mock

from ads_mcp.tools.gads_mutations import _common
from ads_mcp.tools.gads_mutations import ads_creatives
from ads_mcp.tools.gads_mutations import budgets_bidding
from ads_mcp.tools.gads_mutations import keywords_targeting
from ads_mcp.tools.gads_mutations import recommendations
from ads_mcp.tools.gads_mutations import structure
from fastmcp.exceptions import ToolError
import pytest


# ---------------------------------------------------------------------------
# _common helpers
# ---------------------------------------------------------------------------

def test_require_digits_ok():
  assert _common.require_digits(" 123 ", "x") == "123"


def test_require_digits_rejects_non_digits():
  with pytest.raises(ToolError):
    _common.require_digits("12a", "x")


def test_normalize_date_ok_and_none():
  assert _common.normalize_date("2026-05-01", "d") == "20260501"
  assert _common.normalize_date(None, "d") is None


def test_normalize_date_bad():
  with pytest.raises(ToolError):
    _common.normalize_date("05/01/2026", "d")


def test_single_result_validate_only():
  assert _common.single_result(None, True) == {
      "validated_only": True, "resource_name": None
  }


def test_single_result_real():
  resp = mock.Mock()
  resp.results = [mock.Mock(resource_name="customers/1/campaigns/2")]
  assert _common.single_result(resp, False) == {
      "resource_name": "customers/1/campaigns/2"
  }


def test_multi_result_surfaces_partial_failure():
  resp = mock.Mock()
  resp.results = [mock.Mock(resource_name="rn1")]
  resp.partial_failure_error = mock.Mock(code=3, message="one failed")
  out = _common.multi_result(resp, False)
  assert out["resource_names"] == ["rn1"]
  assert out["partial_failure"] == "one failed"


def test_annotation_presets():
  assert _common.ANN_CREATE["idempotentHint"] is False
  assert _common.ANN_STATUS["destructiveHint"] is True
  assert _common.ANN_UPDATE["idempotentHint"] is True


# ---------------------------------------------------------------------------
# Structure (§3) — staging + validation
# ---------------------------------------------------------------------------

@mock.patch("ads_mcp.tools.gads_mutations.structure.propose")
def test_create_campaign_stages_with_tool_name(mock_propose):
  mock_propose.return_value = {"change_id": "abc", "status": "pending"}
  structure.gads_create_campaign("123", "Camp", "SEARCH", "456")
  tool_name, customer_id, summary, _params, executor = mock_propose.call_args[0]
  assert tool_name == "gads_create_campaign"
  assert customer_id == "123"
  assert "PAUSED" in summary
  assert callable(executor)


def test_create_campaign_rejects_bad_customer_id():
  with pytest.raises(ToolError):
    structure.gads_create_campaign("abc", "Camp", "SEARCH", "456")


@mock.patch("ads_mcp.tools.gads_mutations.structure.propose")
def test_update_campaign_requires_a_field(mock_propose):
  with pytest.raises(ToolError):
    structure.gads_update_campaign("123", "456")  # no fields provided


@mock.patch("ads_mcp.tools.gads_mutations.structure.propose")
def test_create_ad_group_stages(mock_propose):
  mock_propose.return_value = {"change_id": "abc", "status": "pending"}
  structure.gads_create_ad_group("123", "456", "AG")
  assert mock_propose.call_args[0][0] == "gads_create_ad_group"


# ---------------------------------------------------------------------------
# Budgets & bidding (§6)
# ---------------------------------------------------------------------------

@mock.patch("ads_mcp.tools.gads_mutations.budgets_bidding.propose")
def test_create_budget_rejects_nonpositive(mock_propose):
  with pytest.raises(ToolError):
    budgets_bidding.gads_create_budget("123", "B", 0)


@mock.patch("ads_mcp.tools.gads_mutations.budgets_bidding.propose")
def test_update_bidding_rejects_unknown_strategy(mock_propose):
  with pytest.raises(ToolError):
    budgets_bidding.gads_update_bidding_strategy("123", "456", "BOGUS")


@mock.patch("ads_mcp.tools.gads_mutations.budgets_bidding.propose")
def test_update_bidding_target_cpa_requires_target(mock_propose):
  with pytest.raises(ToolError):
    budgets_bidding.gads_update_bidding_strategy("123", "456", "TARGET_CPA")


@mock.patch("ads_mcp.tools.gads_mutations.budgets_bidding.propose")
def test_update_bidding_stages_manual_cpc(mock_propose):
  mock_propose.return_value = {"change_id": "abc", "status": "pending"}
  budgets_bidding.gads_update_bidding_strategy("123", "456", "manual_cpc")
  assert mock_propose.call_args[0][0] == "gads_update_bidding_strategy"


# ---------------------------------------------------------------------------
# Ads & creatives (§4)
# ---------------------------------------------------------------------------

def test_create_rsa_requires_assets():
  with pytest.raises(ToolError):
    ads_creatives.gads_create_responsive_search_ad(
        "123", "456", [], ["d"], ["https://x"]
    )


def test_update_ad_requires_a_field():
  with pytest.raises(ToolError):
    ads_creatives.gads_update_ad("123", "456")


def test_upload_image_requires_source():
  with pytest.raises(ToolError):
    ads_creatives.gads_upload_image_asset("123", "name")


# ---------------------------------------------------------------------------
# Keywords & targeting (§5)
# ---------------------------------------------------------------------------

def test_add_keywords_requires_fields():
  with pytest.raises(ToolError):
    keywords_targeting.gads_add_keywords("123", "456", [{"text": "x"}])


def test_add_negative_keywords_bad_level():
  with pytest.raises(ToolError):
    keywords_targeting.gads_add_negative_keywords(
        "123", "account", "456", ["free"]
    )


def test_set_targeting_requires_exactly_one_parent():
  with pytest.raises(ToolError):
    keywords_targeting.gads_set_targeting(
        "123", [{"type": "geo", "value": "2246"}]
    )  # neither campaign_id nor ad_group_id


@mock.patch("ads_mcp.tools.gads_mutations.keywords_targeting.propose")
def test_set_targeting_stages_with_campaign(mock_propose):
  mock_propose.return_value = {"change_id": "abc", "status": "pending"}
  keywords_targeting.gads_set_targeting(
      "123", [{"type": "geo", "value": "2246"}], campaign_id="789"
  )
  assert mock_propose.call_args[0][0] == "gads_set_targeting"


# ---------------------------------------------------------------------------
# Recommendations (§7 apply/dismiss)
# ---------------------------------------------------------------------------

def test_apply_recommendation_rejects_validate_only():
  with pytest.raises(ToolError):
    recommendations.gads_apply_recommendation(
        "123", "customers/123/recommendations/abc", validate_only=True
    )


@mock.patch("ads_mcp.tools.gads_mutations.recommendations.propose")
def test_dismiss_recommendation_stages(mock_propose):
  mock_propose.return_value = {"change_id": "abc", "status": "pending"}
  recommendations.gads_dismiss_recommendation(
      "123", "customers/123/recommendations/abc"
  )
  assert mock_propose.call_args[0][0] == "gads_dismiss_recommendation"
