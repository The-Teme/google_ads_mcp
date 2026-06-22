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

"""Asset-building helpers shared by the direct and gated asset tools.

This module defines NO MCP tools, so both asset.py (direct-execute) and
gated_asset.py (approval-gated) can import it without registering each other's
tools and defeating the env-var gating.

Image bytes are supplied as base64 by the caller rather than fetched from a URL
by the server. This is deliberate: a server-side URL fetch would let a prompt
injection point the MCP at an internal address (SSRF), which the rest of this
server is careful to avoid.
"""

from __future__ import annotations

import base64
import binascii

from ads_mcp.tools._ads_api import resource_types
from ads_mcp.tools._ads_api import service_types
from ads_mcp.tools.mutations.common import _get_client
from ads_mcp.tools.mutations.common import _handle_google_ads_error
from fastmcp.exceptions import ToolError
from google.ads.googleads.errors import GoogleAdsException

# Google Ads rejects image assets larger than a few MB; reject early with a
# clear message rather than after a round trip. Generous default.
_MAX_IMAGE_BYTES = 5_000_000


def _decode_image(image_base64: str) -> bytes:
  """Decode and size-check base64 image data."""
  try:
    data = base64.b64decode(image_base64, validate=True)
  except (binascii.Error, ValueError) as e:
    raise ToolError("image_base64 is not valid base64-encoded data.") from e
  if not data:
    raise ToolError("image_base64 decoded to zero bytes.")
  if len(data) > _MAX_IMAGE_BYTES:
    raise ToolError(
        f"Image is {len(data)} bytes, which exceeds the {_MAX_IMAGE_BYTES}-byte "
        "limit for image assets."
    )
  return data


def build_image_asset(name: str, image_base64: str):
  """Build (and validate) an image Asset proto from base64 image bytes."""
  data = _decode_image(image_base64)
  asset = resource_types.Asset(name=name)
  asset.image_asset.data = data
  return asset


def build_youtube_video_asset(name: str, youtube_video_id: str):
  """Build a YouTube video Asset proto from a bare video ID."""
  if (
      not youtube_video_id
      or "/" in youtube_video_id
      or "=" in youtube_video_id
  ):
    raise ToolError(
        "youtube_video_id must be the bare video ID (e.g. 'dQw4w9WgXcQ'), "
        "not a URL."
    )
  asset = resource_types.Asset(name=name)
  asset.youtube_video_asset.youtube_video_id = youtube_video_id
  return asset


def run_asset_create(customer_id, login_customer_id, asset):
  """Run a single AssetOperation create and return its resource_name."""
  ads_client = _get_client(login_customer_id)
  service = ads_client.get_service("AssetService")
  operation = service_types.AssetOperation(create=asset)
  try:
    response = service.mutate_assets(
        customer_id=customer_id, operations=[operation]
    )
  except GoogleAdsException as e:
    _handle_google_ads_error(e)
  return {"resource_name": response.results[0].resource_name}
