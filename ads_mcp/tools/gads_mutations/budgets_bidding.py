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

"""Budgets & bidding mutations (spec §6) — approval-gated, the money levers.

  gads_create_budget            gads_update_budget
  gads_update_bidding_strategy

Amounts are in micros (1,000,000 micros = 1 currency unit). All stage through
the approval workflow and accept validate_only.
"""

from __future__ import annotations

from typing import Any

from ads_mcp.coordinator import mcp_server as mcp
from ads_mcp.tools._ads_api import enum_types
from ads_mcp.tools._ads_api import resource_types
from ads_mcp.tools._ads_api import service_types
from ads_mcp.tools.gads_mutations._common import ANN_CREATE
from ads_mcp.tools.gads_mutations._common import ANN_UPDATE
from ads_mcp.tools.gads_mutations._common import build_request
from ads_mcp.tools.gads_mutations._common import require_digits
from ads_mcp.tools.gads_mutations._common import single_result
from ads_mcp.tools.gads_mutations._common import _get_client
from ads_mcp.tools.gads_mutations._common import _handle_google_ads_error
from ads_mcp.tools.gads_mutations._common import _resolve_enum
from ads_mcp.tools.mutations.approval import propose
from fastmcp.exceptions import ToolError
from google.ads.googleads.errors import GoogleAdsException
from google.protobuf import field_mask_pb2


@mcp.tool(name="gads_create_budget", annotations=ANN_CREATE)
def gads_create_budget(
    customer_id: str,
    name: str,
    amount_micros: int,
    delivery_method: str = "STANDARD",
    validate_only: bool = False,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Stages creation of a campaign budget. Requires approval.

  Args:
    customer_id: Google Ads customer ID (digits only).
    name: Budget name.
    amount_micros: Daily amount in micros (1,000,000 micros = 1 unit; e.g.
      EUR 10/day = 10000000).
    delivery_method: STANDARD (default) or ACCELERATED.
    validate_only: If True, the approved change runs as a dry-run.
    login_customer_id: Manager (MCC) ID if the account is managed.

  Returns:
    Pending change record. On approval, returns the budget resource_name to
    pass to gads_create_campaign.
  """
  cid = require_digits(customer_id, "customer_id")
  if int(amount_micros) <= 0:
    raise ToolError("amount_micros must be a positive integer (micros).")
  params = dict(
      customer_id=cid, name=name, amount_micros=int(amount_micros),
      delivery_method=delivery_method, validate_only=validate_only,
      login_customer_id=login_customer_id,
  )

  def executor():
    client = _get_client(login_customer_id)
    service = client.get_service("CampaignBudgetService")
    budget = resource_types.CampaignBudget(
        name=name,
        amount_micros=int(amount_micros),
        delivery_method=_resolve_enum(
            enum_types.BudgetDeliveryMethodEnum.BudgetDeliveryMethod,
            delivery_method, "delivery_method",
        ),
    )
    operation = service_types.CampaignBudgetOperation(create=budget)
    try:
      response = service.mutate_campaign_budgets(
          request=build_request(
              client, "MutateCampaignBudgetsRequest", cid, [operation],
              validate_only,
          )
      )
    except GoogleAdsException as e:
      _handle_google_ads_error(e)
    return single_result(response, validate_only)

  summary = (
      f"Create budget '{name}' = {int(amount_micros) / 1_000_000:.2f}/day "
      f"({delivery_method}) for customer {cid}"
      + (" [validate_only]" if validate_only else "")
  )
  return propose("gads_create_budget", cid, summary, params, executor)


@mcp.tool(name="gads_update_budget", annotations=ANN_UPDATE)
def gads_update_budget(
    customer_id: str,
    budget_id: str,
    amount_micros: int,
    validate_only: bool = False,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Stages a change to a budget's daily amount. Requires approval.

  Args:
    customer_id: Google Ads customer ID (digits only).
    budget_id: Campaign budget ID (digits only).
    amount_micros: New daily amount in micros.
    validate_only: If True, the approved change runs as a dry-run.
    login_customer_id: Manager (MCC) ID if the account is managed.

  Returns:
    Pending change record.
  """
  cid = require_digits(customer_id, "customer_id")
  bid = require_digits(budget_id, "budget_id")
  if int(amount_micros) <= 0:
    raise ToolError("amount_micros must be a positive integer (micros).")
  params = dict(
      customer_id=cid, budget_id=bid, amount_micros=int(amount_micros),
      validate_only=validate_only, login_customer_id=login_customer_id,
  )

  def executor():
    client = _get_client(login_customer_id)
    service = client.get_service("CampaignBudgetService")
    budget = resource_types.CampaignBudget(
        resource_name=service.campaign_budget_path(cid, bid),
        amount_micros=int(amount_micros),
    )
    operation = service_types.CampaignBudgetOperation(update=budget)
    operation.update_mask.CopyFrom(
        field_mask_pb2.FieldMask(paths=["amount_micros"])
    )
    try:
      response = service.mutate_campaign_budgets(
          request=build_request(
              client, "MutateCampaignBudgetsRequest", cid, [operation],
              validate_only,
          )
      )
    except GoogleAdsException as e:
      _handle_google_ads_error(e)
    return single_result(response, validate_only)

  summary = (
      f"Update budget {bid} -> {int(amount_micros) / 1_000_000:.2f}/day "
      f"(customer {cid})" + (" [validate_only]" if validate_only else "")
  )
  return propose("gads_update_budget", cid, summary, params, executor)


@mcp.tool(name="gads_update_bidding_strategy", annotations=ANN_UPDATE)
def gads_update_bidding_strategy(
    customer_id: str,
    campaign_id: str,
    strategy: str,
    target: float | None = None,
    validate_only: bool = False,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Stages a campaign bidding-strategy change. Requires approval.

  Args:
    customer_id: Google Ads customer ID (digits only).
    campaign_id: Campaign ID (digits only).
    strategy: One of MANUAL_CPC, MAXIMIZE_CONVERSIONS,
      MAXIMIZE_CONVERSION_VALUE, TARGET_CPA, TARGET_ROAS, TARGET_SPEND.
    target: Strategy target where applicable — for TARGET_CPA and
      MAXIMIZE_CONVERSIONS this is target CPA in micros (int); for TARGET_ROAS
      and MAXIMIZE_CONVERSION_VALUE this is the target ROAS ratio (e.g. 4.0).
      Ignored for MANUAL_CPC / TARGET_SPEND.
    validate_only: If True, the approved change runs as a dry-run.
    login_customer_id: Manager (MCC) ID if the account is managed.

  Returns:
    Pending change record.
  """
  cid = require_digits(customer_id, "customer_id")
  campid = require_digits(campaign_id, "campaign_id")
  strat = strategy.upper()
  valid = {
      "MANUAL_CPC", "MAXIMIZE_CONVERSIONS", "MAXIMIZE_CONVERSION_VALUE",
      "TARGET_CPA", "TARGET_ROAS", "TARGET_SPEND",
  }
  if strat not in valid:
    raise ToolError(
        f"Invalid strategy {strategy!r}. Valid: {', '.join(sorted(valid))}."
    )
  if strat in ("TARGET_CPA", "TARGET_ROAS") and target is None:
    raise ToolError(f"{strat} requires a target value.")
  params = dict(
      customer_id=cid, campaign_id=campid, strategy=strat, target=target,
      validate_only=validate_only, login_customer_id=login_customer_id,
  )

  def executor():
    client = _get_client(login_customer_id)
    service = client.get_service("CampaignService")
    # Build the bidding fields first, WITHOUT resource_name, so the computed
    # field mask contains only the bidding leaves (e.g.
    # "target_cpa.target_cpa_micros") and not resource_name.
    # The Google Ads API requires a LEAF path in the update mask to switch a
    # campaign's standard bidding strategy — masking the bare scheme message
    # (e.g. "target_cpa") is rejected with FIELD_HAS_SUBFIELDS. So each branch
    # sets one concrete leaf (using a neutral 0 / False when no target is
    # given) and masks exactly that leaf.
    campaign = resource_types.Campaign()
    if strat == "MANUAL_CPC":
      campaign.manual_cpc.enhanced_cpc_enabled = False
      paths = ["manual_cpc.enhanced_cpc_enabled"]
    elif strat == "TARGET_SPEND":
      if target is not None:
        campaign.target_spend.cpc_bid_ceiling_micros = int(target)
        paths = ["target_spend.cpc_bid_ceiling_micros"]
      else:
        campaign.target_spend.target_spend_micros = 0
        paths = ["target_spend.target_spend_micros"]
    elif strat == "MAXIMIZE_CONVERSIONS":
      campaign.maximize_conversions.target_cpa_micros = (
          int(target) if target is not None else 0
      )
      paths = ["maximize_conversions.target_cpa_micros"]
    elif strat == "MAXIMIZE_CONVERSION_VALUE":
      campaign.maximize_conversion_value.target_roas = (
          float(target) if target is not None else 0.0
      )
      paths = ["maximize_conversion_value.target_roas"]
    elif strat == "TARGET_CPA":
      campaign.target_cpa.target_cpa_micros = int(target)
      paths = ["target_cpa.target_cpa_micros"]
    else:  # TARGET_ROAS
      campaign.target_roas.target_roas = float(target)
      paths = ["target_roas.target_roas"]

    campaign.resource_name = service.campaign_path(cid, campid)
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

  tgt = f", target={target}" if target is not None else ""
  summary = (
      f"Set campaign {campid} bidding -> {strat}{tgt} (customer {cid})"
      + (" [validate_only]" if validate_only else "")
  )
  return propose(
      "gads_update_bidding_strategy", cid, summary, params, executor
  )
