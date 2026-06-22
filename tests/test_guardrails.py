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

"""Tests for ads_mcp.guardrails."""

import os
from unittest import mock

from ads_mcp import guardrails
from fastmcp.exceptions import ToolError
import pytest


def test_validate_customer_id_normalizes_dashes():
  assert guardrails.validate_customer_id("123-456-7890") == "1234567890"


def test_validate_customer_id_strips_whitespace():
  assert guardrails.validate_customer_id(" 1234567890 ") == "1234567890"


@pytest.mark.parametrize("bad", ["123", "12345678901", "abcdefghij", ""])
def test_validate_customer_id_rejects_bad_format(bad):
  with pytest.raises(ToolError):
    guardrails.validate_customer_id(bad)


def test_allowlist_blocks_unlisted_account():
  with mock.patch.dict(
      os.environ, {"ADS_MCP_ALLOWED_CUSTOMER_IDS": "111-222-3333"}, clear=True
  ):
    with pytest.raises(ToolError):
      guardrails.validate_customer_id("1234567890")


def test_allowlist_permits_listed_account_with_dashes():
  with mock.patch.dict(
      os.environ,
      {"ADS_MCP_ALLOWED_CUSTOMER_IDS": "1112223333,4445556666"},
      clear=True,
  ):
    assert guardrails.validate_customer_id("111-222-3333") == "1112223333"


def test_validate_accounts_returns_both_normalized():
  cid, lcid = guardrails.validate_accounts("123-456-7890", "222-333-4444")
  assert (cid, lcid) == ("1234567890", "2223334444")


def test_validate_accounts_allows_none_login():
  cid, lcid = guardrails.validate_accounts("1234567890")
  assert cid == "1234567890"
  assert lcid is None


def test_budget_cap_default_blocks_over_limit():
  with mock.patch.dict(os.environ, {}, clear=True):
    with pytest.raises(ToolError):
      guardrails.check_budget_micros(2_000_000_000)


def test_budget_cap_allows_under_limit():
  with mock.patch.dict(os.environ, {}, clear=True):
    guardrails.check_budget_micros(5_000_000)  # no raise


def test_budget_cap_rejects_negative():
  with pytest.raises(ToolError):
    guardrails.check_budget_micros(-1)


def test_budget_cap_disabled_with_zero():
  with mock.patch.dict(
      os.environ, {"ADS_MCP_MAX_BUDGET_MICROS": "0"}, clear=True
  ):
    guardrails.check_budget_micros(10_000_000_000)  # no raise


def test_budget_cap_custom_value():
  with mock.patch.dict(
      os.environ, {"ADS_MCP_MAX_BUDGET_MICROS": "5000000"}, clear=True
  ):
    guardrails.check_budget_micros(5_000_000)
    with pytest.raises(ToolError):
      guardrails.check_budget_micros(5_000_001)


def test_bid_cap_default_blocks_over_limit():
  with mock.patch.dict(os.environ, {}, clear=True):
    with pytest.raises(ToolError):
      guardrails.check_bid_micros(200_000_000)


def test_bid_cap_allows_under_limit():
  with mock.patch.dict(os.environ, {}, clear=True):
    guardrails.check_bid_micros(1_000_000)  # no raise


def test_invalid_cap_env_raises():
  with mock.patch.dict(
      os.environ, {"ADS_MCP_MAX_BUDGET_MICROS": "not-a-number"}, clear=True
  ):
    with pytest.raises(ToolError):
      guardrails.check_budget_micros(1)
