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

"""Campaign structure mutations (spec §3) — approval-gated.

  gads_create_campaign      gads_create_ad_group
  gads_update_campaign      gads_update_ad_group
  gads_set_campaign_status  gads_set_ad_group_status

All create new entities PAUSED, accept validate_only, and stage through the
approval workflow (call approve_change to execute).
"""

from __future__ import annotations

from typing import Any

from ads_mcp.coordinator import mcp_server as mcp
from ads_mcp.tools._ads_api import common_types
from ads_mcp.tools._ads_api import enum_types
from ads_mcp.tools._ads_api import resource_types
from ads_mcp.tools._ads_api import service_types
from ads_mcp.tools.gads_mutations._common import ANN_CREATE
from ads_mcp.tools.gads_mutations._common import ANN_STATUS
from ads_mcp.tools.gads_mutations._common import ANN_UPDATE
from ads_mcp.tools.gads_mutations._common import build_request
from ads_mcp.tools.gads_mutations._common import normalize_date
from ads_mcp.tools.gads_mutations._common import require_digits
from ads_mcp.tools.gads_mutations._common import single_result
from ads_mcp.tools.gads_mutations._common import _get_client
from ads_mcp.tools.gads_mutations._common import _handle_google_ads_error
from ads_mcp.tools.gads_mutations._common import _resolve_enum
from ads_mcp.tools.mutations.approval import propose
from fastmcp.exceptions import ToolError
from google.ads.googleads.errors import GoogleAdsException
from google.protobuf import field_mask_pb2

# Bidding strategies that need no target value (valid at campaign create time).
_SIMPLE_BIDDING = {
    "MANUAL_CPC": lambda: common_types.ManualCpc(),
    "MAXIMIZE_CONVERSIONS": lambda: common_types.MaximizeConversions(),
    "MAXIMIZE_CONVERSION_VALUE": lambda: common_types.MaximizeConversionValue(),
    "TARGET_SPEND": lambda: common_types.TargetSpend(),
}


def _apply_simple_bidding(campaign, strategy: str) -> None:
  key = strategy.upper()
  factory = _SIMPLE_BIDDING.get(key)
  if not factory:
    raise ToolError(
        f"Unsupported bidding_strategy {strategy!r} for create. Valid: "
        f"{', '.join(_SIMPLE_BIDDING)}. Use gads_update_bidding_strategy for "
        "target-based strategies (TARGET_CPA, TARGET_ROAS)."
    )
  if key == "MANUAL_CPC":
    campaign.manual_cpc = factory()
  elif key == "MAXIMIZE_CONVERSIONS":
    campaign.maximize_conversions = factory()
  elif key == "MAXIMIZE_CONVERSION_VALUE":
    campaign.maximize_conversion_value = factory()
  elif key == "TARGET_SPEND":
    campaign.target_spend = factory()


# ---------------------------------------------------------------------------
# Campaigns
# ---------------------------------------------------------------------------

@mcp.tool(name="gads_create_campaign", annotations=ANN_CREATE)
def gads_create_campaign(
    customer_id: str,
    name: str,
    channel_type: str,
    budget_id: str,
    bidding_strategy: str = "MANUAL_CPC",
    start_date: str | None = None,
    end_date: str | None = None,
    validate_only: bool = False,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Stages creation of a campaign (created PAUSED). Requires approval.

  Args:
    customer_id: Google Ads customer ID (digits only).
    name: Campaign name.
    channel_type: SEARCH, DISPLAY, SHOPPING, VIDEO, etc.
    budget_id: ID of an existing campaign budget (see gads_create_budget).
    bidding_strategy: One of MANUAL_CPC (default), MAXIMIZE_CONVERSIONS,
      MAXIMIZE_CONVERSION_VALUE, TARGET_SPEND.
    start_date: Optional YYYY-MM-DD start date.
    end_date: Optional YYYY-MM-DD end date.
    validate_only: If True, the approved change runs as a Google Ads API
      dry-run (validateOnly) without creating anything.
    login_customer_id: Manager (MCC) ID if the account is managed.

  Returns:
    Pending change record (change_id, summary, approval instructions).
  """
  cid = require_digits(customer_id, "customer_id")
  bid = require_digits(budget_id, "budget_id")
  start = normalize_date(start_date, "start_date")
  end = normalize_date(end_date, "end_date")
  params = dict(
      customer_id=cid, name=name, channel_type=channel_type, budget_id=bid,
      bidding_strategy=bidding_strategy, start_date=start_date,
      end_date=end_date, validate_only=validate_only,
      login_customer_id=login_customer_id,
  )

  def executor():
    client = _get_client(login_customer_id)
    service = client.get_service("CampaignService")
    budget_rn = service.campaign_budget_path(cid, bid)
    eu = enum_types.EuPoliticalAdvertisingStatusEnum.EuPoliticalAdvertisingStatus
    campaign = resource_types.Campaign(
        name=name,
        campaign_budget=budget_rn,
        status=enum_types.CampaignStatusEnum.CampaignStatus.PAUSED,
        advertising_channel_type=_resolve_enum(
            enum_types.AdvertisingChannelTypeEnum.AdvertisingChannelType,
            channel_type, "channel_type",
        ),
        contains_eu_political_advertising=(
            eu.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING
        ),
    )
    _apply_simple_bidding(campaign, bidding_strategy)
    if start:
      campaign.start_date = start
    if end:
      campaign.end_date = end
    operation = service_types.CampaignOperation(create=campaign)
    try:
      response = service.mutate_campaigns(
          request=build_request(
              client, "MutateCampaignsRequest", cid, [operation], validate_only
          )
      )
    except GoogleAdsException as e:
      _handle_google_ads_error(e)
    return single_result(response, validate_only)

  summary = (
      f"Create {channel_type} campaign '{name}' (PAUSED) for customer {cid}, "
      f"budget_id={bid}, bidding={bidding_strategy}"
      + (" [validate_only]" if validate_only else "")
  )
  return propose("gads_create_campaign", cid, summary, params, executor)


@mcp.tool(name="gads_update_campaign", annotations=ANN_UPDATE)
def gads_update_campaign(
    customer_id: str,
    campaign_id: str,
    name: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    validate_only: bool = False,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Stages an update to a campaign's name and/or dates. Requires approval.

  (Status changes use gads_set_campaign_status; bidding uses
  gads_update_bidding_strategy.)

  Args:
    customer_id: Google Ads customer ID (digits only).
    campaign_id: Campaign ID to update (digits only).
    name: New campaign name (optional).
    start_date: New YYYY-MM-DD start date (optional).
    end_date: New YYYY-MM-DD end date (optional).
    validate_only: If True, the approved change runs as a dry-run.
    login_customer_id: Manager (MCC) ID if the account is managed.

  Returns:
    Pending change record.
  """
  cid = require_digits(customer_id, "customer_id")
  campid = require_digits(campaign_id, "campaign_id")
  start = normalize_date(start_date, "start_date")
  end = normalize_date(end_date, "end_date")
  if name is None and start is None and end is None:
    raise ToolError("Provide at least one of: name, start_date, end_date.")
  params = dict(
      customer_id=cid, campaign_id=campid, name=name, start_date=start_date,
      end_date=end_date, validate_only=validate_only,
      login_customer_id=login_customer_id,
  )

  def executor():
    client = _get_client(login_customer_id)
    service = client.get_service("CampaignService")
    campaign = resource_types.Campaign(
        resource_name=service.campaign_path(cid, campid)
    )
    paths = []
    if name is not None:
      campaign.name = name
      paths.append("name")
    if start is not None:
      campaign.start_date = start
      paths.append("start_date")
    if end is not None:
      campaign.end_date = end
      paths.append("end_date")
    operation = service_types.CampaignOperation(update=campaign)
    operation.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=paths))
    try:
      response = service.mutate_campaigns(
          request=build_request(
              client, "MutateCampaignsRequest", cid, [operation], validate_only
          )
      )
    except GoogleAdsException as e:
      _handle_google_ads_error(e)
    return single_result(response, validate_only)

  summary = (
      f"Update campaign {campid} (customer {cid}): "
      + ", ".join(
          f"{k}={v}" for k, v in
          [("name", name), ("start_date", start_date), ("end_date", end_date)]
          if v is not None
      )
      + (" [validate_only]" if validate_only else "")
  )
  return propose("gads_update_campaign", cid, summary, params, executor)


@mcp.tool(name="gads_set_campaign_status", annotations=ANN_STATUS)
def gads_set_campaign_status(
    customer_id: str,
    campaign_id: str,
    status: str,
    validate_only: bool = False,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Stages enabling, pausing, or removing a campaign. Requires approval.

  Args:
    customer_id: Google Ads customer ID (digits only).
    campaign_id: Campaign ID (digits only).
    status: ENABLED, PAUSED, or REMOVED. REMOVED is destructive.
    validate_only: If True, the approved change runs as a dry-run.
    login_customer_id: Manager (MCC) ID if the account is managed.

  Returns:
    Pending change record.
  """
  cid = require_digits(customer_id, "customer_id")
  campid = require_digits(campaign_id, "campaign_id")
  params = dict(
      customer_id=cid, campaign_id=campid, status=status,
      validate_only=validate_only, login_customer_id=login_customer_id,
  )

  def executor():
    client = _get_client(login_customer_id)
    service = client.get_service("CampaignService")
    campaign = resource_types.Campaign(
        resource_name=service.campaign_path(cid, campid),
        status=_resolve_enum(
            enum_types.CampaignStatusEnum.CampaignStatus, status, "status"
        ),
    )
    operation = service_types.CampaignOperation(update=campaign)
    operation.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["status"]))
    try:
      response = service.mutate_campaigns(
          request=build_request(
              client, "MutateCampaignsRequest", cid, [operation], validate_only
          )
      )
    except GoogleAdsException as e:
      _handle_google_ads_error(e)
    return single_result(response, validate_only)

  summary = (
      f"Set campaign {campid} status -> {status.upper()} (customer {cid})"
      + (" [validate_only]" if validate_only else "")
  )
  return propose("gads_set_campaign_status", cid, summary, params, executor)


# ---------------------------------------------------------------------------
# Ad groups
# ---------------------------------------------------------------------------

@mcp.tool(name="gads_create_ad_group", annotations=ANN_CREATE)
def gads_create_ad_group(
    customer_id: str,
    campaign_id: str,
    name: str,
    cpc_bid_micros: int | None = None,
    validate_only: bool = False,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Stages creation of an ad group (created PAUSED). Requires approval.

  Args:
    customer_id: Google Ads customer ID (digits only).
    campaign_id: Parent campaign ID (digits only).
    name: Ad group name.
    cpc_bid_micros: Optional max CPC bid in micros (1,000,000 = 1 unit).
    validate_only: If True, the approved change runs as a dry-run.
    login_customer_id: Manager (MCC) ID if the account is managed.

  Returns:
    Pending change record.
  """
  cid = require_digits(customer_id, "customer_id")
  campid = require_digits(campaign_id, "campaign_id")
  params = dict(
      customer_id=cid, campaign_id=campid, name=name,
      cpc_bid_micros=cpc_bid_micros, validate_only=validate_only,
      login_customer_id=login_customer_id,
  )

  def executor():
    client = _get_client(login_customer_id)
    service = client.get_service("AdGroupService")
    campaign_service = client.get_service("CampaignService")
    ad_group = resource_types.AdGroup(
        name=name,
        campaign=campaign_service.campaign_path(cid, campid),
        status=enum_types.AdGroupStatusEnum.AdGroupStatus.PAUSED,
        type_=enum_types.AdGroupTypeEnum.AdGroupType.SEARCH_STANDARD,
    )
    if cpc_bid_micros is not None:
      ad_group.cpc_bid_micros = cpc_bid_micros
    operation = service_types.AdGroupOperation(create=ad_group)
    try:
      response = service.mutate_ad_groups(
          request=build_request(
              client, "MutateAdGroupsRequest", cid, [operation], validate_only
          )
      )
    except GoogleAdsException as e:
      _handle_google_ads_error(e)
    return single_result(response, validate_only)

  summary = (
      f"Create ad group '{name}' (PAUSED) in campaign {campid} "
      f"(customer {cid})" + (" [validate_only]" if validate_only else "")
  )
  return propose("gads_create_ad_group", cid, summary, params, executor)


@mcp.tool(name="gads_update_ad_group", annotations=ANN_UPDATE)
def gads_update_ad_group(
    customer_id: str,
    ad_group_id: str,
    name: str | None = None,
    cpc_bid_micros: int | None = None,
    validate_only: bool = False,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Stages an update to an ad group's name and/or CPC bid. Requires approval.

  Args:
    customer_id: Google Ads customer ID (digits only).
    ad_group_id: Ad group ID to update (digits only).
    name: New ad group name (optional).
    cpc_bid_micros: New max CPC bid in micros (optional).
    validate_only: If True, the approved change runs as a dry-run.
    login_customer_id: Manager (MCC) ID if the account is managed.

  Returns:
    Pending change record.
  """
  cid = require_digits(customer_id, "customer_id")
  agid = require_digits(ad_group_id, "ad_group_id")
  if name is None and cpc_bid_micros is None:
    raise ToolError("Provide at least one of: name, cpc_bid_micros.")
  params = dict(
      customer_id=cid, ad_group_id=agid, name=name,
      cpc_bid_micros=cpc_bid_micros, validate_only=validate_only,
      login_customer_id=login_customer_id,
  )

  def executor():
    client = _get_client(login_customer_id)
    service = client.get_service("AdGroupService")
    ad_group = resource_types.AdGroup(
        resource_name=service.ad_group_path(cid, agid)
    )
    paths = []
    if name is not None:
      ad_group.name = name
      paths.append("name")
    if cpc_bid_micros is not None:
      ad_group.cpc_bid_micros = cpc_bid_micros
      paths.append("cpc_bid_micros")
    operation = service_types.AdGroupOperation(update=ad_group)
    operation.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=paths))
    try:
      response = service.mutate_ad_groups(
          request=build_request(
              client, "MutateAdGroupsRequest", cid, [operation], validate_only
          )
      )
    except GoogleAdsException as e:
      _handle_google_ads_error(e)
    return single_result(response, validate_only)

  summary = (
      f"Update ad group {agid} (customer {cid})"
      + (" [validate_only]" if validate_only else "")
  )
  return propose("gads_update_ad_group", cid, summary, params, executor)


@mcp.tool(name="gads_set_ad_group_status", annotations=ANN_STATUS)
def gads_set_ad_group_status(
    customer_id: str,
    ad_group_id: str,
    status: str,
    validate_only: bool = False,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Stages enabling, pausing, or removing an ad group. Requires approval.

  Args:
    customer_id: Google Ads customer ID (digits only).
    ad_group_id: Ad group ID (digits only).
    status: ENABLED, PAUSED, or REMOVED. REMOVED is destructive.
    validate_only: If True, the approved change runs as a dry-run.
    login_customer_id: Manager (MCC) ID if the account is managed.

  Returns:
    Pending change record.
  """
  cid = require_digits(customer_id, "customer_id")
  agid = require_digits(ad_group_id, "ad_group_id")
  params = dict(
      customer_id=cid, ad_group_id=agid, status=status,
      validate_only=validate_only, login_customer_id=login_customer_id,
  )

  def executor():
    client = _get_client(login_customer_id)
    service = client.get_service("AdGroupService")
    ad_group = resource_types.AdGroup(
        resource_name=service.ad_group_path(cid, agid),
        status=_resolve_enum(
            enum_types.AdGroupStatusEnum.AdGroupStatus, status, "status"
        ),
    )
    operation = service_types.AdGroupOperation(update=ad_group)
    operation.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["status"]))
    try:
      response = service.mutate_ad_groups(
          request=build_request(
              client, "MutateAdGroupsRequest", cid, [operation], validate_only
          )
      )
    except GoogleAdsException as e:
      _handle_google_ads_error(e)
    return single_result(response, validate_only)

  summary = (
      f"Set ad group {agid} status -> {status.upper()} (customer {cid})"
      + (" [validate_only]" if validate_only else "")
  )
  return propose("gads_set_ad_group_status", cid, summary, params, executor)
