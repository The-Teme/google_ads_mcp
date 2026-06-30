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

"""Common utilities for Google Ads API MCP tools."""

import os
import sys
from ads_mcp.utils import ROOT_DIR
from fastmcp.server.dependencies import get_access_token
from google.ads.googleads.client import GoogleAdsClient
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
import yaml

_ADS_CLIENT: GoogleAdsClient | None = None


def get_ads_client() -> GoogleAdsClient:
  """Gets a GoogleAdsClient instance.

  Looks for an access token from the environment or loads credentials from
  a YAML file.

  Returns:
      A GoogleAdsClient instance.

  Raises:
      FileNotFoundError: If the credentials YAML file is not found.
  """
  global _ADS_CLIENT

  access_token = get_access_token()
  if access_token:
    access_token = access_token.token

  default_path = f"{ROOT_DIR}/google-ads.yaml"
  credentials_path = os.environ.get("GOOGLE_ADS_CREDENTIALS", default_path)
  if not os.path.isfile(credentials_path):
    raise FileNotFoundError(
        "Google Ads credentials YAML file is not found. "
        "Check [GOOGLE_ADS_CREDENTIALS] config."
    )

  if access_token:
    credentials = Credentials(access_token)
    with open(credentials_path, "r", encoding="utf-8") as f:
      ads_config = yaml.safe_load(f.read())
    return GoogleAdsClient(
        credentials,
        developer_token=ads_config.get("developer_token"),
        use_proto_plus=True,
    )

  if not _ADS_CLIENT:
    _ADS_CLIENT = GoogleAdsClient.load_from_storage(credentials_path)
    _ADS_CLIENT.use_proto_plus = (
        True  # Forced enable proto plus to avoid attribute issues.
    )

  return _ADS_CLIENT


def verify_credentials_or_exit() -> None:
  """Validates Google Ads credentials at startup with a clear failure message.

  The MCP client only sees a generic transport error (e.g. -32000) when the
  server process dies during boot, so an expired refresh token or a missing
  YAML otherwise surfaces as an opaque failure. This turns the two common
  credential problems into a plain-English message on stderr and a clean exit.
  """
  try:
    get_ads_client()
  except RefreshError as exc:
    print(
        "\n[google-ads MCP] OAuth credentials were rejected:\n"
        f"    {exc}\n\n"
        "Your refresh token is expired or revoked. Regenerate it:\n"
        "    uv run python regen_refresh_token.py\n"
        "Then restart / reconnect the MCP server. If this keeps happening every\n"
        "~7 days, publish your OAuth app to Production (Cloud Console -> OAuth\n"
        "consent screen) so refresh tokens stop expiring. See SECURITY.md.\n",
        file=sys.stderr,
    )
    sys.exit(1)
  except FileNotFoundError as exc:
    print(f"\n[google-ads MCP] {exc}\n", file=sys.stderr)
    sys.exit(1)
