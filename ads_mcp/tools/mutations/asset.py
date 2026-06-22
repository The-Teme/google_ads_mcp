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

"""Direct-execute asset mutation tools for Google Ads API.

Image and YouTube video assets are account-level library objects that Display,
Demand Gen, Video, and Performance Max creatives reference by resource name.
Create the asset once here, then pass its resource_name to a campaign/ad
builder. These tools bypass the approval flow (OFF by default); the gated
equivalents live in gated_asset.py. The actual proto-building logic is shared
via asset_lib.py.
"""

from __future__ import annotations

from ads_mcp.coordinator import mcp_server as mcp
from ads_mcp.guardrails import validate_accounts
from ads_mcp.tools.mutations import asset_lib


@mcp.tool()
def create_image_asset(
    customer_id: str,
    name: str,
    image_base64: str,
    login_customer_id: str | None = None,
) -> dict[str, str]:
  """Creates an image asset from base64-encoded image bytes.

  The returned resource_name can be used in responsive display ads, Demand Gen
  ads, and Performance Max asset groups (as MARKETING_IMAGE,
  SQUARE_MARKETING_IMAGE, LOGO, etc.).

  Args:
      customer_id: Google Ads customer ID (digits only).
      name: A unique name for the asset in the account's asset library.
      image_base64: The image file contents, base64-encoded (PNG/JPG/GIF).
      login_customer_id: MCC account ID if customer is managed.

  Returns:
      Dict with the image asset resource_name.
  """
  customer_id, login_customer_id = validate_accounts(
      customer_id, login_customer_id
  )
  asset = asset_lib.build_image_asset(name, image_base64)
  return asset_lib.run_asset_create(customer_id, login_customer_id, asset)


@mcp.tool()
def create_youtube_video_asset(
    customer_id: str,
    name: str,
    youtube_video_id: str,
    login_customer_id: str | None = None,
) -> dict[str, str]:
  """Creates a YouTube video asset from a YouTube video ID.

  The returned resource_name is used by Video campaign ads and Demand Gen /
  Performance Max asset groups (as YOUTUBE_VIDEO).

  Args:
      customer_id: Google Ads customer ID (digits only).
      name: A unique name for the asset in the account's asset library.
      youtube_video_id: The YouTube video ID (the v= value in the URL, e.g.
        "dQw4w9WgXcQ"), not the full URL.
      login_customer_id: MCC account ID if customer is managed.

  Returns:
      Dict with the YouTube video asset resource_name.
  """
  customer_id, login_customer_id = validate_accounts(
      customer_id, login_customer_id
  )
  asset = asset_lib.build_youtube_video_asset(name, youtube_video_id)
  return asset_lib.run_asset_create(customer_id, login_customer_id, asset)
