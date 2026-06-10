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

"""Tests for the convenience performance reporting tools."""

from unittest import mock

from ads_mcp.tools import _utils
from ads_mcp.tools import performance
from fastmcp.exceptions import ToolError
import pytest


@pytest.fixture(autouse=True)
def reset_ads_client():
  """Resets the cached GoogleAdsClient instance before each test."""
  _utils._ADS_CLIENT = None  # pylint: disable=protected-access
  yield
  _utils._ADS_CLIENT = None  # pylint: disable=protected-access


# ---------------------------------------------------------------------------
# _date_clause
# ---------------------------------------------------------------------------

def test_date_clause_default():
  assert performance._date_clause(None, None, None) == (
      "segments.date DURING LAST_30_DAYS"
  )


def test_date_clause_relative_is_uppercased():
  assert performance._date_clause("last_7_days", None, None) == (
      "segments.date DURING LAST_7_DAYS"
  )


def test_date_clause_custom_range():
  assert performance._date_clause(None, "2026-05-01", "2026-05-31") == (
      "segments.date BETWEEN '2026-05-01' AND '2026-05-31'"
  )


def test_date_clause_invalid_range_raises():
  with pytest.raises(ToolError):
    performance._date_clause("LAST_3_DAYS", None, None)


def test_date_clause_partial_custom_raises():
  with pytest.raises(ToolError):
    performance._date_clause(None, "2026-05-01", None)


def test_date_clause_bad_date_format_raises():
  with pytest.raises(ToolError):
    performance._date_clause(None, "2026/05/01", "2026-05-31")


# ---------------------------------------------------------------------------
# _id_clause
# ---------------------------------------------------------------------------

def test_id_clause_empty():
  assert performance._id_clause("campaign.id", None) == ""
  assert performance._id_clause("campaign.id", []) == ""


def test_id_clause_builds_in_filter():
  assert performance._id_clause("campaign.id", ["123", "456"]) == (
      " AND campaign.id IN (123, 456)"
  )


def test_id_clause_rejects_injection():
  with pytest.raises(ToolError):
    performance._id_clause("campaign.id", ["123; DROP TABLE"])


# ---------------------------------------------------------------------------
# _metrics
# ---------------------------------------------------------------------------

def test_metrics_converts_micros_and_computes_roas():
  row = {
      "metrics.impressions": 1000,
      "metrics.clicks": 50,
      "metrics.ctr": 0.05,
      "metrics.average_cpc": 500_000,  # 0.50
      "metrics.cost_micros": 25_000_000,  # 25.00
      "metrics.conversions": 5.0,
      "metrics.conversions_value": 100.0,
      "metrics.cost_per_conversion": 5_000_000,  # 5.00
  }
  m = performance._metrics(row)
  assert m["impressions"] == 1000
  assert m["clicks"] == 50
  assert m["avg_cpc"] == 0.50
  assert m["cost"] == 25.00
  assert m["cost_per_conversion"] == 5.00
  assert m["roas"] == 4.0  # 100 / 25


def test_metrics_handles_zero_cost():
  m = performance._metrics({"metrics.conversions_value": 10.0})
  assert m["cost"] == 0.0
  assert m["roas"] == 0.0


# ---------------------------------------------------------------------------
# gads_get_campaign_performance (query-building + shaping)
# ---------------------------------------------------------------------------

@mock.patch("ads_mcp.tools.performance._rows")
def test_get_campaign_performance_shapes_rows(mock_rows):
  mock_rows.return_value = [{
      "campaign.id": 123,
      "campaign.name": "Test Campaign",
      "campaign.status": "ENABLED",
      "campaign.advertising_channel_type": "SEARCH",
      "metrics.impressions": 100,
      "metrics.clicks": 10,
      "metrics.cost_micros": 10_000_000,
      "metrics.conversions_value": 40.0,
  }]
  result = performance.gads_get_campaign_performance("123", date_range="LAST_7_DAYS")
  assert len(result["data"]) == 1
  row = result["data"][0]
  assert row["campaign_id"] == "123"
  assert row["campaign_name"] == "Test Campaign"
  assert row["cost"] == 10.0
  assert row["roas"] == 4.0

  # The generated query should carry the date filter and ordering.
  _, query, _ = mock_rows.call_args[0]
  assert "segments.date DURING LAST_7_DAYS" in query
  assert "FROM campaign" in query
  assert "ORDER BY metrics.cost_micros DESC" in query


@mock.patch("ads_mcp.tools.performance._rows")
def test_get_search_terms_uses_search_term_view(mock_rows):
  mock_rows.return_value = []
  performance.gads_get_search_terms("123", campaign_ids=["555"])
  _, query, _ = mock_rows.call_args[0]
  assert "FROM search_term_view" in query
  assert "AND campaign.id IN (555)" in query
