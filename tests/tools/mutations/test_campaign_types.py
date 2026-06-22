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

"""Tests for the direct and approval-gated campaign-type tools."""

from unittest import mock

from ads_mcp.tools.mutations import campaign_types
from ads_mcp.tools.mutations import gated_campaign_types
from ads_mcp.tools.mutations.approval import _executor_registry
from ads_mcp.tools.mutations.approval import approve_change

_CID = "1234567890"
_IMG = ["customers/1234567890/assets/100"]


@mock.patch("ads_mcp.tools.mutations.campaign_types.builders.execute_mutate")
@mock.patch("ads_mcp.tools.mutations.campaign_types._get_client")
def test_create_display_campaign_executes_mutate(mock_client, mock_execute):
  mock_execute.return_value = {"campaign_result": ["customers/1/campaigns/2"]}
  result = campaign_types.create_display_campaign(
      customer_id=_CID,
      name="D",
      budget_micros=5_000_000,
      final_url="https://x.com",
      headlines=["h1", "h2"],
      long_headline="lh",
      descriptions=["d1", "d2"],
      business_name="Biz",
      marketing_image_assets=_IMG,
      square_marketing_image_assets=_IMG,
  )
  assert result == {"campaign_result": ["customers/1/campaigns/2"]}
  mock_execute.assert_called_once()
  # The operation list passed to execute_mutate should be the 4-op display set.
  _client, cid, ops = mock_execute.call_args[0]
  assert cid == _CID
  assert len(ops) == 4


def test_propose_pmax_stages_without_executing():
  """propose_* must NOT touch the API; it only stages an executor."""
  with mock.patch(
      "ads_mcp.tools.mutations.gated_campaign_types.builders.execute_mutate"
  ) as mock_execute:
    staged = gated_campaign_types.propose_create_pmax_campaign(
        customer_id=_CID,
        name="P",
        budget_micros=5_000_000,
        final_url="https://x.com",
        headlines=["h1", "h2", "h3"],
        long_headlines=["lh"],
        descriptions=["d1", "d2"],
        business_name="Biz",
        marketing_image_assets=_IMG,
        square_marketing_image_assets=_IMG,
        logo_image_assets=_IMG,
    )
    mock_execute.assert_not_called()

  assert staged["status"] == "pending"
  assert staged["tool"] == "create_pmax_campaign"
  change_id = staged["change_id"]
  assert change_id in _executor_registry

  # Approving runs the staged executor, which calls execute_mutate exactly once.
  with (
      mock.patch("ads_mcp.tools.mutations.gated_campaign_types._get_client"),
      mock.patch(
          "ads_mcp.tools.mutations.gated_campaign_types.builders.execute_mutate"
      ) as mock_execute,
  ):
    mock_execute.return_value = {
        "campaign_result": ["customers/1/campaigns/9"]
    }
    approved = approve_change(change_id)
    mock_execute.assert_called_once()

  assert approved["status"] == "approved"
  assert approved["result"] == {"campaign_result": ["customers/1/campaigns/9"]}
