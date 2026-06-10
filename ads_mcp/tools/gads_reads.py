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

"""Read-only tools from spec §4 (assets) and §7 (optimization & planning).

  gads_list_assets             – account assets (images, sitelinks, callouts)
  gads_list_recommendations    – Google's auto-recommendations
  gads_generate_keyword_ideas  – Keyword Planner ideas + volume/competition
  gads_list_conversion_actions – configured conversion actions

All always-on and read-only. The apply/dismiss recommendation tools (§7
mutations) live in the gated gads_mutations package.
"""

from __future__ import annotations

from typing import Any

from ads_mcp.coordinator import mcp_server as mcp
from ads_mcp.tools._utils import get_ads_client
from fastmcp.exceptions import ToolError
from google.ads.googleads.errors import GoogleAdsException

_READ = {"readOnlyHint": True, "idempotentHint": True}

_ID_OK = lambda s: str(s).isdigit()


def _search(customer_id: str, query: str, login_customer_id: str | None):
  client = get_ads_client()
  if login_customer_id:
    client.login_customer_id = login_customer_id
  service = client.get_service("GoogleAdsService")
  try:
    stream = service.search_stream(query=query, customer_id=customer_id)
    rows = []
    for batch in stream:
      rows.extend(batch.results)
    return rows
  except GoogleAdsException as e:
    raise ToolError("\n".join(str(err) for err in e.failure.errors)) from e


@mcp.tool(name="gads_list_assets", annotations=_READ)
def gads_list_assets(
    customer_id: str,
    asset_type: str | None = None,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Lists account assets (images, text, sitelinks, callouts, etc.).

  Args:
    customer_id: Google Ads customer ID (digits only).
    asset_type: Optional filter such as IMAGE, TEXT, SITELINK, CALLOUT,
      YOUTUBE_VIDEO. Case-insensitive. When omitted, all asset types return.
    login_customer_id: Manager (MCC) ID if the account is managed.

  Returns:
    Dict with ``data``: list of {asset_id, name, type, resource_name}.
  """
  where = ""
  if asset_type:
    safe = asset_type.strip().upper().replace("'", "")
    where = f" WHERE asset.type = {safe}"
  query = (
      "SELECT asset.id, asset.name, asset.type, asset.resource_name "
      f"FROM asset{where} ORDER BY asset.id"
  )
  rows = _search(customer_id, query, login_customer_id)
  return {
      "data": [
          {
              "asset_id": str(r.asset.id),
              "name": r.asset.name,
              "type": r.asset.type_.name,
              "resource_name": r.asset.resource_name,
          }
          for r in rows
      ]
  }


@mcp.tool(name="gads_list_recommendations", annotations=_READ)
def gads_list_recommendations(
    customer_id: str,
    types: list[str] | None = None,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Lists Google's auto-recommendations for the account.

  Args:
    customer_id: Google Ads customer ID (digits only).
    types: Optional list of recommendation types to filter to, e.g.
      ["KEYWORD", "CAMPAIGN_BUDGET", "TARGET_CPA_OPT_IN"]. Case-insensitive.
    login_customer_id: Manager (MCC) ID if the account is managed.

  Returns:
    Dict with ``data``: list of {resource_name, type, campaign,
    dismissed}. Pass a resource_name to gads_apply_recommendation or
    gads_dismiss_recommendation.
  """
  where = ""
  if types:
    safe = ", ".join(t.strip().upper().replace("'", "") for t in types if t)
    if safe:
      where = f" WHERE recommendation.type IN ({safe})"
  query = (
      "SELECT recommendation.resource_name, recommendation.type, "
      "recommendation.campaign, recommendation.dismissed "
      f"FROM recommendation{where}"
  )
  rows = _search(customer_id, query, login_customer_id)
  return {
      "data": [
          {
              "resource_name": r.recommendation.resource_name,
              "type": r.recommendation.type_.name,
              "campaign": r.recommendation.campaign,
              "dismissed": r.recommendation.dismissed,
          }
          for r in rows
      ]
  }


@mcp.tool(name="gads_list_conversion_actions", annotations=_READ)
def gads_list_conversion_actions(
    customer_id: str,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Lists configured conversion actions for the account.

  Args:
    customer_id: Google Ads customer ID (digits only).
    login_customer_id: Manager (MCC) ID if the account is managed.

  Returns:
    Dict with ``data``: list of {id, name, type, category, status,
    primary_for_goal}.
  """
  query = """
    SELECT
      conversion_action.id,
      conversion_action.name,
      conversion_action.type,
      conversion_action.category,
      conversion_action.status,
      conversion_action.primary_for_goal
    FROM conversion_action
    ORDER BY conversion_action.id
  """
  rows = _search(customer_id, query, login_customer_id)
  return {
      "data": [
          {
              "id": str(r.conversion_action.id),
              "name": r.conversion_action.name,
              "type": r.conversion_action.type_.name,
              "category": r.conversion_action.category.name,
              "status": r.conversion_action.status.name,
              "primary_for_goal": r.conversion_action.primary_for_goal,
          }
          for r in rows
      ]
  }


@mcp.tool(name="gads_generate_keyword_ideas", annotations=_READ)
def gads_generate_keyword_ideas(
    customer_id: str,
    seed_keywords: list[str] | None = None,
    url: str | None = None,
    geo_target_ids: list[str] | None = None,
    language_id: str = "1000",
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Generates Keyword Planner ideas with search volume and competition.

  Provide ``seed_keywords``, a ``url``, or both. Metrics reflect the given
  geo/language targeting.

  Args:
    customer_id: Google Ads customer ID (digits only).
    seed_keywords: Seed terms to expand from.
    url: A page URL to derive ideas from (used alone or with seeds).
    geo_target_ids: Geo target constant IDs (e.g. ["2246"] for Finland,
      ["2840"] for the US). Optional.
    language_id: Language constant ID. Default "1000" (English). Finnish is
      "1035".
    login_customer_id: Manager (MCC) ID if the account is managed.

  Returns:
    Dict with ``data``: list of {keyword, avg_monthly_searches, competition,
    competition_index, low_top_of_page_bid_micros,
    high_top_of_page_bid_micros}, sorted by avg_monthly_searches descending.
  """
  if not seed_keywords and not url:
    raise ToolError("Provide seed_keywords, url, or both.")
  if not _ID_OK(language_id):
    raise ToolError("language_id must be digits only (e.g. '1000').")
  for g in geo_target_ids or []:
    if not _ID_OK(g):
      raise ToolError(f"Invalid geo_target_id '{g}': digits only.")

  client = get_ads_client()
  if login_customer_id:
    client.login_customer_id = login_customer_id
  service = client.get_service("KeywordPlanIdeaService")

  request = client.get_type("GenerateKeywordIdeasRequest")
  request.customer_id = customer_id
  request.language = f"languageConstants/{language_id}"
  request.geo_target_constants.extend(
      [f"geoTargetConstants/{g}" for g in (geo_target_ids or [])]
  )
  request.keyword_plan_network = (
      client.enums.KeywordPlanNetworkEnum.GOOGLE_SEARCH
  )

  seeds = [s for s in (seed_keywords or []) if s.strip()]
  if seeds and url:
    request.keyword_and_url_seed.url = url
    request.keyword_and_url_seed.keywords.extend(seeds)
  elif seeds:
    request.keyword_seed.keywords.extend(seeds)
  else:
    request.url_seed.url = url

  try:
    response = service.generate_keyword_ideas(request=request)
  except GoogleAdsException as e:
    raise ToolError("\n".join(str(err) for err in e.failure.errors)) from e

  data = []
  for idea in response:
    m = idea.keyword_idea_metrics
    data.append({
        "keyword": idea.text,
        "avg_monthly_searches": m.avg_monthly_searches,
        "competition": m.competition.name,
        "competition_index": m.competition_index,
        "low_top_of_page_bid_micros": m.low_top_of_page_bid_micros,
        "high_top_of_page_bid_micros": m.high_top_of_page_bid_micros,
    })
  data.sort(key=lambda d: d["avg_monthly_searches"] or 0, reverse=True)
  return {"data": data}
