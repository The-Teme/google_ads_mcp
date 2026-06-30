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

"""Tests for server.py."""

import os
import sys
from unittest import mock

from ads_mcp import server


@mock.patch.dict(os.environ, {"USE_GOOGLE_OAUTH_ACCESS_TOKEN": "true"})
@mock.patch("ads_mcp.server.mcp_server")
@mock.patch("ads_mcp.server.verify_credentials_or_exit")
@mock.patch("ads_mcp.server.update_views_yaml", new_callable=mock.Mock)
def test_main_with_oauth_env(
    mock_update_views, mock_get_ads_client, mock_mcp_server
):
  """Tests main function with USE_GOOGLE_OAUTH_ACCESS_TOKEN set."""
  with mock.patch("ads_mcp.server.asyncio.run"):
    server.main()

  mock_update_views.assert_called_once()
  mock_get_ads_client.assert_called_once()
  mock_mcp_server.run.assert_called_once_with(
      transport="streamable-http",
      host="127.0.0.1",
      port=8000,
      show_banner=False,
  )
  # Verify auth set (hard to verify exact type without exposing it better,
  # but we can check if it was accessed/set if we mock it differently,
  # or just rely on coverage hitting the line)


@mock.patch("ads_mcp.server.mcp_server")
@mock.patch("ads_mcp.server.verify_credentials_or_exit")
@mock.patch("ads_mcp.server.update_views_yaml", new_callable=mock.Mock)
def test_main_refuses_insecure_http(
    mock_update_views, mock_get_ads_client, mock_mcp_server
):
  """main() must refuse streamable-http with no auth and no opt-in."""
  # pylint: disable=unused-argument
  mock_mcp_server.auth = None
  with mock.patch.dict(os.environ, {}, clear=True):
    with mock.patch("ads_mcp.server.asyncio.run"):
      try:
        server.main()
        assert False, "expected SystemExit"
      except SystemExit:
        pass
  mock_mcp_server.run.assert_not_called()


@mock.patch("ads_mcp.server.mcp_server")
@mock.patch("ads_mcp.server.verify_credentials_or_exit")
@mock.patch("ads_mcp.server.update_views_yaml", new_callable=mock.Mock)
def test_main_insecure_http_opt_in(
    mock_update_views, mock_get_ads_client, mock_mcp_server
):
  """ADS_MCP_ALLOW_INSECURE_HTTP=true lets the no-auth server start."""
  # pylint: disable=unused-argument
  mock_mcp_server.auth = None
  with mock.patch.dict(
      os.environ, {"ADS_MCP_ALLOW_INSECURE_HTTP": "true"}, clear=True
  ):
    with mock.patch("ads_mcp.server.asyncio.run"):
      server.main()
  mock_mcp_server.run.assert_called_once()


@mock.patch("ads_mcp.server.mcp_server")
@mock.patch("ads_mcp.server.verify_credentials_or_exit")
@mock.patch("ads_mcp.server.update_views_yaml", new_callable=mock.Mock)
def test_main_no_env(mock_update_views, mock_get_ads_client, mock_mcp_server):
  """Tests main function with no env vars."""
  # pylint: disable=unused-argument
  with mock.patch("ads_mcp.server.asyncio.run"):
    server.main()

  mock_mcp_server.run.assert_called_once()
  mock_get_ads_client.assert_called_once()


def test_mutations_disabled_by_default():
  """Tests that mutations are disabled by default."""
  # Clear module from sys.modules to force reload and re-evaluate env var
  if "ads_mcp.server" in sys.modules:
    del sys.modules["ads_mcp.server"]

  with mock.patch.dict(os.environ, {}, clear=True):
    # We need to mock get_ads_client and update_views_yaml to avoid actual calls
    with (
        mock.patch("ads_mcp.server.verify_credentials_or_exit"),
        mock.patch("ads_mcp.server.update_views_yaml"),
        mock.patch("ads_mcp.server.mcp_server"),
    ):
      import ads_mcp.server as server_module  # pylint: disable=import-outside-toplevel, reimported

      # Verify that mutation modules are NOT in tools
      tool_names = [t.__name__ for t in server_module.tools]
      assert "ads_mcp.tools.mutations.budget" not in tool_names
      assert "ads_mcp.tools.mutations.campaign" not in tool_names


def test_mutations_enabled_are_approval_only_by_default():
  """ADS_MCP_ENABLE_MUTATIONS=true registers gated tools, not direct ones."""
  if "ads_mcp.server" in sys.modules:
    del sys.modules["ads_mcp.server"]

  with mock.patch.dict(
      os.environ, {"ADS_MCP_ENABLE_MUTATIONS": "true"}, clear=True
  ):
    with (
        mock.patch("ads_mcp.server.verify_credentials_or_exit"),
        mock.patch("ads_mcp.server.update_views_yaml"),
        mock.patch("ads_mcp.server.mcp_server"),
    ):
      import ads_mcp.server as server_module  # pylint: disable=import-outside-toplevel, reimported

      tool_names = [t.__name__ for t in server_module.tools]
      # Gated + preview tools are registered.
      assert "ads_mcp.tools.mutations.gated_campaign" in tool_names
      assert "ads_mcp.tools.mutations.preview" in tool_names
      # Direct-execute tools are NOT registered by default.
      assert "ads_mcp.tools.mutations.budget" not in tool_names
      assert "ads_mcp.tools.mutations.campaign" not in tool_names


def test_direct_mutations_opt_in():
  """ADS_MCP_DIRECT_MUTATIONS=true registers the direct-execute tools."""
  if "ads_mcp.server" in sys.modules:
    del sys.modules["ads_mcp.server"]

  with mock.patch.dict(
      os.environ,
      {
          "ADS_MCP_ENABLE_MUTATIONS": "true",
          "ADS_MCP_DIRECT_MUTATIONS": "true",
      },
      clear=True,
  ):
    with (
        mock.patch("ads_mcp.server.verify_credentials_or_exit"),
        mock.patch("ads_mcp.server.update_views_yaml"),
        mock.patch("ads_mcp.server.mcp_server"),
    ):
      import ads_mcp.server as server_module  # pylint: disable=import-outside-toplevel, reimported

      tool_names = [t.__name__ for t in server_module.tools]
      assert "ads_mcp.tools.mutations.budget" in tool_names
      assert "ads_mcp.tools.mutations.campaign" in tool_names
