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

"""Approval-gated builders for Display, Shopping, Demand Gen, Video, and
Performance Max campaigns.

Each propose_* tool validates and assembles the campaign's atomic operation
list immediately (so input errors surface at once), then stages it as a single
pending change. Nothing reaches the Google Ads API until approve_change() runs
the staged executor. The operations are built by mutations/builders.py, the
same code path the direct-execute tools use.
"""

from __future__ import annotations

from typing import Any

from ads_mcp.coordinator import mcp_server as mcp
from ads_mcp.guardrails import validate_accounts
from ads_mcp.tools.mutations import builders
from ads_mcp.tools.mutations.approval import propose
from ads_mcp.tools.mutations.common import _get_client
from ads_mcp.tools.mutations.common import _handle_google_ads_error
from google.ads.googleads.errors import GoogleAdsException


def _stage(
    tool_name: str,
    customer_id: str,
    login_customer_id: str | None,
    operations: list[Any],
    summary: str,
    params: dict[str, Any],
) -> dict[str, Any]:
  """Wrap a prebuilt operation list in an executor and stage it for approval."""

  def executor():
    ads_client = _get_client(login_customer_id)
    try:
      return builders.execute_mutate(ads_client, customer_id, operations)
    except GoogleAdsException as e:
      _handle_google_ads_error(e)

  return propose(tool_name, customer_id, summary, params, executor)


@mcp.tool()
def propose_create_display_campaign(
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
  """Stages a Display campaign for approval (see create_display_campaign).

  Builds the campaign + ad group + responsive display ad as one atomic change.
  Call approve_change(change_id) to execute. Image assets must be created first
  with create_image_asset.
  """
  customer_id, login_customer_id = validate_accounts(
      customer_id, login_customer_id
  )
  operations, summary = builders.build_display_campaign(
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
  params = dict(
      customer_id=customer_id, name=name, budget_micros=budget_micros
  )
  return _stage(
      "create_display_campaign",
      customer_id,
      login_customer_id,
      operations,
      summary,
      params,
  )


@mcp.tool()
def propose_create_shopping_campaign(
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
  """Stages a Shopping campaign for approval (see create_shopping_campaign).

  Requires a Merchant Center account already linked to the Google Ads account.
  Call approve_change(change_id) to execute.
  """
  customer_id, login_customer_id = validate_accounts(
      customer_id, login_customer_id
  )
  operations, summary = builders.build_shopping_campaign(
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
  params = dict(
      customer_id=customer_id,
      name=name,
      budget_micros=budget_micros,
      merchant_id=merchant_id,
  )
  return _stage(
      "create_shopping_campaign",
      customer_id,
      login_customer_id,
      operations,
      summary,
      params,
  )


@mcp.tool()
def propose_create_demand_gen_campaign(
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
  """Stages a Demand Gen campaign for approval (see create_demand_gen_campaign).

  Requires a conversion-based bidding strategy. Image assets must be created
  first with create_image_asset. Call approve_change(change_id) to execute.
  """
  customer_id, login_customer_id = validate_accounts(
      customer_id, login_customer_id
  )
  operations, summary = builders.build_demand_gen_campaign(
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
  params = dict(
      customer_id=customer_id, name=name, budget_micros=budget_micros
  )
  return _stage(
      "create_demand_gen_campaign",
      customer_id,
      login_customer_id,
      operations,
      summary,
      params,
  )


@mcp.tool()
def propose_create_video_campaign(
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
  """Stages a Video campaign for approval (see create_video_campaign).

  YouTube video assets must be created first with create_youtube_video_asset.
  Call approve_change(change_id) to execute.
  """
  customer_id, login_customer_id = validate_accounts(
      customer_id, login_customer_id
  )
  operations, summary = builders.build_video_campaign(
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
  params = dict(
      customer_id=customer_id, name=name, budget_micros=budget_micros
  )
  return _stage(
      "create_video_campaign",
      customer_id,
      login_customer_id,
      operations,
      summary,
      params,
  )


@mcp.tool()
def propose_create_pmax_campaign(
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
  """Stages a Performance Max campaign for approval (see create_pmax_campaign).

  Pass a merchant_id for retail PMax. Image/video assets must be created first;
  text assets are created inline. Call approve_change(change_id) to execute.
  """
  customer_id, login_customer_id = validate_accounts(
      customer_id, login_customer_id
  )
  operations, summary = builders.build_pmax_campaign(
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
  params = dict(
      customer_id=customer_id, name=name, budget_micros=budget_micros
  )
  return _stage(
      "create_pmax_campaign",
      customer_id,
      login_customer_id,
      operations,
      summary,
      params,
  )
