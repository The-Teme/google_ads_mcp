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

"""Direct-execute campaign builders for Display, Shopping, Demand Gen, Video,
and Performance Max.

Each tool creates a complete campaign in one atomic GoogleAdsService.mutate
call. These bypass the approval flow and are therefore OFF by default; the
approval-gated equivalents live in gated_campaign_types.py. The actual
operation lists are assembled by mutations/builders.py and shared between both.
"""

from __future__ import annotations

from typing import Any

from ads_mcp.coordinator import mcp_server as mcp
from ads_mcp.guardrails import validate_accounts
from ads_mcp.tools.mutations import builders
from ads_mcp.tools.mutations.common import _get_client
from ads_mcp.tools.mutations.common import _handle_google_ads_error
from google.ads.googleads.errors import GoogleAdsException


def _execute(login_customer_id, customer_id, operations) -> dict[str, Any]:
  """Run the atomic mutate and surface Google Ads errors as ToolError."""
  ads_client = _get_client(login_customer_id)
  try:
    return builders.execute_mutate(ads_client, customer_id, operations)
  except GoogleAdsException as e:
    _handle_google_ads_error(e)


@mcp.tool()
def create_display_campaign(
    customer_id: str,
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
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Creates a Display campaign + ad group + responsive display ad atomically.

  Image assets must be created first with create_image_asset; pass their
  resource names here.

  Args:
      customer_id: Google Ads customer ID (digits only).
      name: Campaign name.
      budget_micros: Daily budget in micros (1,000,000 = 1 currency unit).
      final_url: Landing page URL for the ad.
      headlines: Short headline strings (max 30 chars each).
      long_headline: A single long headline (max 90 chars).
      descriptions: Description strings (max 90 chars each).
      business_name: Advertiser/business name shown in the ad.
      marketing_image_assets: Image asset resource names (1.91:1). Required.
      square_marketing_image_assets: Square (1:1) image asset resource names.
        Required.
      logo_image_assets: Optional logo image asset resource names.
      status: PAUSED or ENABLED. Default PAUSED.
      bidding_strategy: MAXIMIZE_CONVERSIONS (default), MAXIMIZE_CLICKS,
        MAXIMIZE_CONVERSION_VALUE, TARGET_CPA, or TARGET_ROAS.
      target_cpa_micros: Target CPA in micros (for TARGET_CPA / optional with
        MAXIMIZE_CONVERSIONS).
      target_roas: Target ROAS ratio, e.g. 4.0 (for TARGET_ROAS / optional with
        MAXIMIZE_CONVERSION_VALUE).
      login_customer_id: MCC account ID if customer is managed.

  Returns:
      Dict of created resource names keyed by result type.
  """
  customer_id, login_customer_id = validate_accounts(
      customer_id, login_customer_id
  )
  operations, _ = builders.build_display_campaign(
      customer_id,
      name=name,
      budget_micros=budget_micros,
      final_url=final_url,
      headlines=headlines,
      long_headline=long_headline,
      descriptions=descriptions,
      business_name=business_name,
      marketing_image_assets=marketing_image_assets,
      square_marketing_image_assets=square_marketing_image_assets,
      logo_image_assets=logo_image_assets,
      status=status,
      bidding_strategy=bidding_strategy,
      target_cpa_micros=target_cpa_micros,
      target_roas=target_roas,
  )
  return _execute(login_customer_id, customer_id, operations)


@mcp.tool()
def create_shopping_campaign(
    customer_id: str,
    name: str,
    budget_micros: int,
    merchant_id: int,
    feed_label: str = "",
    campaign_priority: int = 0,
    status: str = "PAUSED",
    bidding_strategy: str = "MAXIMIZE_CONVERSION_VALUE",
    target_roas: float | None = None,
    target_cpa_micros: int | None = None,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Creates a standard Shopping campaign (all products) atomically.

  Requires a Merchant Center account already linked to the Google Ads account.
  Product ads carry no creative; they render from the Merchant Center feed.

  Args:
      customer_id: Google Ads customer ID (digits only).
      name: Campaign name.
      budget_micros: Daily budget in micros (1,000,000 = 1 currency unit).
      merchant_id: The linked Merchant Center account ID.
      feed_label: Feed label (formerly sales country, e.g. "US"). Optional.
      campaign_priority: Shopping campaign priority 0-2. Default 0.
      status: PAUSED or ENABLED. Default PAUSED.
      bidding_strategy: MAXIMIZE_CONVERSION_VALUE (default), TARGET_ROAS,
        MAXIMIZE_CONVERSIONS, TARGET_CPA, or MANUAL_CPC.
      target_roas: Target ROAS ratio, e.g. 4.0 (for TARGET_ROAS).
      target_cpa_micros: Target CPA in micros (for TARGET_CPA).
      login_customer_id: MCC account ID if customer is managed.

  Returns:
      Dict of created resource names keyed by result type.
  """
  customer_id, login_customer_id = validate_accounts(
      customer_id, login_customer_id
  )
  operations, _ = builders.build_shopping_campaign(
      customer_id,
      name=name,
      budget_micros=budget_micros,
      merchant_id=merchant_id,
      feed_label=feed_label,
      campaign_priority=campaign_priority,
      status=status,
      bidding_strategy=bidding_strategy,
      target_roas=target_roas,
      target_cpa_micros=target_cpa_micros,
  )
  return _execute(login_customer_id, customer_id, operations)


@mcp.tool()
def create_demand_gen_campaign(
    customer_id: str,
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
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Creates a Demand Gen campaign + ad group + multi-asset ad atomically.

  Demand Gen requires a conversion-based bidding strategy. Image assets must be
  created first with create_image_asset.

  Args:
      customer_id: Google Ads customer ID (digits only).
      name: Campaign name.
      budget_micros: Daily budget in micros (1,000,000 = 1 currency unit).
      final_url: Landing page URL for the ad.
      headlines: Headline strings (max 40 chars each).
      descriptions: Description strings (max 90 chars each).
      business_name: Advertiser/business name shown in the ad.
      marketing_image_assets: Landscape (1.91:1) image asset resource names.
      square_marketing_image_assets: Square (1:1) image asset resource names.
      logo_image_assets: Logo (1:1) image asset resource names.
      status: PAUSED or ENABLED. Default PAUSED.
      bidding_strategy: MAXIMIZE_CONVERSIONS (default),
        MAXIMIZE_CONVERSION_VALUE, TARGET_CPA, or TARGET_ROAS.
      target_cpa_micros: Target CPA in micros (for TARGET_CPA / optional with
        MAXIMIZE_CONVERSIONS).
      target_roas: Target ROAS ratio, e.g. 4.0 (for TARGET_ROAS / optional with
        MAXIMIZE_CONVERSION_VALUE).
      login_customer_id: MCC account ID if customer is managed.

  Returns:
      Dict of created resource names keyed by result type.
  """
  customer_id, login_customer_id = validate_accounts(
      customer_id, login_customer_id
  )
  operations, _ = builders.build_demand_gen_campaign(
      customer_id,
      name=name,
      budget_micros=budget_micros,
      final_url=final_url,
      headlines=headlines,
      descriptions=descriptions,
      business_name=business_name,
      marketing_image_assets=marketing_image_assets,
      square_marketing_image_assets=square_marketing_image_assets,
      logo_image_assets=logo_image_assets,
      status=status,
      bidding_strategy=bidding_strategy,
      target_cpa_micros=target_cpa_micros,
      target_roas=target_roas,
  )
  return _execute(login_customer_id, customer_id, operations)


@mcp.tool()
def create_video_campaign(
    customer_id: str,
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
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Creates a Video (YouTube) campaign + ad group + responsive video ad.

  YouTube video assets must be created first with create_youtube_video_asset.

  Args:
      customer_id: Google Ads customer ID (digits only).
      name: Campaign name.
      budget_micros: Daily budget in micros (1,000,000 = 1 currency unit).
      final_url: Landing page URL for the ad.
      video_assets: YouTube video asset resource names. At least one required.
      headlines: Short headline strings.
      long_headlines: Long headline strings.
      descriptions: Description strings.
      business_name: Advertiser/business name shown in the ad.
      status: PAUSED or ENABLED. Default PAUSED.
      bidding_strategy: MAXIMIZE_CONVERSIONS (default), TARGET_CPA, TARGET_CPM,
        MAXIMIZE_CONVERSION_VALUE, or TARGET_ROAS.
      target_cpa_micros: Target CPA in micros (for TARGET_CPA / optional with
        MAXIMIZE_CONVERSIONS).
      target_roas: Target ROAS ratio (for TARGET_ROAS / optional with
        MAXIMIZE_CONVERSION_VALUE).
      login_customer_id: MCC account ID if customer is managed.

  Returns:
      Dict of created resource names keyed by result type.
  """
  customer_id, login_customer_id = validate_accounts(
      customer_id, login_customer_id
  )
  operations, _ = builders.build_video_campaign(
      customer_id,
      name=name,
      budget_micros=budget_micros,
      final_url=final_url,
      video_assets=video_assets,
      headlines=headlines,
      long_headlines=long_headlines,
      descriptions=descriptions,
      business_name=business_name,
      status=status,
      bidding_strategy=bidding_strategy,
      target_cpa_micros=target_cpa_micros,
      target_roas=target_roas,
  )
  return _execute(login_customer_id, customer_id, operations)


@mcp.tool()
def create_pmax_campaign(
    customer_id: str,
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
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Creates a Performance Max campaign with one asset group atomically.

  Performance Max has no ad groups, keywords, or ads. Pass a merchant_id to
  create a retail PMax campaign (adds an "all products" listing group). Image
  and video assets must be created first with create_image_asset /
  create_youtube_video_asset; text assets are created inline.

  Args:
      customer_id: Google Ads customer ID (digits only).
      name: Campaign name.
      budget_micros: Daily budget in micros (1,000,000 = 1 currency unit).
      final_url: Landing page URL for the asset group.
      headlines: At least 3 headline strings (max 30 chars each).
      long_headlines: At least 1 long headline (max 90 chars).
      descriptions: At least 2 description strings (max 90 chars each).
      business_name: Advertiser/business name.
      marketing_image_assets: Landscape (1.91:1) image asset resource names.
      square_marketing_image_assets: Square (1:1) image asset resource names.
      logo_image_assets: Logo (1:1) image asset resource names.
      youtube_video_assets: Optional YouTube video asset resource names.
      merchant_id: Optional Merchant Center ID for retail PMax.
      feed_label: Feed label for retail PMax (e.g. "US"). Optional.
      status: PAUSED or ENABLED. Default PAUSED.
      bidding_strategy: Conversion-based only: MAXIMIZE_CONVERSIONS (default),
        MAXIMIZE_CONVERSION_VALUE, TARGET_CPA, or TARGET_ROAS.
      target_cpa_micros: Target CPA in micros (for TARGET_CPA / optional with
        MAXIMIZE_CONVERSIONS).
      target_roas: Target ROAS ratio (for TARGET_ROAS / optional with
        MAXIMIZE_CONVERSION_VALUE).
      login_customer_id: MCC account ID if customer is managed.

  Returns:
      Dict of created resource names keyed by result type.
  """
  customer_id, login_customer_id = validate_accounts(
      customer_id, login_customer_id
  )
  operations, _ = builders.build_pmax_campaign(
      customer_id,
      name=name,
      budget_micros=budget_micros,
      final_url=final_url,
      headlines=headlines,
      long_headlines=long_headlines,
      descriptions=descriptions,
      business_name=business_name,
      marketing_image_assets=marketing_image_assets,
      square_marketing_image_assets=square_marketing_image_assets,
      logo_image_assets=logo_image_assets,
      youtube_video_assets=youtube_video_assets,
      merchant_id=merchant_id,
      feed_label=feed_label,
      status=status,
      bidding_strategy=bidding_strategy,
      target_cpa_micros=target_cpa_micros,
      target_roas=target_roas,
  )
  return _execute(login_customer_id, customer_id, operations)
