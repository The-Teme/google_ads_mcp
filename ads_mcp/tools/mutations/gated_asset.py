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

"""Approval-gated asset creation tools.

Image and YouTube video assets are reusable, account-level library objects that
Display, Demand Gen, Video, and Performance Max campaigns reference by resource
name. These propose_* tools stage asset creation for approval; nothing reaches
the Google Ads API until approve_change(change_id) runs.
"""

from __future__ import annotations

from typing import Any

from ads_mcp.coordinator import mcp_server as mcp
from ads_mcp.guardrails import validate_accounts
from ads_mcp.tools.mutations import asset_lib
from ads_mcp.tools.mutations.approval import propose


@mcp.tool()
def propose_create_image_asset(
    customer_id: str,
    name: str,
    image_base64: str,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Stages creation of an image asset for approval (see create_image_asset).

  Image bytes are validated immediately; the asset is created on approval.
  Call approve_change(change_id) to execute, then use the returned
  resource_name in a campaign builder.
  """
  customer_id, login_customer_id = validate_accounts(
      customer_id, login_customer_id
  )
  # Build now so invalid base64 / oversize images fail before staging.
  proto = asset_lib.build_image_asset(name, image_base64)

  def executor():
    return asset_lib.run_asset_create(customer_id, login_customer_id, proto)

  params = dict(customer_id=customer_id, name=name)
  summary = f"Create image asset '{name}' for customer {customer_id}"
  return propose("create_image_asset", customer_id, summary, params, executor)


@mcp.tool()
def propose_create_youtube_video_asset(
    customer_id: str,
    name: str,
    youtube_video_id: str,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Stages creation of a YouTube video asset (see create_youtube_video_asset).

  Call approve_change(change_id) to execute, then use the returned
  resource_name in a Video / Demand Gen / Performance Max campaign builder.
  """
  customer_id, login_customer_id = validate_accounts(
      customer_id, login_customer_id
  )
  proto = asset_lib.build_youtube_video_asset(name, youtube_video_id)

  def executor():
    return asset_lib.run_asset_create(customer_id, login_customer_id, proto)

  params = dict(
      customer_id=customer_id, name=name, youtube_video_id=youtube_video_id
  )
  summary = (
      f"Create YouTube video asset '{name}' (video {youtube_video_id}) for "
      f"customer {customer_id}"
  )
  return propose(
      "create_youtube_video_asset", customer_id, summary, params, executor
  )
