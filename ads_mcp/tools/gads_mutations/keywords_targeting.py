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

"""Keywords & targeting mutations (spec §5) — approval-gated.

  gads_add_keywords            gads_remove_keywords
  gads_add_negative_keywords   gads_set_targeting

Batch operations use partial_failure so per-operation errors surface instead
of failing the whole batch. All accept validate_only and stage through the
approval flow.
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
from ads_mcp.tools.gads_mutations._common import multi_result
from ads_mcp.tools.gads_mutations._common import require_digits
from ads_mcp.tools.gads_mutations._common import _get_client
from ads_mcp.tools.gads_mutations._common import _handle_google_ads_error
from ads_mcp.tools.gads_mutations._common import _resolve_enum
from ads_mcp.tools.mutations.approval import propose
from fastmcp.exceptions import ToolError
from google.ads.googleads.errors import GoogleAdsException


@mcp.tool(name="gads_add_keywords", annotations=ANN_CREATE)
def gads_add_keywords(
    customer_id: str,
    ad_group_id: str,
    keywords: list[dict[str, Any]],
    validate_only: bool = False,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Stages adding keywords (ENABLED) to an ad group. Requires approval.

  Args:
    customer_id: Google Ads customer ID (digits only).
    ad_group_id: Ad group ID (digits only).
    keywords: List of dicts with: text (str), match_type
      (EXACT/PHRASE/BROAD), and optional cpc_bid_micros (int).
    validate_only: If True, the approved change runs as a dry-run.
    login_customer_id: Manager (MCC) ID if the account is managed.

  Returns:
    Pending change record.
  """
  cid = require_digits(customer_id, "customer_id")
  agid = require_digits(ad_group_id, "ad_group_id")
  if not keywords:
    raise ToolError("Provide at least one keyword.")
  for kw in keywords:
    if not kw.get("text") or not kw.get("match_type"):
      raise ToolError("Each keyword needs 'text' and 'match_type'.")
  params = dict(
      customer_id=cid, ad_group_id=agid, keywords=keywords,
      validate_only=validate_only, login_customer_id=login_customer_id,
  )

  def executor():
    client = _get_client(login_customer_id)
    service = client.get_service("AdGroupCriterionService")
    ad_group_service = client.get_service("AdGroupService")
    ad_group_rn = ad_group_service.ad_group_path(cid, agid)
    operations = []
    for kw in keywords:
      criterion = resource_types.AdGroupCriterion(
          ad_group=ad_group_rn,
          status=(
              enum_types.AdGroupCriterionStatusEnum.AdGroupCriterionStatus.ENABLED
          ),
          keyword=common_types.KeywordInfo(
              text=kw["text"],
              match_type=_resolve_enum(
                  enum_types.KeywordMatchTypeEnum.KeywordMatchType,
                  kw["match_type"], "match_type",
              ),
          ),
      )
      if kw.get("cpc_bid_micros") is not None:
        criterion.cpc_bid_micros = int(kw["cpc_bid_micros"])
      operations.append(
          service_types.AdGroupCriterionOperation(create=criterion)
      )
    try:
      response = service.mutate_ad_group_criteria(
          request=build_request(
              client, "MutateAdGroupCriteriaRequest", cid, operations,
              validate_only, partial_failure=True,
          )
      )
    except GoogleAdsException as e:
      _handle_google_ads_error(e)
    return multi_result(response, validate_only)

  summary = (
      f"Add {len(keywords)} keyword(s) to ad group {agid} (customer {cid})"
      + (" [validate_only]" if validate_only else "")
  )
  return propose("gads_add_keywords", cid, summary, params, executor)


@mcp.tool(name="gads_add_negative_keywords", annotations=ANN_UPDATE)
def gads_add_negative_keywords(
    customer_id: str,
    level: str,
    parent_id: str,
    keywords: list[str],
    match_type: str = "BROAD",
    validate_only: bool = False,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Stages adding negative keywords at ad-group or campaign level. Requires approval.

  Args:
    customer_id: Google Ads customer ID (digits only).
    level: "ad_group" or "campaign".
    parent_id: The ad group ID or campaign ID (matching level; digits only).
    keywords: Negative keyword texts.
    match_type: EXACT, PHRASE, or BROAD (default BROAD).
    validate_only: If True, the approved change runs as a dry-run.
    login_customer_id: Manager (MCC) ID if the account is managed.

  Returns:
    Pending change record.
  """
  cid = require_digits(customer_id, "customer_id")
  pid = require_digits(parent_id, "parent_id")
  lvl = level.strip().lower()
  if lvl not in ("ad_group", "campaign"):
    raise ToolError("level must be 'ad_group' or 'campaign'.")
  if not keywords:
    raise ToolError("Provide at least one keyword.")
  params = dict(
      customer_id=cid, level=lvl, parent_id=pid, keywords=keywords,
      match_type=match_type, validate_only=validate_only,
      login_customer_id=login_customer_id,
  )

  def executor():
    client = _get_client(login_customer_id)
    mt = _resolve_enum(
        enum_types.KeywordMatchTypeEnum.KeywordMatchType, match_type,
        "match_type",
    )
    if lvl == "ad_group":
      service = client.get_service("AdGroupCriterionService")
      parent_rn = service.ad_group_path(cid, pid)
      operations = []
      for text in keywords:
        criterion = resource_types.AdGroupCriterion(
            ad_group=parent_rn, negative=True,
            keyword=common_types.KeywordInfo(text=text, match_type=mt),
        )
        operations.append(
            service_types.AdGroupCriterionOperation(create=criterion)
        )
      request_type, method = "MutateAdGroupCriteriaRequest", service.mutate_ad_group_criteria
    else:
      service = client.get_service("CampaignCriterionService")
      parent_rn = service.campaign_path(cid, pid)
      operations = []
      for text in keywords:
        criterion = resource_types.CampaignCriterion(
            campaign=parent_rn, negative=True,
            keyword=common_types.KeywordInfo(text=text, match_type=mt),
        )
        operations.append(
            service_types.CampaignCriterionOperation(create=criterion)
        )
      request_type, method = "MutateCampaignCriteriaRequest", service.mutate_campaign_criteria
    try:
      response = method(
          request=build_request(
              client, request_type, cid, operations, validate_only,
              partial_failure=True,
          )
      )
    except GoogleAdsException as e:
      _handle_google_ads_error(e)
    return multi_result(response, validate_only)

  summary = (
      f"Add {len(keywords)} negative [{match_type}] keyword(s) at {lvl} "
      f"{pid} (customer {cid})" + (" [validate_only]" if validate_only else "")
  )
  return propose("gads_add_negative_keywords", cid, summary, params, executor)


@mcp.tool(name="gads_remove_keywords", annotations=ANN_STATUS)
def gads_remove_keywords(
    customer_id: str,
    ad_group_id: str,
    criterion_ids: list[str],
    validate_only: bool = False,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Stages removal of keyword criteria from an ad group. Requires approval.

  Note: ad_group_id is required (a keyword criterion is addressed by ad group
  + criterion ID) — a small deviation from the spec which lists only
  criterion_ids.

  Args:
    customer_id: Google Ads customer ID (digits only).
    ad_group_id: Ad group the criteria belong to (digits only).
    criterion_ids: Criterion IDs to remove (digits only).
    validate_only: If True, the approved change runs as a dry-run.
    login_customer_id: Manager (MCC) ID if the account is managed.

  Returns:
    Pending change record.
  """
  cid = require_digits(customer_id, "customer_id")
  agid = require_digits(ad_group_id, "ad_group_id")
  if not criterion_ids:
    raise ToolError("Provide at least one criterion_id.")
  crit_ids = [require_digits(c, "criterion_id") for c in criterion_ids]
  params = dict(
      customer_id=cid, ad_group_id=agid, criterion_ids=crit_ids,
      validate_only=validate_only, login_customer_id=login_customer_id,
  )

  def executor():
    client = _get_client(login_customer_id)
    service = client.get_service("AdGroupCriterionService")
    operations = []
    for crit_id in crit_ids:
      resource_name = service.ad_group_criterion_path(cid, agid, crit_id)
      operations.append(
          service_types.AdGroupCriterionOperation(remove=resource_name)
      )
    try:
      response = service.mutate_ad_group_criteria(
          request=build_request(
              client, "MutateAdGroupCriteriaRequest", cid, operations,
              validate_only, partial_failure=True,
          )
      )
    except GoogleAdsException as e:
      _handle_google_ads_error(e)
    return multi_result(response, validate_only)

  summary = (
      f"Remove {len(crit_ids)} keyword(s) from ad group {agid} "
      f"(customer {cid})" + (" [validate_only]" if validate_only else "")
  )
  return propose("gads_remove_keywords", cid, summary, params, executor)


@mcp.tool(name="gads_set_targeting", annotations=ANN_CREATE)
def gads_set_targeting(
    customer_id: str,
    criteria: list[dict[str, Any]],
    campaign_id: str | None = None,
    ad_group_id: str | None = None,
    validate_only: bool = False,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Stages adding/removing geo, language, device, or audience criteria.

  Requires approval. Targets either a campaign or an ad group (provide exactly
  one of campaign_id / ad_group_id).

  Args:
    customer_id: Google Ads customer ID (digits only).
    criteria: List of dicts, each: {type, value, negative?}. ``type`` is one
      of geo (value = geo target constant ID), language (value = language
      constant ID), device (value = MOBILE/DESKTOP/TABLET), audience (value =
      user_list ID). ``negative`` (bool) excludes instead of includes.
    campaign_id: Campaign ID to target (digits only).
    ad_group_id: Ad group ID to target (digits only).
    validate_only: If True, the approved change runs as a dry-run.
    login_customer_id: Manager (MCC) ID if the account is managed.

  Returns:
    Pending change record.
  """
  cid = require_digits(customer_id, "customer_id")
  if bool(campaign_id) == bool(ad_group_id):
    raise ToolError("Provide exactly one of campaign_id or ad_group_id.")
  if not criteria:
    raise ToolError("Provide at least one criterion.")
  parent = "campaign" if campaign_id else "ad_group"
  pid = require_digits(campaign_id or ad_group_id, "parent_id")
  params = dict(
      customer_id=cid, criteria=criteria, campaign_id=campaign_id,
      ad_group_id=ad_group_id, validate_only=validate_only,
      login_customer_id=login_customer_id,
  )

  def _populate(criterion, ctype: str, value: str):
    t = ctype.strip().lower()
    if t == "geo":
      criterion.location.geo_target_constant = f"geoTargetConstants/{value}"
    elif t == "language":
      criterion.language.language_constant = f"languageConstants/{value}"
    elif t == "device":
      criterion.device.type_ = _resolve_enum(
          enum_types.DeviceEnum.Device, value, "device"
      )
    elif t == "audience":
      criterion.user_list.user_list = (
          f"customers/{cid}/userLists/{value}"
      )
    else:
      raise ToolError(
          f"Unsupported criterion type {ctype!r}. Use geo, language, device, "
          "or audience."
      )

  def executor():
    client = _get_client(login_customer_id)
    if parent == "campaign":
      service = client.get_service("CampaignCriterionService")
      parent_rn = service.campaign_path(cid, pid)
      operations = []
      for c in criteria:
        crit = resource_types.CampaignCriterion(campaign=parent_rn)
        if c.get("negative"):
          crit.negative = True
        _populate(crit, c.get("type", ""), str(c.get("value", "")))
        operations.append(
            service_types.CampaignCriterionOperation(create=crit)
        )
      request_type, method = "MutateCampaignCriteriaRequest", service.mutate_campaign_criteria
    else:
      service = client.get_service("AdGroupCriterionService")
      parent_rn = service.ad_group_path(cid, pid)
      operations = []
      for c in criteria:
        crit = resource_types.AdGroupCriterion(ad_group=parent_rn)
        if c.get("negative"):
          crit.negative = True
        _populate(crit, c.get("type", ""), str(c.get("value", "")))
        operations.append(
            service_types.AdGroupCriterionOperation(create=crit)
        )
      request_type, method = "MutateAdGroupCriteriaRequest", service.mutate_ad_group_criteria
    try:
      response = method(
          request=build_request(
              client, request_type, cid, operations, validate_only,
              partial_failure=True,
          )
      )
    except GoogleAdsException as e:
      _handle_google_ads_error(e)
    return multi_result(response, validate_only)

  summary = (
      f"Set {len(criteria)} targeting criteria on {parent} {pid} "
      f"(customer {cid})" + (" [validate_only]" if validate_only else "")
  )
  return propose("gads_set_targeting", cid, summary, params, executor)
