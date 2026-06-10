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

"""Optimization & planning mutations (spec §7) — approval-gated.

  gads_apply_recommendation     gads_dismiss_recommendation

(The read-only gads_list_recommendations lives in gads_reads.py.) Both stage
through the approval flow; apply also supports validate_only.
"""

from __future__ import annotations

from typing import Any

from ads_mcp.coordinator import mcp_server as mcp
from ads_mcp.tools.gads_mutations._common import ANN_CREATE
from ads_mcp.tools.gads_mutations._common import ANN_DISMISS
from ads_mcp.tools.gads_mutations._common import require_digits
from ads_mcp.tools.gads_mutations._common import _get_client
from ads_mcp.tools.gads_mutations._common import _handle_google_ads_error
from ads_mcp.tools.mutations.approval import propose
from fastmcp.exceptions import ToolError
from google.ads.googleads.errors import GoogleAdsException


def _recommendation_rn(client, customer_id: str, recommendation_id: str) -> str:
  """Resolves a recommendation resource name from an id or full resource name."""
  rid = recommendation_id.strip()
  if "/" in rid:
    return rid
  service = client.get_service("RecommendationService")
  return service.recommendation_path(customer_id, rid)


@mcp.tool(name="gads_apply_recommendation", annotations=ANN_CREATE)
def gads_apply_recommendation(
    customer_id: str,
    recommendation_id: str,
    validate_only: bool = False,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Stages applying a Google Ads recommendation. Requires approval.

  Args:
    customer_id: Google Ads customer ID (digits only).
    recommendation_id: A recommendation resource name (from
      gads_list_recommendations) or its bare ID.
    validate_only: Accepted for signature compatibility, but the Google Ads
      API has no dry-run for applying recommendations — passing True raises.
      The approval workflow is the safety gate here.
    login_customer_id: Manager (MCC) ID if the account is managed.

  Returns:
    Pending change record.
  """
  cid = require_digits(customer_id, "customer_id")
  if not recommendation_id.strip():
    raise ToolError("recommendation_id is required.")
  if validate_only:
    raise ToolError(
        "apply_recommendation does not support validate_only — the Google "
        "Ads API has no dry-run for applying recommendations. Review via the "
        "approval workflow (approve_change) instead."
    )
  params = dict(
      customer_id=cid, recommendation_id=recommendation_id,
      login_customer_id=login_customer_id,
  )

  def executor():
    client = _get_client(login_customer_id)
    service = client.get_service("RecommendationService")
    operation = client.get_type("ApplyRecommendationOperation")
    operation.resource_name = _recommendation_rn(client, cid, recommendation_id)
    request = client.get_type("ApplyRecommendationRequest")
    request.customer_id = cid
    request.operations.append(operation)
    try:
      response = service.apply_recommendation(request=request)
    except GoogleAdsException as e:
      _handle_google_ads_error(e)
    return {"resource_name": response.results[0].resource_name}

  summary = (
      f"Apply recommendation {recommendation_id} (customer {cid})"
      + (" [validate_only]" if validate_only else "")
  )
  try:
    return propose("gads_apply_recommendation", cid, summary, params, executor)
  except GoogleAdsException as e:  # pragma: no cover - defensive
    _handle_google_ads_error(e)


@mcp.tool(name="gads_dismiss_recommendation", annotations=ANN_DISMISS)
def gads_dismiss_recommendation(
    customer_id: str,
    recommendation_id: str,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Stages dismissing a Google Ads recommendation. Requires approval.

  Args:
    customer_id: Google Ads customer ID (digits only).
    recommendation_id: A recommendation resource name (from
      gads_list_recommendations) or its bare ID.
    login_customer_id: Manager (MCC) ID if the account is managed.

  Returns:
    Pending change record.
  """
  cid = require_digits(customer_id, "customer_id")
  if not recommendation_id.strip():
    raise ToolError("recommendation_id is required.")
  params = dict(
      customer_id=cid, recommendation_id=recommendation_id,
      login_customer_id=login_customer_id,
  )

  def executor():
    client = _get_client(login_customer_id)
    service = client.get_service("RecommendationService")
    operation = client.get_type("DismissRecommendationOperation")
    operation.resource_name = _recommendation_rn(client, cid, recommendation_id)
    request = client.get_type(
        "DismissRecommendationRequest"
    )
    request.customer_id = cid
    request.operations.append(operation)
    try:
      response = service.dismiss_recommendation(request=request)
    except GoogleAdsException as e:
      _handle_google_ads_error(e)
    return {"dismissed": response.results[0].resource_name}

  summary = f"Dismiss recommendation {recommendation_id} (customer {cid})"
  return propose("gads_dismiss_recommendation", cid, summary, params, executor)
