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

"""Convenience reporting tools for Google Ads API (read-only).

These ``gads_*`` tools wrap common GAQL reporting queries so callers don't
have to hand-write GAQL for everyday reporting tasks:

  gads_run_gaql                 – arbitrary GAQL with paging support
  gads_get_campaign_performance – campaign metrics over a date range
  gads_get_ad_group_performance – ad-group metrics over a date range
  gads_get_ad_performance       – ad-level metrics + creative fields
  gads_get_keyword_performance  – keyword metrics + match type + quality score
  gads_get_search_terms         – search-terms report (actual user queries)

All tools are read-only and idempotent. For accounts managed under an MCC
(or accessed via a manager), pass ``login_customer_id`` = the manager ID.
"""

from __future__ import annotations

import re
from typing import Any

from ads_mcp.coordinator import mcp_server as mcp
from ads_mcp.tools._utils import get_ads_client
from ads_mcp.tools.reporting import format_value
from ads_mcp.tools.reporting import preprocess_gaql
from fastmcp.exceptions import ToolError
from google.ads.googleads.errors import GoogleAdsException
from google.ads.googleads.util import get_nested_attr

# Read-only + idempotent hints for MCP clients.
_READ_ANNOTATIONS = {"readOnlyHint": True, "idempotentHint": True}

# Predefined Google Ads relative date ranges (DateRangeType enum values).
_VALID_DATE_RANGES = frozenset({
    "TODAY",
    "YESTERDAY",
    "LAST_7_DAYS",
    "LAST_14_DAYS",
    "LAST_30_DAYS",
    "LAST_BUSINESS_WEEK",
    "THIS_WEEK_SUN_TODAY",
    "THIS_WEEK_MON_TODAY",
    "LAST_WEEK_SUN_SAT",
    "LAST_WEEK_MON_SUN",
    "THIS_MONTH",
    "LAST_MONTH",
    "ALL_TIME",
})

# Metrics selected by every performance wrapper.
_METRIC_FIELDS = (
    "metrics.impressions",
    "metrics.clicks",
    "metrics.ctr",
    "metrics.average_cpc",
    "metrics.cost_micros",
    "metrics.conversions",
    "metrics.conversions_value",
    "metrics.cost_per_conversion",
)

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ID_RE = re.compile(r"^\d+$")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _rows(
    customer_id: str,
    query: str,
    login_customer_id: str | None = None,
) -> list[dict[str, Any]]:
  """Runs a GAQL query and returns rows keyed by selected field path."""
  query = preprocess_gaql(query)
  ads_client = get_ads_client()
  if login_customer_id:
    ads_client.login_customer_id = login_customer_id
  service = ads_client.get_service("GoogleAdsService")
  try:
    stream = service.search_stream(query=query, customer_id=customer_id)
    output = []
    for batch in stream:
      for row in batch.results:
        output.append({
            path: format_value(get_nested_attr(row, path))
            for path in batch.field_mask.paths
        })
    return output
  except GoogleAdsException as e:
    raise ToolError("\n".join(str(err) for err in e.failure.errors)) from e


def _date_clause(
    date_range: str | None,
    start_date: str | None,
    end_date: str | None,
) -> str:
  """Builds the segments.date WHERE clause from either form of input.

  Custom start_date/end_date (YYYY-MM-DD) take precedence over date_range.
  Falls back to LAST_30_DAYS when nothing is supplied.
  """
  if start_date or end_date:
    if not (start_date and end_date):
      raise ToolError(
          "Both start_date and end_date are required for a custom range."
      )
    if not (_DATE_RE.match(start_date) and _DATE_RE.match(end_date)):
      raise ToolError("start_date and end_date must be in YYYY-MM-DD format.")
    return f"segments.date BETWEEN '{start_date}' AND '{end_date}'"

  effective = (date_range or "LAST_30_DAYS").upper()
  if effective not in _VALID_DATE_RANGES:
    raise ToolError(
        f"Invalid date_range '{date_range}'. Use one of "
        f"{sorted(_VALID_DATE_RANGES)} or pass start_date/end_date."
    )
  return f"segments.date DURING {effective}"


def _id_clause(field: str, ids: list[str] | None) -> str:
  """Builds an optional ``AND field IN (...)`` clause from digit-only IDs."""
  if not ids:
    return ""
  clean = [str(i).strip() for i in ids if str(i).strip()]
  for i in clean:
    if not _ID_RE.match(i):
      raise ToolError(f"Invalid id '{i}' for {field}: IDs must be digits only.")
  if not clean:
    return ""
  return f" AND {field} IN ({', '.join(clean)})"


def _metrics(r: dict[str, Any]) -> dict[str, Any]:
  """Extracts and normalizes the common metric block from a row.

  Micros fields (cost, average_cpc, cost_per_conversion) are converted to
  account-currency units. ROAS is derived as conversions_value / cost.
  """
  cost = (r.get("metrics.cost_micros") or 0) / 1_000_000
  conv_value = r.get("metrics.conversions_value") or 0.0
  return {
      "impressions": int(r.get("metrics.impressions") or 0),
      "clicks": int(r.get("metrics.clicks") or 0),
      "ctr": round(r.get("metrics.ctr") or 0.0, 6),
      "avg_cpc": round((r.get("metrics.average_cpc") or 0) / 1_000_000, 2),
      "cost": round(cost, 2),
      "conversions": round(r.get("metrics.conversions") or 0.0, 2),
      "conversions_value": round(conv_value, 2),
      "cost_per_conversion": round(
          (r.get("metrics.cost_per_conversion") or 0) / 1_000_000, 2
      ),
      "roas": round(conv_value / cost, 2) if cost else 0.0,
  }


# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------

@mcp.tool(name="gads_run_gaql", annotations=_READ_ANNOTATIONS)
def gads_run_gaql(
    customer_id: str,
    query: str,
    page_size: int | None = None,
    page_token: str | None = None,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Runs an arbitrary GAQL query and returns one page of results.

  This covers nearly the whole read surface of the Google Ads API. Unlike
  search_stream, it pages: pass ``page_token`` (returned as
  ``next_page_token``) to fetch the next page.

  Args:
    customer_id: Google Ads customer ID being queried (digits only).
    query: The GAQL query to execute.
    page_size: Accepted for compatibility but ignored — the Google Ads API
      fixes the page size at 10000 rows and rejects the field.
    page_token: Token from a previous call's ``next_page_token`` to continue.
    login_customer_id: Manager (MCC) ID if the account is accessed via a
      manager. Digits only.

  Returns:
    Dict with ``data`` (list of row dicts keyed by selected field path),
    ``next_page_token`` (empty string when there are no more pages), and
    ``total_rows`` (rows in this page).
  """
  query = preprocess_gaql(query)
  ads_client = get_ads_client()
  if login_customer_id:
    ads_client.login_customer_id = login_customer_id
  service = ads_client.get_service("GoogleAdsService")

  request = ads_client.get_type("SearchGoogleAdsRequest")
  request.customer_id = customer_id
  request.query = query
  # NOTE: the Google Ads API no longer honors page_size (fixed at 10000 rows
  # per page and rejects the field). The parameter is accepted for caller
  # compatibility but intentionally not forwarded to the API.
  del page_size
  if page_token:
    request.page_token = page_token

  try:
    pager = service.search(request=request)
    # Take just the first page so paging is controllable by the caller.
    page = next(iter(pager.pages))
  except StopIteration:
    return {"data": [], "next_page_token": "", "total_rows": 0}
  except GoogleAdsException as e:
    raise ToolError("\n".join(str(err) for err in e.failure.errors)) from e

  data = [
      {
          path: format_value(get_nested_attr(row, path))
          for path in page.field_mask.paths
      }
      for row in page.results
  ]
  return {
      "data": data,
      "next_page_token": page.next_page_token or "",
      "total_rows": len(data),
  }


@mcp.tool(name="gads_get_campaign_performance", annotations=_READ_ANNOTATIONS)
def gads_get_campaign_performance(
    customer_id: str,
    date_range: str | None = "LAST_30_DAYS",
    start_date: str | None = None,
    end_date: str | None = None,
    campaign_ids: list[str] | None = None,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Campaign-level metrics (impressions, clicks, cost, conversions, ROAS).

  Args:
    customer_id: Google Ads customer ID (digits only).
    date_range: Predefined range such as LAST_7_DAYS, LAST_30_DAYS, THIS_MONTH.
      Ignored when start_date/end_date are given. Defaults to LAST_30_DAYS.
    start_date: Custom range start, YYYY-MM-DD (requires end_date).
    end_date: Custom range end, YYYY-MM-DD (requires start_date).
    campaign_ids: Optional list of campaign IDs to filter to (digits only).
    login_customer_id: Manager (MCC) ID if accessed via a manager.

  Returns:
    Dict with ``data``: one row per campaign, sorted by cost descending.
  """
  where = _date_clause(date_range, start_date, end_date)
  where += _id_clause("campaign.id", campaign_ids)
  query = f"""
    SELECT
      campaign.id,
      campaign.name,
      campaign.status,
      campaign.advertising_channel_type,
      {", ".join(_METRIC_FIELDS)}
    FROM campaign
    WHERE {where}
    ORDER BY metrics.cost_micros DESC
  """
  rows = _rows(customer_id, query, login_customer_id)
  return {
      "data": [
          {
              "campaign_id": str(r.get("campaign.id", "")),
              "campaign_name": r.get("campaign.name", ""),
              "status": r.get("campaign.status", ""),
              "channel_type": r.get("campaign.advertising_channel_type", ""),
              **_metrics(r),
          }
          for r in rows
      ]
  }


@mcp.tool(name="gads_get_ad_group_performance", annotations=_READ_ANNOTATIONS)
def gads_get_ad_group_performance(
    customer_id: str,
    date_range: str | None = "LAST_30_DAYS",
    start_date: str | None = None,
    end_date: str | None = None,
    campaign_ids: list[str] | None = None,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Ad-group-level metrics over a date range.

  Args:
    customer_id: Google Ads customer ID (digits only).
    date_range: Predefined range (default LAST_30_DAYS). See
      gads_get_campaign_performance for accepted values.
    start_date: Custom range start, YYYY-MM-DD (requires end_date).
    end_date: Custom range end, YYYY-MM-DD (requires start_date).
    campaign_ids: Optional list of campaign IDs to filter to (digits only).
    login_customer_id: Manager (MCC) ID if accessed via a manager.

  Returns:
    Dict with ``data``: one row per ad group, sorted by cost descending.
  """
  where = _date_clause(date_range, start_date, end_date)
  where += _id_clause("campaign.id", campaign_ids)
  query = f"""
    SELECT
      ad_group.id,
      ad_group.name,
      ad_group.status,
      campaign.id,
      campaign.name,
      {", ".join(_METRIC_FIELDS)}
    FROM ad_group
    WHERE {where}
    ORDER BY metrics.cost_micros DESC
  """
  rows = _rows(customer_id, query, login_customer_id)
  return {
      "data": [
          {
              "ad_group_id": str(r.get("ad_group.id", "")),
              "ad_group_name": r.get("ad_group.name", ""),
              "status": r.get("ad_group.status", ""),
              "campaign_id": str(r.get("campaign.id", "")),
              "campaign_name": r.get("campaign.name", ""),
              **_metrics(r),
          }
          for r in rows
      ]
  }


@mcp.tool(name="gads_get_ad_performance", annotations=_READ_ANNOTATIONS)
def gads_get_ad_performance(
    customer_id: str,
    date_range: str | None = "LAST_30_DAYS",
    start_date: str | None = None,
    end_date: str | None = None,
    ad_group_ids: list[str] | None = None,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Ad-level metrics with creative fields (headlines, descriptions, URLs).

  Args:
    customer_id: Google Ads customer ID (digits only).
    date_range: Predefined range (default LAST_30_DAYS).
    start_date: Custom range start, YYYY-MM-DD (requires end_date).
    end_date: Custom range end, YYYY-MM-DD (requires start_date).
    ad_group_ids: Optional list of ad group IDs to filter to (digits only).
    login_customer_id: Manager (MCC) ID if accessed via a manager.

  Returns:
    Dict with ``data``: one row per ad, sorted by cost descending. Each row
    includes ad id/name/type/status, final_urls, and (for responsive search
    ads) headlines and descriptions.
  """
  where = _date_clause(date_range, start_date, end_date)
  where += _id_clause("ad_group.id", ad_group_ids)
  query = f"""
    SELECT
      ad_group_ad.ad.id,
      ad_group_ad.ad.name,
      ad_group_ad.ad.type,
      ad_group_ad.status,
      ad_group_ad.ad.final_urls,
      ad_group_ad.ad.responsive_search_ad.headlines,
      ad_group_ad.ad.responsive_search_ad.descriptions,
      ad_group.id,
      ad_group.name,
      campaign.id,
      campaign.name,
      {", ".join(_METRIC_FIELDS)}
    FROM ad_group_ad
    WHERE {where}
    ORDER BY metrics.cost_micros DESC
  """
  rows = _rows(customer_id, query, login_customer_id)
  return {
      "data": [
          {
              "ad_id": str(r.get("ad_group_ad.ad.id", "")),
              "ad_name": r.get("ad_group_ad.ad.name", ""),
              "ad_type": r.get("ad_group_ad.ad.type", ""),
              "status": r.get("ad_group_ad.status", ""),
              "final_urls": r.get("ad_group_ad.ad.final_urls", []),
              "headlines": r.get(
                  "ad_group_ad.ad.responsive_search_ad.headlines", []
              ),
              "descriptions": r.get(
                  "ad_group_ad.ad.responsive_search_ad.descriptions", []
              ),
              "ad_group_id": str(r.get("ad_group.id", "")),
              "ad_group_name": r.get("ad_group.name", ""),
              "campaign_id": str(r.get("campaign.id", "")),
              "campaign_name": r.get("campaign.name", ""),
              **_metrics(r),
          }
          for r in rows
      ]
  }


@mcp.tool(name="gads_get_keyword_performance", annotations=_READ_ANNOTATIONS)
def gads_get_keyword_performance(
    customer_id: str,
    date_range: str | None = "LAST_30_DAYS",
    start_date: str | None = None,
    end_date: str | None = None,
    ad_group_ids: list[str] | None = None,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Keyword-level metrics with match type and Quality Score.

  Args:
    customer_id: Google Ads customer ID (digits only).
    date_range: Predefined range (default LAST_30_DAYS).
    start_date: Custom range start, YYYY-MM-DD (requires end_date).
    end_date: Custom range end, YYYY-MM-DD (requires start_date).
    ad_group_ids: Optional list of ad group IDs to filter to (digits only).
    login_customer_id: Manager (MCC) ID if accessed via a manager.

  Returns:
    Dict with ``data``: one row per keyword, sorted by cost descending.
  """
  where = _date_clause(date_range, start_date, end_date)
  where += _id_clause("ad_group.id", ad_group_ids)
  query = f"""
    SELECT
      ad_group_criterion.criterion_id,
      ad_group_criterion.keyword.text,
      ad_group_criterion.keyword.match_type,
      ad_group_criterion.status,
      ad_group_criterion.quality_info.quality_score,
      ad_group.id,
      ad_group.name,
      campaign.id,
      campaign.name,
      {", ".join(_METRIC_FIELDS)}
    FROM keyword_view
    WHERE {where}
    ORDER BY metrics.cost_micros DESC
  """
  rows = _rows(customer_id, query, login_customer_id)
  return {
      "data": [
          {
              "criterion_id": str(r.get("ad_group_criterion.criterion_id", "")),
              "keyword": r.get("ad_group_criterion.keyword.text", ""),
              "match_type": r.get(
                  "ad_group_criterion.keyword.match_type", ""
              ),
              "status": r.get("ad_group_criterion.status", ""),
              "quality_score": r.get(
                  "ad_group_criterion.quality_info.quality_score"
              ),
              "ad_group_id": str(r.get("ad_group.id", "")),
              "ad_group_name": r.get("ad_group.name", ""),
              "campaign_id": str(r.get("campaign.id", "")),
              "campaign_name": r.get("campaign.name", ""),
              **_metrics(r),
          }
          for r in rows
      ]
  }


@mcp.tool(name="gads_get_search_terms", annotations=_READ_ANNOTATIONS)
def gads_get_search_terms(
    customer_id: str,
    date_range: str | None = "LAST_30_DAYS",
    start_date: str | None = None,
    end_date: str | None = None,
    campaign_ids: list[str] | None = None,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Search-terms report — the actual queries users typed.

  Args:
    customer_id: Google Ads customer ID (digits only).
    date_range: Predefined range (default LAST_30_DAYS).
    start_date: Custom range start, YYYY-MM-DD (requires end_date).
    end_date: Custom range end, YYYY-MM-DD (requires start_date).
    campaign_ids: Optional list of campaign IDs to filter to (digits only).
    login_customer_id: Manager (MCC) ID if accessed via a manager.

  Returns:
    Dict with ``data``: one row per search term, sorted by impressions
    descending. Each row includes the term, its match type, and the
    campaign / ad group it served under.
  """
  where = _date_clause(date_range, start_date, end_date)
  where += _id_clause("campaign.id", campaign_ids)
  query = f"""
    SELECT
      search_term_view.search_term,
      search_term_view.status,
      segments.search_term_match_type,
      campaign.id,
      campaign.name,
      ad_group.id,
      ad_group.name,
      {", ".join(_METRIC_FIELDS)}
    FROM search_term_view
    WHERE {where}
    ORDER BY metrics.impressions DESC
  """
  rows = _rows(customer_id, query, login_customer_id)
  return {
      "data": [
          {
              "search_term": r.get("search_term_view.search_term", ""),
              "status": r.get("search_term_view.status", ""),
              "match_type": r.get("segments.search_term_match_type", ""),
              "campaign_id": str(r.get("campaign.id", "")),
              "campaign_name": r.get("campaign.name", ""),
              "ad_group_id": str(r.get("ad_group.id", "")),
              "ad_group_name": r.get("ad_group.name", ""),
              **_metrics(r),
          }
          for r in rows
      ]
  }
