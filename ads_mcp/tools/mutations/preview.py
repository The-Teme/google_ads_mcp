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

"""Change preview (diff) tools for Google Ads mutations.

Each tool in this module fetches the *current* state of a resource via GAQL
and returns a {before, after, summary} dict without writing anything to the
Google Ads API. Use these before calling the corresponding propose_* tool so
you can review what will actually change.
"""

from __future__ import annotations

from typing import Any

from ads_mcp.coordinator import mcp_server as mcp
from ads_mcp.tools._utils import get_ads_client
from ads_mcp.tools.mutations.common import _get_client
from fastmcp.exceptions import ToolError
from google.ads.googleads.errors import GoogleAdsException


def _run_gaql(customer_id: str, query: str, login_customer_id: str | None = None) -> list[dict]:
  """Execute a GAQL query and return rows as dicts."""
  ads_client = get_ads_client()
  if login_customer_id:
    ads_client.login_customer_id = login_customer_id
  service = ads_client.get_service("GoogleAdsService")
  try:
    stream = service.search_stream(query=query, customer_id=customer_id)
    rows = []
    for batch in stream:
      for row in batch.results:
        rows.append({path: _extract(row, path) for path in batch.field_mask.paths})
    return rows
  except GoogleAdsException as e:
    raise ToolError("\n".join(str(err) for err in e.failure.errors)) from e


def _extract(row, path: str):
  """Safely extract a dotted field path from a proto row."""
  obj = row
  for part in path.split("."):
    try:
      obj = getattr(obj, part)
    except AttributeError:
      return None
  # Convert proto enums to their name string
  if hasattr(obj, "name"):
    return obj.name
  return obj


# ---------------------------------------------------------------------------
# Preview tools
# ---------------------------------------------------------------------------

@mcp.tool()
def preview_update_campaign_status(
    customer_id: str,
    campaign_resource_name: str,
    new_status: str,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Preview what changing a campaign's status will look like (read-only).

  Fetches the campaign's current status and shows a before/after diff
  without making any changes.

  Args:
    customer_id: Google Ads customer ID (digits only).
    campaign_resource_name: Full resource name (e.g. "customers/123/campaigns/456").
    new_status: The status you intend to set: ENABLED or PAUSED.
    login_customer_id: MCC account ID if customer is managed.

  Returns:
    Dict with campaign name, before/after status, and a plain-English summary.
  """
  # Extract numeric campaign ID from resource name
  campaign_id = campaign_resource_name.split("/")[-1]
  query = (
      f"SELECT campaign.id, campaign.name, campaign.status "
      f"FROM campaign "
      f"WHERE campaign.id = {campaign_id}"
  )
  rows = _run_gaql(customer_id, query, login_customer_id)
  if not rows:
    raise ToolError(f"Campaign not found: {campaign_resource_name}")

  row = rows[0]
  current_status = row.get("campaign.status", "UNKNOWN")
  campaign_name = row.get("campaign.name", "(unknown)")

  return {
      "campaign": campaign_name,
      "resource_name": campaign_resource_name,
      "before": {"status": current_status},
      "after": {"status": new_status.upper()},
      "changed": current_status != new_status.upper(),
      "summary": (
          f"Campaign '{campaign_name}' status: {current_status} → {new_status.upper()}"
          if current_status != new_status.upper()
          else f"Campaign '{campaign_name}' is already {current_status}. No change needed."
      ),
  }


@mcp.tool()
def preview_update_campaign_budget(
    customer_id: str,
    budget_resource_name: str,
    new_amount_micros: int,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Preview what updating a campaign budget will look like (read-only).

  Args:
    customer_id: Google Ads customer ID (digits only).
    budget_resource_name: Full resource name of the CampaignBudget.
    new_amount_micros: Intended new daily budget in micros.
    login_customer_id: MCC account ID if customer is managed.

  Returns:
    Dict with budget name, before/after amounts in both micros and currency units.
  """
  budget_id = budget_resource_name.split("/")[-1]
  query = (
      f"SELECT campaign_budget.id, campaign_budget.name, "
      f"campaign_budget.amount_micros, campaign_budget.status "
      f"FROM campaign_budget "
      f"WHERE campaign_budget.id = {budget_id}"
  )
  rows = _run_gaql(customer_id, query, login_customer_id)
  if not rows:
    raise ToolError(f"Budget not found: {budget_resource_name}")

  row = rows[0]
  current_micros = row.get("campaign_budget.amount_micros", 0)
  budget_name = row.get("campaign_budget.name", "(unknown)")

  current_amount = current_micros / 1_000_000
  new_amount = new_amount_micros / 1_000_000
  delta = new_amount - current_amount
  delta_str = f"+{delta:.2f}" if delta >= 0 else f"{delta:.2f}"

  return {
      "budget": budget_name,
      "resource_name": budget_resource_name,
      "before": {
          "amount_micros": current_micros,
          "amount": round(current_amount, 2),
      },
      "after": {
          "amount_micros": new_amount_micros,
          "amount": round(new_amount, 2),
      },
      "delta": round(delta, 2),
      "changed": current_micros != new_amount_micros,
      "summary": (
          f"Budget '{budget_name}': {current_amount:.2f} → {new_amount:.2f}/day "
          f"({delta_str})"
      ),
  }


@mcp.tool()
def preview_update_ad_group_status(
    customer_id: str,
    ad_group_resource_name: str,
    new_status: str,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Preview what changing an ad group's status will look like (read-only).

  Args:
    customer_id: Google Ads customer ID (digits only).
    ad_group_resource_name: Full resource name of the ad group.
    new_status: The status you intend to set: ENABLED, PAUSED, or REMOVED.
    login_customer_id: MCC account ID if customer is managed.

  Returns:
    Dict with ad group name, before/after status.
  """
  ad_group_id = ad_group_resource_name.split("/")[-1]
  query = (
      f"SELECT ad_group.id, ad_group.name, ad_group.status "
      f"FROM ad_group "
      f"WHERE ad_group.id = {ad_group_id}"
  )
  rows = _run_gaql(customer_id, query, login_customer_id)
  if not rows:
    raise ToolError(f"Ad group not found: {ad_group_resource_name}")

  row = rows[0]
  current_status = row.get("ad_group.status", "UNKNOWN")
  ad_group_name = row.get("ad_group.name", "(unknown)")

  return {
      "ad_group": ad_group_name,
      "resource_name": ad_group_resource_name,
      "before": {"status": current_status},
      "after": {"status": new_status.upper()},
      "changed": current_status != new_status.upper(),
      "summary": (
          f"Ad group '{ad_group_name}' status: {current_status} → {new_status.upper()}"
          if current_status != new_status.upper()
          else f"Ad group '{ad_group_name}' is already {current_status}. No change needed."
      ),
  }


@mcp.tool()
def preview_add_negative_keyword(
    customer_id: str,
    ad_group_resource_name: str,
    keyword_text: str,
    match_type: str = "EXACT",
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Preview adding a negative keyword — checks if it already exists (read-only).

  Args:
    customer_id: Google Ads customer ID (digits only).
    ad_group_resource_name: Full resource name of the ad group.
    keyword_text: The negative keyword text.
    match_type: EXACT, PHRASE, or BROAD. Default EXACT.
    login_customer_id: MCC account ID if customer is managed.

  Returns:
    Dict confirming the keyword to be added and whether it already exists.
  """
  ad_group_id = ad_group_resource_name.split("/")[-1]
  query = (
      f"SELECT ad_group_criterion.keyword.text, "
      f"ad_group_criterion.keyword.match_type, "
      f"ad_group_criterion.negative "
      f"FROM ad_group_criterion "
      f"WHERE ad_group_criterion.ad_group = '{ad_group_resource_name}' "
      f"AND ad_group_criterion.negative = TRUE "
      f"AND ad_group_criterion.type = KEYWORD"
  )
  try:
    rows = _run_gaql(customer_id, query, login_customer_id)
  except ToolError:
    rows = []

  already_exists = any(
      r.get("ad_group_criterion.keyword.text", "").lower() == keyword_text.lower()
      and r.get("ad_group_criterion.keyword.match_type", "") == match_type.upper()
      for r in rows
  )

  return {
      "ad_group_resource_name": ad_group_resource_name,
      "keyword_text": keyword_text,
      "match_type": match_type.upper(),
      "negative": True,
      "already_exists": already_exists,
      "summary": (
          f"Negative keyword [{match_type.upper()}] '{keyword_text}' already exists in this ad group."
          if already_exists
          else f"Will add negative keyword [{match_type.upper()}] '{keyword_text}' to ad group."
      ),
  }
