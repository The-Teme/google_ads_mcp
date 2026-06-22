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

"""Approval-gated campaign mutation tools.

These tools replace the direct-execute versions in mutations/campaign.py.
They call propose() which stages the change and returns a change_id;
nothing hits the Google Ads API until approve_change(change_id) is called.
"""

from __future__ import annotations

from typing import Any

from ads_mcp.coordinator import mcp_server as mcp
from ads_mcp.guardrails import check_budget_micros
from ads_mcp.guardrails import validate_accounts
from ads_mcp.tools._ads_api import common_types
from ads_mcp.tools._ads_api import enum_types
from ads_mcp.tools._ads_api import resource_types
from ads_mcp.tools._ads_api import service_types
from ads_mcp.tools.mutations.approval import propose
from ads_mcp.tools.mutations.common import _get_client
from ads_mcp.tools.mutations.common import _handle_google_ads_error
from ads_mcp.tools.mutations.common import _resolve_enum
from fastmcp.exceptions import ToolError
from google.ads.googleads.errors import GoogleAdsException
from google.protobuf import field_mask_pb2


@mcp.tool()
def propose_create_search_campaign(
    customer_id: str,
    name: str,
    budget_resource_name: str,
    status: str = "PAUSED",
    target_google_search: bool = True,
    target_search_network: bool = False,
    target_content_network: bool = False,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Stages a request to create a Search campaign (requires approval).

  The campaign is NOT created immediately. A pending change is returned;
  call approve_change(change_id) to execute it.

  Args:
    customer_id: Google Ads customer ID (digits only).
    name: Campaign name.
    budget_resource_name: Resource name from create_campaign_budget.
    status: PAUSED or ENABLED. Default PAUSED.
    target_google_search: Show on Google Search. Default True.
    target_search_network: Show on search partners. Default False.
    target_content_network: Show on Display Network. Default False.
    login_customer_id: MCC account ID if customer is managed.

  Returns:
    Pending change record with change_id, summary, and approval instructions.
  """
  customer_id, login_customer_id = validate_accounts(
      customer_id, login_customer_id
  )
  params = dict(
      customer_id=customer_id,
      name=name,
      budget_resource_name=budget_resource_name,
      status=status,
      target_google_search=target_google_search,
      target_search_network=target_search_network,
      target_content_network=target_content_network,
      login_customer_id=login_customer_id,
  )

  def executor():
    ads_client = _get_client(login_customer_id)
    service = ads_client.get_service("CampaignService")

    eu_political_enum = (
        enum_types.EuPoliticalAdvertisingStatusEnum.EuPoliticalAdvertisingStatus
    )
    eu_status = eu_political_enum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING
    campaign = resource_types.Campaign(
        name=name,
        campaign_budget=budget_resource_name,
        status=_resolve_enum(
            enum_types.CampaignStatusEnum.CampaignStatus, status, "status"
        ),
        advertising_channel_type=(
            enum_types.AdvertisingChannelTypeEnum.AdvertisingChannelType.SEARCH
        ),
        target_spend=common_types.TargetSpend(),
        contains_eu_political_advertising=eu_status,
    )
    campaign.network_settings.target_google_search = target_google_search
    campaign.network_settings.target_search_network = target_search_network
    campaign.network_settings.target_content_network = target_content_network
    campaign.network_settings.target_partner_search_network = False

    operation = service_types.CampaignOperation(create=campaign)
    try:
      response = service.mutate_campaigns(
          customer_id=customer_id, operations=[operation]
      )
    except GoogleAdsException as e:
      _handle_google_ads_error(e)

    return {"resource_name": response.results[0].resource_name}

  summary = (
      f"Create Search campaign '{name}' for customer {customer_id} "
      f"with status={status}, budget={budget_resource_name}"
  )
  return propose("create_search_campaign", customer_id, summary, params, executor)


@mcp.tool()
def propose_update_campaign_status(
    customer_id: str,
    campaign_resource_name: str,
    status: str,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Stages a request to update a campaign's status (requires approval).

  Args:
    customer_id: Google Ads customer ID (digits only).
    campaign_resource_name: Full resource name of the campaign.
    status: New status: ENABLED or PAUSED.
    login_customer_id: MCC account ID if customer is managed.

  Returns:
    Pending change record with change_id, summary, and approval instructions.
  """
  customer_id, login_customer_id = validate_accounts(
      customer_id, login_customer_id
  )
  params = dict(
      customer_id=customer_id,
      campaign_resource_name=campaign_resource_name,
      status=status,
      login_customer_id=login_customer_id,
  )

  def executor():
    ads_client = _get_client(login_customer_id)
    service = ads_client.get_service("CampaignService")
    campaign = resource_types.Campaign(
        resource_name=campaign_resource_name,
        status=_resolve_enum(
            enum_types.CampaignStatusEnum.CampaignStatus, status, "status"
        ),
    )
    operation = service_types.CampaignOperation(update=campaign)
    operation.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["status"]))
    try:
      response = service.mutate_campaigns(
          customer_id=customer_id, operations=[operation]
      )
    except GoogleAdsException as e:
      _handle_google_ads_error(e)
    return {"resource_name": response.results[0].resource_name}

  summary = (
      f"Update campaign {campaign_resource_name} status → {status} "
      f"(customer {customer_id})"
  )
  return propose("update_campaign_status", customer_id, summary, params, executor)


@mcp.tool()
def propose_update_campaign_budget(
    customer_id: str,
    budget_resource_name: str,
    amount_micros: int,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Stages a request to update a campaign budget's daily amount (requires approval).

  Args:
    customer_id: Google Ads customer ID (digits only).
    budget_resource_name: Full resource name of the CampaignBudget.
    amount_micros: New daily budget in micros (1,000,000 micros = 1 currency unit).
    login_customer_id: MCC account ID if customer is managed.

  Returns:
    Pending change record.
  """
  customer_id, login_customer_id = validate_accounts(
      customer_id, login_customer_id
  )
  check_budget_micros(amount_micros)
  params = dict(
      customer_id=customer_id,
      budget_resource_name=budget_resource_name,
      amount_micros=amount_micros,
      login_customer_id=login_customer_id,
  )

  def executor():
    ads_client = _get_client(login_customer_id)
    service = ads_client.get_service("CampaignBudgetService")
    budget = ads_client.get_type("CampaignBudget")
    budget.resource_name = budget_resource_name
    budget.amount_micros = amount_micros
    operation = ads_client.get_type("CampaignBudgetOperation")
    operation.update.CopyFrom(budget)
    operation.update_mask.CopyFrom(
        field_mask_pb2.FieldMask(paths=["amount_micros"])
    )
    try:
      response = service.mutate_campaign_budgets(
          customer_id=customer_id, operations=[operation]
      )
    except GoogleAdsException as e:
      _handle_google_ads_error(e)
    return {"resource_name": response.results[0].resource_name}

  amount_display = amount_micros / 1_000_000
  summary = (
      f"Update budget {budget_resource_name} → {amount_display:.2f}/day "
      f"(customer {customer_id})"
  )
  return propose("update_campaign_budget", customer_id, summary, params, executor)


@mcp.tool()
def propose_update_ad_group_status(
    customer_id: str,
    ad_group_resource_name: str,
    status: str,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Stages a request to update an ad group's status (requires approval).

  Args:
    customer_id: Google Ads customer ID (digits only).
    ad_group_resource_name: Full resource name of the ad group.
    status: New status: ENABLED, PAUSED, or REMOVED.
    login_customer_id: MCC account ID if customer is managed.

  Returns:
    Pending change record.
  """
  customer_id, login_customer_id = validate_accounts(
      customer_id, login_customer_id
  )
  params = dict(
      customer_id=customer_id,
      ad_group_resource_name=ad_group_resource_name,
      status=status,
      login_customer_id=login_customer_id,
  )

  def executor():
    ads_client = _get_client(login_customer_id)
    service = ads_client.get_service("AdGroupService")
    ad_group = ads_client.get_type("AdGroup")
    ad_group.resource_name = ad_group_resource_name
    ad_group.status = _resolve_enum(
        enum_types.AdGroupStatusEnum.AdGroupStatus, status, "status"
    )
    operation = ads_client.get_type("AdGroupOperation")
    operation.update.CopyFrom(ad_group)
    operation.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["status"]))
    try:
      response = service.mutate_ad_groups(
          customer_id=customer_id, operations=[operation]
      )
    except GoogleAdsException as e:
      _handle_google_ads_error(e)
    return {"resource_name": response.results[0].resource_name}

  summary = (
      f"Update ad group {ad_group_resource_name} status → {status} "
      f"(customer {customer_id})"
  )
  return propose("update_ad_group_status", customer_id, summary, params, executor)


@mcp.tool()
def propose_add_negative_keyword(
    customer_id: str,
    ad_group_resource_name: str,
    keyword_text: str,
    match_type: str = "EXACT",
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Stages adding a negative keyword to an ad group (requires approval).

  Args:
    customer_id: Google Ads customer ID (digits only).
    ad_group_resource_name: Full resource name of the ad group.
    keyword_text: The keyword text to add as a negative.
    match_type: EXACT, PHRASE, or BROAD. Default EXACT.
    login_customer_id: MCC account ID if customer is managed.

  Returns:
    Pending change record.
  """
  customer_id, login_customer_id = validate_accounts(
      customer_id, login_customer_id
  )
  params = dict(
      customer_id=customer_id,
      ad_group_resource_name=ad_group_resource_name,
      keyword_text=keyword_text,
      match_type=match_type,
      login_customer_id=login_customer_id,
  )

  def executor():
    ads_client = _get_client(login_customer_id)
    service = ads_client.get_service("AdGroupCriterionService")
    criterion = ads_client.get_type("AdGroupCriterion")
    criterion.ad_group = ad_group_resource_name
    criterion.negative = True
    criterion.keyword.text = keyword_text
    criterion.keyword.match_type = _resolve_enum(
        enum_types.KeywordMatchTypeEnum.KeywordMatchType, match_type, "match_type"
    )
    operation = ads_client.get_type("AdGroupCriterionOperation")
    operation.create.CopyFrom(criterion)
    try:
      response = service.mutate_ad_group_criteria(
          customer_id=customer_id, operations=[operation]
      )
    except GoogleAdsException as e:
      _handle_google_ads_error(e)
    return {"resource_name": response.results[0].resource_name}

  summary = (
      f"Add negative keyword [{match_type}] '{keyword_text}' "
      f"to ad group {ad_group_resource_name} (customer {customer_id})"
  )
  return propose("add_negative_keyword", customer_id, summary, params, executor)
