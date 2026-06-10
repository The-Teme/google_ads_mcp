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

"""Ads & creatives mutations (spec §4) — approval-gated.

  gads_create_responsive_search_ad   gads_set_ad_status
  gads_update_ad                     gads_upload_image_asset

(The read-only gads_list_assets lives in gads_reads.py.) New ads are created
PAUSED; all tools accept validate_only and stage through the approval flow.
"""

from __future__ import annotations

import base64
import urllib.request
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
from ads_mcp.tools.gads_mutations._common import require_digits
from ads_mcp.tools.gads_mutations._common import single_result
from ads_mcp.tools.gads_mutations._common import _get_client
from ads_mcp.tools.gads_mutations._common import _handle_google_ads_error
from ads_mcp.tools.gads_mutations._common import _resolve_enum
from ads_mcp.tools.mutations.approval import propose
from fastmcp.exceptions import ToolError
from google.ads.googleads.errors import GoogleAdsException
from google.protobuf import field_mask_pb2


@mcp.tool(name="gads_create_responsive_search_ad", annotations=ANN_CREATE)
def gads_create_responsive_search_ad(
    customer_id: str,
    ad_group_id: str,
    headlines: list[str],
    descriptions: list[str],
    final_urls: list[str],
    path1: str = "",
    path2: str = "",
    validate_only: bool = False,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Stages creation of a Responsive Search Ad (PAUSED). Requires approval.

  Args:
    customer_id: Google Ads customer ID (digits only).
    ad_group_id: Parent ad group ID (digits only).
    headlines: 3-15 headlines (max 30 chars each).
    descriptions: 2-4 descriptions (max 90 chars each).
    final_urls: Landing page URL(s).
    path1: Optional display-URL path1 (max 15 chars).
    path2: Optional display-URL path2 (max 15 chars).
    validate_only: If True, the approved change runs as a dry-run.
    login_customer_id: Manager (MCC) ID if the account is managed.

  Returns:
    Pending change record.
  """
  cid = require_digits(customer_id, "customer_id")
  agid = require_digits(ad_group_id, "ad_group_id")
  if not headlines or not descriptions or not final_urls:
    raise ToolError("headlines, descriptions, and final_urls are required.")
  params = dict(
      customer_id=cid, ad_group_id=agid, headlines=headlines,
      descriptions=descriptions, final_urls=final_urls, path1=path1,
      path2=path2, validate_only=validate_only,
      login_customer_id=login_customer_id,
  )

  def executor():
    client = _get_client(login_customer_id)
    service = client.get_service("AdGroupAdService")
    ad_group_service = client.get_service("AdGroupService")
    rsa = common_types.ResponsiveSearchAdInfo(
        headlines=[common_types.AdTextAsset(text=h) for h in headlines],
        descriptions=[common_types.AdTextAsset(text=d) for d in descriptions],
    )
    if path1:
      rsa.path1 = path1
    if path2:
      rsa.path2 = path2
    ad_group_ad = resource_types.AdGroupAd(
        ad_group=ad_group_service.ad_group_path(cid, agid),
        status=enum_types.AdGroupAdStatusEnum.AdGroupAdStatus.PAUSED,
        ad=resource_types.Ad(final_urls=list(final_urls), responsive_search_ad=rsa),
    )
    operation = service_types.AdGroupAdOperation(create=ad_group_ad)
    try:
      response = service.mutate_ad_group_ads(
          request=build_request(
              client, "MutateAdGroupAdsRequest", cid, [operation], validate_only
          )
      )
    except GoogleAdsException as e:
      _handle_google_ads_error(e)
    return single_result(response, validate_only)

  summary = (
      f"Create RSA (PAUSED) in ad group {agid} with {len(headlines)} "
      f"headlines / {len(descriptions)} descriptions (customer {cid})"
      + (" [validate_only]" if validate_only else "")
  )
  return propose(
      "gads_create_responsive_search_ad", cid, summary, params, executor
  )


@mcp.tool(name="gads_update_ad", annotations=ANN_UPDATE)
def gads_update_ad(
    customer_id: str,
    ad_id: str,
    headlines: list[str] | None = None,
    descriptions: list[str] | None = None,
    final_urls: list[str] | None = None,
    path1: str | None = None,
    path2: str | None = None,
    validate_only: bool = False,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Stages an update to a Responsive Search Ad's assets/URLs. Requires approval.

  Only the fields you pass are updated. (Updating RSA headlines/descriptions
  replaces the full list.)

  Args:
    customer_id: Google Ads customer ID (digits only).
    ad_id: Ad ID to update (digits only).
    headlines: Replacement headlines (optional).
    descriptions: Replacement descriptions (optional).
    final_urls: Replacement final URLs (optional).
    path1: New display-URL path1 (optional).
    path2: New display-URL path2 (optional).
    validate_only: If True, the approved change runs as a dry-run.
    login_customer_id: Manager (MCC) ID if the account is managed.

  Returns:
    Pending change record.
  """
  cid = require_digits(customer_id, "customer_id")
  adid = require_digits(ad_id, "ad_id")
  if all(v is None for v in (headlines, descriptions, final_urls, path1, path2)):
    raise ToolError(
        "Provide at least one of: headlines, descriptions, final_urls, "
        "path1, path2."
    )
  params = dict(
      customer_id=cid, ad_id=adid, headlines=headlines,
      descriptions=descriptions, final_urls=final_urls, path1=path1,
      path2=path2, validate_only=validate_only,
      login_customer_id=login_customer_id,
  )

  def executor():
    client = _get_client(login_customer_id)
    service = client.get_service("AdService")
    ad = resource_types.Ad(resource_name=service.ad_path(cid, adid))
    paths = []
    if final_urls is not None:
      ad.final_urls.extend(final_urls)
      paths.append("final_urls")
    if headlines is not None:
      ad.responsive_search_ad.headlines.extend(
          common_types.AdTextAsset(text=h) for h in headlines
      )
      paths.append("responsive_search_ad.headlines")
    if descriptions is not None:
      ad.responsive_search_ad.descriptions.extend(
          common_types.AdTextAsset(text=d) for d in descriptions
      )
      paths.append("responsive_search_ad.descriptions")
    if path1 is not None:
      ad.responsive_search_ad.path1 = path1
      paths.append("responsive_search_ad.path1")
    if path2 is not None:
      ad.responsive_search_ad.path2 = path2
      paths.append("responsive_search_ad.path2")
    operation = service_types.AdOperation(update=ad)
    operation.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=paths))
    try:
      response = service.mutate_ads(
          request=build_request(
              client, "MutateAdsRequest", cid, [operation], validate_only
          )
      )
    except GoogleAdsException as e:
      _handle_google_ads_error(e)
    return single_result(response, validate_only)

  summary = (
      f"Update ad {adid} (customer {cid})"
      + (" [validate_only]" if validate_only else "")
  )
  return propose("gads_update_ad", cid, summary, params, executor)


@mcp.tool(name="gads_set_ad_status", annotations=ANN_STATUS)
def gads_set_ad_status(
    customer_id: str,
    ad_group_id: str,
    ad_id: str,
    status: str,
    validate_only: bool = False,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Stages enabling, pausing, or removing an ad. Requires approval.

  Note: ads are addressed by ad_group_id + ad_id (the AdGroupAd resource), so
  both IDs are required (a small, necessary deviation from the spec which
  lists only ad_id).

  Args:
    customer_id: Google Ads customer ID (digits only).
    ad_group_id: Ad group ID the ad belongs to (digits only).
    ad_id: Ad ID (digits only).
    status: ENABLED, PAUSED, or REMOVED. REMOVED is destructive.
    validate_only: If True, the approved change runs as a dry-run.
    login_customer_id: Manager (MCC) ID if the account is managed.

  Returns:
    Pending change record.
  """
  cid = require_digits(customer_id, "customer_id")
  agid = require_digits(ad_group_id, "ad_group_id")
  adid = require_digits(ad_id, "ad_id")
  params = dict(
      customer_id=cid, ad_group_id=agid, ad_id=adid, status=status,
      validate_only=validate_only, login_customer_id=login_customer_id,
  )

  def executor():
    client = _get_client(login_customer_id)
    service = client.get_service("AdGroupAdService")
    ad_group_ad = resource_types.AdGroupAd(
        resource_name=service.ad_group_ad_path(cid, agid, adid),
        status=_resolve_enum(
            enum_types.AdGroupAdStatusEnum.AdGroupAdStatus, status, "status"
        ),
    )
    operation = service_types.AdGroupAdOperation(update=ad_group_ad)
    operation.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["status"]))
    try:
      response = service.mutate_ad_group_ads(
          request=build_request(
              client, "MutateAdGroupAdsRequest", cid, [operation], validate_only
          )
      )
    except GoogleAdsException as e:
      _handle_google_ads_error(e)
    return single_result(response, validate_only)

  summary = (
      f"Set ad {adid} (ad group {agid}) status -> {status.upper()} "
      f"(customer {cid})" + (" [validate_only]" if validate_only else "")
  )
  return propose("gads_set_ad_status", cid, summary, params, executor)


@mcp.tool(name="gads_upload_image_asset", annotations=ANN_CREATE)
def gads_upload_image_asset(
    customer_id: str,
    name: str,
    image_data: str | None = None,
    url: str | None = None,
    validate_only: bool = False,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Stages an image asset upload. Requires approval.

  Provide the image as base64 (``image_data``) or a fetchable ``url``.

  Args:
    customer_id: Google Ads customer ID (digits only).
    name: Asset name.
    image_data: Base64-encoded image bytes (optional if url given).
    url: Image URL to fetch (optional if image_data given).
    validate_only: If True, the approved change runs as a dry-run.
    login_customer_id: Manager (MCC) ID if the account is managed.

  Returns:
    Pending change record.
  """
  cid = require_digits(customer_id, "customer_id")
  if not image_data and not url:
    raise ToolError("Provide image_data (base64) or url.")
  params = dict(
      customer_id=cid, name=name, has_image_data=bool(image_data), url=url,
      validate_only=validate_only, login_customer_id=login_customer_id,
  )

  def executor():
    client = _get_client(login_customer_id)
    service = client.get_service("AssetService")
    if image_data:
      try:
        raw = base64.b64decode(image_data)
      except (ValueError, TypeError) as exc:
        raise ToolError(f"image_data is not valid base64: {exc}") from exc
    else:
      with urllib.request.urlopen(url) as resp:  # noqa: S310
        raw = resp.read()
    asset = resource_types.Asset(name=name)
    asset.image_asset.data = raw
    operation = service_types.AssetOperation(create=asset)
    try:
      response = service.mutate_assets(
          request=build_request(
              client, "MutateAssetsRequest", cid, [operation], validate_only
          )
      )
    except GoogleAdsException as e:
      _handle_google_ads_error(e)
    return single_result(response, validate_only)

  src = "base64" if image_data else f"url={url}"
  summary = (
      f"Upload image asset '{name}' ({src}) for customer {cid}"
      + (" [validate_only]" if validate_only else "")
  )
  return propose("gads_upload_image_asset", cid, summary, params, executor)
