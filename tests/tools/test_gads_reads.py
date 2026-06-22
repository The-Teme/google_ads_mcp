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

"""Tests for the read-only gads_* tools (§1 account/metadata, §4/§7 reads)."""

from unittest import mock

from ads_mcp.tools import gads_accounts
from ads_mcp.tools import gads_reads
from fastmcp.exceptions import ToolError
import pytest


@mock.patch("ads_mcp.tools.gads_accounts.get_ads_client")
def test_list_resources_no_filter_lists_resources(mock_client):
  client = mock.Mock()
  mock_client.return_value = client
  service = mock.Mock()
  client.get_service.return_value = service
  field = mock.Mock(
      name_=None, category=mock.Mock(name="RESOURCE"),
      data_type=mock.Mock(name="MESSAGE"), selectable=True, filterable=True,
      sortable=False, is_repeated=False,
  )
  field.name = "campaign"
  field.category.name = "RESOURCE"
  field.data_type.name = "MESSAGE"
  service.search_google_ads_fields.return_value = [field]

  out = gads_accounts.gads_list_resources()
  assert out["resource"] is None
  assert out["fields"][0]["name"] == "campaign"
  # No filter -> queries for RESOURCE category.
  query = service.search_google_ads_fields.call_args.kwargs["query"]
  assert "category = RESOURCE" in query


@mock.patch("ads_mcp.tools.gads_accounts.get_ads_client")
def test_list_resources_with_filter_uses_like(mock_client):
  client = mock.Mock()
  mock_client.return_value = client
  service = mock.Mock()
  client.get_service.return_value = service
  service.search_google_ads_fields.return_value = []
  gads_accounts.gads_list_resources("campaign")
  query = service.search_google_ads_fields.call_args.kwargs["query"]
  assert "LIKE 'campaign.%'" in query


@mock.patch("ads_mcp.tools.gads_accounts._search_rows")
def test_get_account_shapes_row(mock_rows):
  c = mock.Mock()
  c.id = 123
  c.descriptive_name = "Acme"
  c.currency_code = "EUR"
  c.time_zone = "Europe/Helsinki"
  c.status.name = "ENABLED"
  c.manager = False
  c.test_account = False
  c.auto_tagging_enabled = True
  c.tracking_url_template = ""
  row = mock.Mock()
  row.customer = c
  mock_rows.return_value = [row]

  out = gads_accounts.gads_get_account("123")
  assert out["id"] == "123"
  assert out["name"] == "Acme"
  assert out["currency"] == "EUR"
  assert out["is_manager"] is False


@mock.patch("ads_mcp.tools.gads_accounts._search_rows")
def test_get_account_no_rows_raises(mock_rows):
  mock_rows.return_value = []
  with pytest.raises(ToolError):
    gads_accounts.gads_get_account("123")


def test_generate_keyword_ideas_requires_seed_or_url():
  with pytest.raises(ToolError):
    gads_reads.gads_generate_keyword_ideas("123")


def test_generate_keyword_ideas_validates_geo_ids():
  with pytest.raises(ToolError):
    gads_reads.gads_generate_keyword_ideas(
        "123", seed_keywords=["x"], geo_target_ids=["abc"]
    )


@mock.patch("ads_mcp.tools.gads_reads.get_ads_client")
def test_list_assets_builds_type_filter(mock_client):
  client = mock.Mock()
  mock_client.return_value = client
  service = mock.Mock()
  client.get_service.return_value = service
  service.search_stream.return_value = []  # no rows
  gads_reads.gads_list_assets("123", asset_type="image")
  query = service.search_stream.call_args.kwargs["query"]
  assert "asset.type = IMAGE" in query
