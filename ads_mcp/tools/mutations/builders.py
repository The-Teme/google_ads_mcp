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

"""Atomic campaign builders for non-Search campaign types.

Each builder returns a list of ``MutateOperation`` protos that create a whole
campaign (budget + campaign + ad group + ad, or campaign + asset group +
listing group + asset links for Performance Max) in a *single*
``GoogleAdsService.mutate`` call. Operations reference one another through
temporary resource names (negative IDs), so the campaign is created atomically:
either everything is created or nothing is.

The builders construct protos directly and do not need a live API client, which
keeps them pure and unit-testable offline. Only ``execute_mutate`` touches the
network. Both the direct-execute tools (campaign_types.py) and the
approval-gated tools (gated_campaign_types.py) build the same operation list
from these helpers, so the two paths can never drift apart.
"""

from __future__ import annotations

from typing import Any

from ads_mcp.guardrails import check_budget_micros
from ads_mcp.tools._ads_api import common_types
from ads_mcp.tools._ads_api import enum_types
from ads_mcp.tools._ads_api import service_types
from ads_mcp.tools.mutations.bidding import apply_bidding
from ads_mcp.tools.mutations.bidding import require_conversion_strategy
from ads_mcp.tools.mutations.common import _resolve_enum
from fastmcp.exceptions import ToolError

# Temporary (negative) resource IDs used to wire operations together within one
# atomic request. Values are arbitrary but must be unique and negative.
_TMP_BUDGET = -1
_TMP_CAMPAIGN = -2
_TMP_AD_GROUP = -3
_TMP_ASSET_GROUP = -3  # PMax has no ad group, so this slot is reused.
_TMP_ASSET_BASE = -100  # Inline assets count down from here.

_EU_POLITICAL_FALSE = (
    enum_types.EuPoliticalAdvertisingStatusEnum.EuPoliticalAdvertisingStatus.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING
)


def _tmp_rn(customer_id: str, collection: str, tmp_id: int) -> str:
  """Build a temporary resource name for cross-referencing within a request."""
  return f"customers/{customer_id}/{collection}/{tmp_id}"


def _budget_op(
    customer_id: str, name: str, amount_micros: int
) -> tuple[Any, str]:
  """Build a CampaignBudget create op. Returns (op, temp_resource_name)."""
  check_budget_micros(amount_micros)
  rn = _tmp_rn(customer_id, "campaignBudgets", _TMP_BUDGET)
  op = service_types.MutateOperation()
  budget = op.campaign_budget_operation.create
  budget.resource_name = rn
  budget.name = name
  budget.amount_micros = amount_micros
  budget.delivery_method = (
      enum_types.BudgetDeliveryMethodEnum.BudgetDeliveryMethod.STANDARD
  )
  budget.explicitly_shared = False
  return op, rn


def _campaign_op(
    customer_id: str,
    *,
    name: str,
    channel: str,
    status: str,
    budget_rn: str,
    bidding_strategy: str,
    target_cpa_micros: int | None,
    target_roas: float | None,
) -> tuple[Any, Any, str]:
  """Build a Campaign create op. Returns (op, campaign_proto, temp_rn).

  The campaign proto is returned so callers can set channel-specific fields
  (shopping_setting, network_settings) before the op is appended.
  """
  rn = _tmp_rn(customer_id, "campaigns", _TMP_CAMPAIGN)
  op = service_types.MutateOperation()
  campaign = op.campaign_operation.create
  campaign.resource_name = rn
  campaign.name = name
  campaign.status = _resolve_enum(
      enum_types.CampaignStatusEnum.CampaignStatus, status, "status"
  )
  campaign.advertising_channel_type = _resolve_enum(
      enum_types.AdvertisingChannelTypeEnum.AdvertisingChannelType,
      channel,
      "channel",
  )
  campaign.campaign_budget = budget_rn
  campaign.contains_eu_political_advertising = _EU_POLITICAL_FALSE
  apply_bidding(
      campaign,
      bidding_strategy,
      target_cpa_micros=target_cpa_micros,
      target_roas=target_roas,
  )
  return op, campaign, rn


def _ad_group_op(
    customer_id: str,
    *,
    name: str,
    campaign_rn: str,
    ad_group_type: str | None,
    status: str = "ENABLED",
    cpc_bid_micros: int | None = None,
) -> tuple[Any, str]:
  """Build an AdGroup create op. Returns (op, temp_resource_name).

  Pass ad_group_type=None to leave the type unset (required for Demand Gen).
  """
  rn = _tmp_rn(customer_id, "adGroups", _TMP_AD_GROUP)
  op = service_types.MutateOperation()
  ad_group = op.ad_group_operation.create
  ad_group.resource_name = rn
  ad_group.name = name
  ad_group.campaign = campaign_rn
  ad_group.status = _resolve_enum(
      enum_types.AdGroupStatusEnum.AdGroupStatus, status, "status"
  )
  if ad_group_type is not None:
    ad_group.type_ = _resolve_enum(
        enum_types.AdGroupTypeEnum.AdGroupType, ad_group_type, "ad_group_type"
    )
  if cpc_bid_micros is not None:
    ad_group.cpc_bid_micros = cpc_bid_micros
  return op, rn


def _text_assets(texts: list[str]):
  """Return a list of AdTextAsset protos from plain strings."""
  return [common_types.AdTextAsset(text=t) for t in texts]


def _image_assets(resource_names: list[str]):
  """Return a list of AdImageAsset protos from image asset resource names."""
  return [common_types.AdImageAsset(asset=rn) for rn in resource_names]


def _video_assets(resource_names: list[str]):
  """Return a list of AdVideoAsset protos from video asset resource names."""
  return [common_types.AdVideoAsset(asset=rn) for rn in resource_names]


_ENABLED_AD = enum_types.AdGroupAdStatusEnum.AdGroupAdStatus.ENABLED


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------


def build_display_campaign(
    customer_id: str,
    *,
    name: str,
    budget_micros: int,
    final_url: str,
    headlines: list[str],
    long_headline: str,
    descriptions: list[str],
    business_name: str,
    marketing_image_assets: list[str],
    square_marketing_image_assets: list[str],
    logo_image_assets: list[str] | None = None,
    status: str = "PAUSED",
    bidding_strategy: str = "MAXIMIZE_CONVERSIONS",
    target_cpa_micros: int | None = None,
    target_roas: float | None = None,
) -> tuple[list[Any], str]:
  """Build operations for a Display campaign with one responsive display ad."""
  if not marketing_image_assets or not square_marketing_image_assets:
    raise ToolError(
        "A responsive display ad needs at least one marketing_image_asset and "
        "one square_marketing_image_asset (create them with create_image_asset)."
    )
  ops: list[Any] = []
  budget_op, budget_rn = _budget_op(
      customer_id, f"{name} budget", budget_micros
  )
  ops.append(budget_op)

  campaign_op, campaign, campaign_rn = _campaign_op(
      customer_id,
      name=name,
      channel="DISPLAY",
      status=status,
      budget_rn=budget_rn,
      bidding_strategy=bidding_strategy,
      target_cpa_micros=target_cpa_micros,
      target_roas=target_roas,
  )
  campaign.network_settings.target_content_network = True
  ops.append(campaign_op)

  ad_group_op, ad_group_rn = _ad_group_op(
      customer_id,
      name=f"{name} ad group",
      campaign_rn=campaign_rn,
      ad_group_type="DISPLAY_STANDARD",
  )
  ops.append(ad_group_op)

  op = service_types.MutateOperation()
  ad_group_ad = op.ad_group_ad_operation.create
  ad_group_ad.ad_group = ad_group_rn
  ad_group_ad.status = _ENABLED_AD
  ad = ad_group_ad.ad
  ad.final_urls.append(final_url)
  rda = ad.responsive_display_ad
  rda.headlines.extend(_text_assets(headlines))
  rda.long_headline.text = long_headline
  rda.descriptions.extend(_text_assets(descriptions))
  rda.business_name = business_name
  rda.marketing_images.extend(_image_assets(marketing_image_assets))
  rda.square_marketing_images.extend(
      _image_assets(square_marketing_image_assets)
  )
  if logo_image_assets:
    rda.logo_images.extend(_image_assets(logo_image_assets))
  ops.append(op)

  summary = (
      f"Create DISPLAY campaign '{name}' (customer {customer_id}, "
      f"status={status}, budget={budget_micros / 1_000_000:.2f}/day, "
      f"bidding={bidding_strategy}) with a responsive display ad."
  )
  return ops, summary


# ---------------------------------------------------------------------------
# Shopping
# ---------------------------------------------------------------------------


def build_shopping_campaign(
    customer_id: str,
    *,
    name: str,
    budget_micros: int,
    merchant_id: int,
    feed_label: str = "",
    campaign_priority: int = 0,
    status: str = "PAUSED",
    bidding_strategy: str = "MAXIMIZE_CONVERSION_VALUE",
    target_roas: float | None = None,
    target_cpa_micros: int | None = None,
) -> tuple[list[Any], str]:
  """Build operations for a standard Shopping campaign (all products)."""
  ops: list[Any] = []
  budget_op, budget_rn = _budget_op(
      customer_id, f"{name} budget", budget_micros
  )
  ops.append(budget_op)

  campaign_op, campaign, campaign_rn = _campaign_op(
      customer_id,
      name=name,
      channel="SHOPPING",
      status=status,
      budget_rn=budget_rn,
      bidding_strategy=bidding_strategy,
      target_cpa_micros=target_cpa_micros,
      target_roas=target_roas,
  )
  campaign.shopping_setting.merchant_id = merchant_id
  if feed_label:
    campaign.shopping_setting.feed_label = feed_label
  if campaign_priority:
    campaign.shopping_setting.campaign_priority = campaign_priority
  ops.append(campaign_op)

  ad_group_op, ad_group_rn = _ad_group_op(
      customer_id,
      name=f"{name} ad group",
      campaign_rn=campaign_rn,
      ad_group_type="SHOPPING_PRODUCT_ADS",
  )
  ops.append(ad_group_op)

  # Product ads carry no creative; they render from the Merchant Center feed.
  op = service_types.MutateOperation()
  ad_group_ad = op.ad_group_ad_operation.create
  ad_group_ad.ad_group = ad_group_rn
  ad_group_ad.status = _ENABLED_AD
  # Touch the field so the (empty) ShoppingProductAdInfo is set on the ad.
  ad_group_ad.ad.shopping_product_ad._pb.SetInParent()
  ops.append(op)

  summary = (
      f"Create SHOPPING campaign '{name}' (customer {customer_id}, "
      f"status={status}, budget={budget_micros / 1_000_000:.2f}/day, "
      f"merchant_id={merchant_id}, bidding={bidding_strategy})."
  )
  return ops, summary


# ---------------------------------------------------------------------------
# Demand Gen
# ---------------------------------------------------------------------------


def build_demand_gen_campaign(
    customer_id: str,
    *,
    name: str,
    budget_micros: int,
    final_url: str,
    headlines: list[str],
    descriptions: list[str],
    business_name: str,
    marketing_image_assets: list[str],
    square_marketing_image_assets: list[str],
    logo_image_assets: list[str],
    status: str = "PAUSED",
    bidding_strategy: str = "MAXIMIZE_CONVERSIONS",
    target_cpa_micros: int | None = None,
    target_roas: float | None = None,
) -> tuple[list[Any], str]:
  """Build operations for a Demand Gen campaign with a multi-asset ad."""
  require_conversion_strategy(bidding_strategy, "Demand Gen")
  if not (
      marketing_image_assets
      and square_marketing_image_assets
      and logo_image_assets
  ):
    raise ToolError(
        "A Demand Gen multi-asset ad needs at least one marketing_image, one "
        "square_marketing_image, and one logo_image asset."
    )
  ops: list[Any] = []
  budget_op, budget_rn = _budget_op(
      customer_id, f"{name} budget", budget_micros
  )
  ops.append(budget_op)

  campaign_op, _, campaign_rn = _campaign_op(
      customer_id,
      name=name,
      channel="DEMAND_GEN",
      status=status,
      budget_rn=budget_rn,
      bidding_strategy=bidding_strategy,
      target_cpa_micros=target_cpa_micros,
      target_roas=target_roas,
  )
  ops.append(campaign_op)

  # Demand Gen ad groups do not take an explicit AdGroupType; leave it unset.
  ad_group_op, ad_group_rn = _ad_group_op(
      customer_id,
      name=f"{name} ad group",
      campaign_rn=campaign_rn,
      ad_group_type=None,
  )
  ops.append(ad_group_op)

  op = service_types.MutateOperation()
  ad_group_ad = op.ad_group_ad_operation.create
  ad_group_ad.ad_group = ad_group_rn
  ad_group_ad.status = _ENABLED_AD
  ad = ad_group_ad.ad
  ad.final_urls.append(final_url)
  dg = ad.demand_gen_multi_asset_ad
  dg.headlines.extend(_text_assets(headlines))
  dg.descriptions.extend(_text_assets(descriptions))
  dg.business_name = business_name
  dg.marketing_images.extend(_image_assets(marketing_image_assets))
  dg.square_marketing_images.extend(
      _image_assets(square_marketing_image_assets)
  )
  dg.logo_images.extend(_image_assets(logo_image_assets))
  ops.append(op)

  summary = (
      f"Create DEMAND_GEN campaign '{name}' (customer {customer_id}, "
      f"status={status}, budget={budget_micros / 1_000_000:.2f}/day, "
      f"bidding={bidding_strategy}) with a multi-asset ad."
  )
  return ops, summary


# ---------------------------------------------------------------------------
# Video / YouTube
# ---------------------------------------------------------------------------


def build_video_campaign(
    customer_id: str,
    *,
    name: str,
    budget_micros: int,
    final_url: str,
    video_assets: list[str],
    headlines: list[str],
    long_headlines: list[str],
    descriptions: list[str],
    business_name: str,
    status: str = "PAUSED",
    bidding_strategy: str = "MAXIMIZE_CONVERSIONS",
    target_cpa_micros: int | None = None,
    target_roas: float | None = None,
) -> tuple[list[Any], str]:
  """Build operations for a Video campaign with a responsive video ad."""
  if not video_assets:
    raise ToolError(
        "A video campaign needs at least one video_asset (create it with "
        "create_youtube_video_asset)."
    )
  ops: list[Any] = []
  budget_op, budget_rn = _budget_op(
      customer_id, f"{name} budget", budget_micros
  )
  ops.append(budget_op)

  campaign_op, _, campaign_rn = _campaign_op(
      customer_id,
      name=name,
      channel="VIDEO",
      status=status,
      budget_rn=budget_rn,
      bidding_strategy=bidding_strategy,
      target_cpa_micros=target_cpa_micros,
      target_roas=target_roas,
  )
  ops.append(campaign_op)

  ad_group_op, ad_group_rn = _ad_group_op(
      customer_id,
      name=f"{name} ad group",
      campaign_rn=campaign_rn,
      ad_group_type="VIDEO_RESPONSIVE",
  )
  ops.append(ad_group_op)

  op = service_types.MutateOperation()
  ad_group_ad = op.ad_group_ad_operation.create
  ad_group_ad.ad_group = ad_group_rn
  ad_group_ad.status = _ENABLED_AD
  ad = ad_group_ad.ad
  ad.final_urls.append(final_url)
  vra = ad.video_responsive_ad
  vra.videos.extend(_video_assets(video_assets))
  vra.headlines.extend(_text_assets(headlines))
  vra.long_headlines.extend(_text_assets(long_headlines))
  vra.descriptions.extend(_text_assets(descriptions))
  vra.business_name.text = business_name
  ops.append(op)

  summary = (
      f"Create VIDEO campaign '{name}' (customer {customer_id}, "
      f"status={status}, budget={budget_micros / 1_000_000:.2f}/day, "
      f"bidding={bidding_strategy}) with a responsive video ad."
  )
  return ops, summary


# ---------------------------------------------------------------------------
# Performance Max
# ---------------------------------------------------------------------------


def build_pmax_campaign(
    customer_id: str,
    *,
    name: str,
    budget_micros: int,
    final_url: str,
    headlines: list[str],
    long_headlines: list[str],
    descriptions: list[str],
    business_name: str,
    marketing_image_assets: list[str],
    square_marketing_image_assets: list[str],
    logo_image_assets: list[str],
    youtube_video_assets: list[str] | None = None,
    merchant_id: int | None = None,
    feed_label: str = "",
    status: str = "PAUSED",
    bidding_strategy: str = "MAXIMIZE_CONVERSIONS",
    target_cpa_micros: int | None = None,
    target_roas: float | None = None,
) -> tuple[list[Any], str]:
  """Build operations for a Performance Max campaign with one asset group.

  Performance Max has no ad groups, keywords, or ads. Text and media are linked
  to an asset group via AssetGroupAsset. Text assets are created inline (as
  temporary assets) in the same atomic request. For retail PMax, pass a
  merchant_id to attach a Merchant Center feed and an "all products" listing
  group filter.
  """
  require_conversion_strategy(bidding_strategy, "Performance Max")
  if not (
      marketing_image_assets
      and square_marketing_image_assets
      and logo_image_assets
  ):
    raise ToolError(
        "A Performance Max asset group needs at least one marketing_image, one "
        "square_marketing_image, and one logo_image asset."
    )
  if len(headlines) < 3:
    raise ToolError("Performance Max requires at least 3 headlines.")
  if len(descriptions) < 2:
    raise ToolError("Performance Max requires at least 2 descriptions.")
  if not long_headlines:
    raise ToolError("Performance Max requires at least 1 long headline.")

  ops: list[Any] = []
  budget_op, budget_rn = _budget_op(
      customer_id, f"{name} budget", budget_micros
  )
  ops.append(budget_op)

  campaign_op, campaign, campaign_rn = _campaign_op(
      customer_id,
      name=name,
      channel="PERFORMANCE_MAX",
      status=status,
      budget_rn=budget_rn,
      bidding_strategy=bidding_strategy,
      target_cpa_micros=target_cpa_micros,
      target_roas=target_roas,
  )
  if merchant_id is not None:
    campaign.shopping_setting.merchant_id = merchant_id
    if feed_label:
      campaign.shopping_setting.feed_label = feed_label
  ops.append(campaign_op)

  asset_group_rn = _tmp_rn(customer_id, "assetGroups", _TMP_ASSET_GROUP)
  ag_op = service_types.MutateOperation()
  asset_group = ag_op.asset_group_operation.create
  asset_group.resource_name = asset_group_rn
  asset_group.name = f"{name} asset group"
  asset_group.campaign = campaign_rn
  asset_group.final_urls.append(final_url)
  asset_group.status = enum_types.AssetGroupStatusEnum.AssetGroupStatus.PAUSED
  ops.append(ag_op)

  field_type_enum = enum_types.AssetFieldTypeEnum.AssetFieldType
  tmp_asset_id = _TMP_ASSET_BASE

  def _link_text(text: str, field_type) -> None:
    nonlocal tmp_asset_id
    asset_rn = _tmp_rn(customer_id, "assets", tmp_asset_id)
    tmp_asset_id -= 1
    asset_op = service_types.MutateOperation()
    asset = asset_op.asset_operation.create
    asset.resource_name = asset_rn
    asset.text_asset.text = text
    ops.append(asset_op)
    _link_asset(asset_rn, field_type)

  def _link_asset(asset_rn: str, field_type) -> None:
    link_op = service_types.MutateOperation()
    link = link_op.asset_group_asset_operation.create
    link.asset_group = asset_group_rn
    link.asset = asset_rn
    link.field_type = field_type
    ops.append(link_op)

  for h in headlines:
    _link_text(h, field_type_enum.HEADLINE)
  for lh in long_headlines:
    _link_text(lh, field_type_enum.LONG_HEADLINE)
  for d in descriptions:
    _link_text(d, field_type_enum.DESCRIPTION)
  _link_text(business_name, field_type_enum.BUSINESS_NAME)

  for img in marketing_image_assets:
    _link_asset(img, field_type_enum.MARKETING_IMAGE)
  for img in square_marketing_image_assets:
    _link_asset(img, field_type_enum.SQUARE_MARKETING_IMAGE)
  for img in logo_image_assets:
    _link_asset(img, field_type_enum.LOGO)
  for vid in youtube_video_assets or []:
    _link_asset(vid, field_type_enum.YOUTUBE_VIDEO)

  # Retail PMax: a top-level "all products" listing group filter is required.
  if merchant_id is not None:
    lgf_op = service_types.MutateOperation()
    lgf = lgf_op.asset_group_listing_group_filter_operation.create
    lgf.asset_group = asset_group_rn
    lgf.type_ = (
        enum_types.ListingGroupFilterTypeEnum.ListingGroupFilterType.UNIT_INCLUDED
    )
    ops.append(lgf_op)

  summary = (
      f"Create PERFORMANCE_MAX campaign '{name}' (customer {customer_id}, "
      f"status={status}, budget={budget_micros / 1_000_000:.2f}/day, "
      f"bidding={bidding_strategy}"
      + (f", merchant_id={merchant_id}" if merchant_id is not None else "")
      + ") with one asset group."
  )
  return ops, summary


# ---------------------------------------------------------------------------
# Execution helpers
# ---------------------------------------------------------------------------


def execute_mutate(ads_client, customer_id: str, operations: list[Any]):
  """Run an atomic GoogleAdsService.mutate and return created resource names."""
  service = ads_client.get_service("GoogleAdsService")
  response = service.mutate(
      customer_id=customer_id, mutate_operations=operations
  )
  return extract_resource_names(response)


def extract_resource_names(response) -> dict[str, list[str]]:
  """Collapse a mutate response into {result_type: [resource_name, ...]}."""
  out: dict[str, list[str]] = {}
  for result in response.mutate_operation_responses:
    which = result._pb.WhichOneof("response")
    if not which:
      continue
    sub = getattr(result, which)
    rn = getattr(sub, "resource_name", None)
    if rn:
      out.setdefault(which, []).append(rn)
  return out
