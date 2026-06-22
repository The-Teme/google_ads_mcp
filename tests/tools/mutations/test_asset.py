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

"""Tests for asset mutation tools and the shared asset library."""

import base64
from unittest import mock

from ads_mcp.tools.mutations import asset
from ads_mcp.tools.mutations import asset_lib
from fastmcp.exceptions import ToolError
import pytest

_PNG = base64.b64encode(b"fake-image-bytes").decode()


def test_build_image_asset_sets_data():
  proto = asset_lib.build_image_asset("logo", _PNG)
  assert proto.name == "logo"
  assert proto.image_asset.data == b"fake-image-bytes"


def test_build_image_asset_rejects_bad_base64():
  with pytest.raises(ToolError):
    asset_lib.build_image_asset("logo", "not!base64!")


def test_build_image_asset_rejects_oversize():
  big = base64.b64encode(b"x" * (asset_lib._MAX_IMAGE_BYTES + 1)).decode()
  with pytest.raises(ToolError):
    asset_lib.build_image_asset("logo", big)


def test_build_youtube_asset_rejects_url():
  with pytest.raises(ToolError):
    asset_lib.build_youtube_video_asset(
        "vid", "https://youtube.com/watch?v=abc"
    )


def test_build_youtube_asset_accepts_bare_id():
  proto = asset_lib.build_youtube_video_asset("vid", "dQw4w9WgXcQ")
  assert proto.youtube_video_asset.youtube_video_id == "dQw4w9WgXcQ"


@mock.patch("ads_mcp.tools.mutations.asset_lib._get_client")
def test_create_image_asset_success(mock_get_client):
  mock_client = mock.Mock()
  mock_get_client.return_value = mock_client
  mock_service = mock.Mock()
  mock_client.get_service.return_value = mock_service
  mock_response = mock.Mock()
  mock_response.results = [mock.Mock(resource_name="customers/1/assets/5")]
  mock_service.mutate_assets.return_value = mock_response

  result = asset.create_image_asset(
      customer_id="1234567890", name="logo", image_base64=_PNG
  )
  assert result == {"resource_name": "customers/1/assets/5"}
  mock_service.mutate_assets.assert_called_once()
