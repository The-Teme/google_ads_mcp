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

"""Tests for the atomic campaign builders.

These run fully offline: the builders construct protos directly and do not need
a live API client.
"""

from unittest import mock

from ads_mcp.tools._ads_api import enum_types
from ads_mcp.tools.mutations import builders
from fastmcp.exceptions import ToolError
import pytest

_CID = "1234567890"
_IMG = ["customers/1234567890/assets/100"]
_VID = ["customers/1234567890/assets/200"]


def _op_kinds(ops):
  return [o._pb.WhichOneof("operation") for o in ops]


def test_display_builder_shape():
  ops, summary = builders.build_display_campaign(
      _CID,
      name="D",
      budget_micros=5_000_000,
      final_url="https://x.com",
      headlines=["h1", "h2"],
      long_headline="lh",
      descriptions=["d1", "d2"],
      business_name="Biz",
      marketing_image_assets=_IMG,
      square_marketing_image_assets=_IMG,
      logo_image_assets=_IMG,
  )
  assert _op_kinds(ops) == [
      "campaign_budget_operation",
      "campaign_operation",
      "ad_group_operation",
      "ad_group_ad_operation",
  ]
  campaign = ops[1].campaign_operation.create
  assert (
      campaign.advertising_channel_type
      == enum_types.AdvertisingChannelTypeEnum.AdvertisingChannelType.DISPLAY
  )
  assert campaign.network_settings.target_content_network is True
  rda = ops[3].ad_group_ad_operation.create.ad.responsive_display_ad
  assert [h.text for h in rda.headlines] == ["h1", "h2"]
  assert "DISPLAY" in summary


def test_display_builder_requires_images():
  with pytest.raises(ToolError):
    builders.build_display_campaign(
        _CID,
        name="D",
        budget_micros=5_000_000,
        final_url="https://x.com",
        headlines=["h1"],
        long_headline="lh",
        descriptions=["d1"],
        business_name="Biz",
        marketing_image_assets=[],
        square_marketing_image_assets=[],
    )


def test_shopping_builder_sets_merchant_and_empty_product_ad():
  ops, _ = builders.build_shopping_campaign(
      _CID, name="S", budget_micros=5_000_000, merchant_id=999, target_roas=4.0
  )
  campaign = ops[1].campaign_operation.create
  assert campaign.shopping_setting.merchant_id == 999
  ad = ops[3].ad_group_ad_operation.create.ad
  assert ad._pb.WhichOneof("ad_data") == "shopping_product_ad"


def test_demand_gen_requires_conversion_strategy():
  with pytest.raises(ToolError):
    builders.build_demand_gen_campaign(
        _CID,
        name="DG",
        budget_micros=5_000_000,
        final_url="https://x.com",
        headlines=["h1"],
        descriptions=["d1"],
        business_name="Biz",
        marketing_image_assets=_IMG,
        square_marketing_image_assets=_IMG,
        logo_image_assets=_IMG,
        bidding_strategy="MAXIMIZE_CLICKS",
    )


def test_demand_gen_ad_group_has_no_type():
  ops, _ = builders.build_demand_gen_campaign(
      _CID,
      name="DG",
      budget_micros=5_000_000,
      final_url="https://x.com",
      headlines=["h1"],
      descriptions=["d1"],
      business_name="Biz",
      marketing_image_assets=_IMG,
      square_marketing_image_assets=_IMG,
      logo_image_assets=_IMG,
  )
  ad_group = ops[2].ad_group_operation.create
  # type_ left unset -> UNSPECIFIED
  assert ad_group.type_ == enum_types.AdGroupTypeEnum.AdGroupType.UNSPECIFIED


def test_video_builder_requires_video():
  with pytest.raises(ToolError):
    builders.build_video_campaign(
        _CID,
        name="V",
        budget_micros=5_000_000,
        final_url="https://x.com",
        video_assets=[],
        headlines=["h1"],
        long_headlines=["lh"],
        descriptions=["d1"],
        business_name="Biz",
    )


def test_video_builder_shape():
  ops, _ = builders.build_video_campaign(
      _CID,
      name="V",
      budget_micros=5_000_000,
      final_url="https://x.com",
      video_assets=_VID,
      headlines=["h1"],
      long_headlines=["lh"],
      descriptions=["d1"],
      business_name="Biz",
  )
  ad_group = ops[2].ad_group_operation.create
  assert (
      ad_group.type_ == enum_types.AdGroupTypeEnum.AdGroupType.VIDEO_RESPONSIVE
  )
  vra = ops[3].ad_group_ad_operation.create.ad.video_responsive_ad
  assert vra.videos[0].asset == _VID[0]


def test_pmax_builder_links_assets_and_listing_group():
  ops, _ = builders.build_pmax_campaign(
      _CID,
      name="P",
      budget_micros=5_000_000,
      final_url="https://x.com",
      headlines=["h1", "h2", "h3"],
      long_headlines=["lh"],
      descriptions=["d1", "d2"],
      business_name="Biz",
      marketing_image_assets=_IMG,
      square_marketing_image_assets=_IMG,
      logo_image_assets=_IMG,
      youtube_video_assets=_VID,
      merchant_id=999,
  )
  kinds = _op_kinds(ops)
  assert kinds[0] == "campaign_budget_operation"
  assert kinds[1] == "campaign_operation"
  assert kinds[2] == "asset_group_operation"
  assert "asset_group_listing_group_filter_operation" in kinds
  # 6 text assets created inline (3 headlines + 1 long + 2 desc + business_name)
  assert kinds.count("asset_operation") == 7
  field_types = [
      o.asset_group_asset_operation.create.field_type
      for o in ops
      if o._pb.WhichOneof("operation") == "asset_group_asset_operation"
  ]
  ft = enum_types.AssetFieldTypeEnum.AssetFieldType
  assert ft.HEADLINE in field_types
  assert ft.YOUTUBE_VIDEO in field_types
  assert ft.LOGO in field_types


def test_pmax_requires_minimum_headlines():
  with pytest.raises(ToolError):
    builders.build_pmax_campaign(
        _CID,
        name="P",
        budget_micros=5_000_000,
        final_url="https://x.com",
        headlines=["h1"],
        long_headlines=["lh"],
        descriptions=["d1", "d2"],
        business_name="Biz",
        marketing_image_assets=_IMG,
        square_marketing_image_assets=_IMG,
        logo_image_assets=_IMG,
    )


def test_pmax_non_retail_has_no_listing_group():
  ops, _ = builders.build_pmax_campaign(
      _CID,
      name="P",
      budget_micros=5_000_000,
      final_url="https://x.com",
      headlines=["h1", "h2", "h3"],
      long_headlines=["lh"],
      descriptions=["d1", "d2"],
      business_name="Biz",
      marketing_image_assets=_IMG,
      square_marketing_image_assets=_IMG,
      logo_image_assets=_IMG,
  )
  assert "asset_group_listing_group_filter_operation" not in _op_kinds(ops)


def test_budget_guardrail_enforced_in_builder():
  with mock.patch.dict("os.environ", {"ADS_MCP_MAX_BUDGET_MICROS": "1000000"}):
    with pytest.raises(ToolError):
      builders.build_shopping_campaign(
          _CID,
          name="S",
          budget_micros=5_000_000,
          merchant_id=999,
          target_roas=4.0,
      )


def test_extract_resource_names():
  response = mock.Mock()
  budget_result = mock.Mock()
  budget_result._pb.WhichOneof.return_value = "campaign_budget_result"
  budget_result.campaign_budget_result.resource_name = "customers/1/budgets/2"
  campaign_result = mock.Mock()
  campaign_result._pb.WhichOneof.return_value = "campaign_result"
  campaign_result.campaign_result.resource_name = "customers/1/campaigns/3"
  response.mutate_operation_responses = [budget_result, campaign_result]

  out = builders.extract_resource_names(response)
  assert out["campaign_result"] == ["customers/1/campaigns/3"]
  assert out["campaign_budget_result"] == ["customers/1/budgets/2"]
