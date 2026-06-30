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

"""Tests for the audit-logging middleware."""

import asyncio
import json
import os
from types import SimpleNamespace
from unittest import mock

import pytest

from ads_mcp.security.middleware import SecurityMiddleware


def _context(name, arguments):
  return SimpleNamespace(
      message=SimpleNamespace(name=name, arguments=arguments)
  )


def test_middleware_logs_ok(tmp_path):
  log_path = tmp_path / "audit.log"
  mw = SecurityMiddleware()

  async def call_next(_context):
    return {"data": []}

  with mock.patch.dict(os.environ, {"ADS_MCP_AUDIT_LOG_PATH": str(log_path)}):
    result = asyncio.run(
        mw.on_call_tool(_context("execute_gaql", {"customer_id": "123"}),
                        call_next)
    )

  assert result == {"data": []}
  record = json.loads(log_path.read_text(encoding="utf-8").strip())
  assert record["tool"] == "execute_gaql"
  assert record["status"] == "ok"


def test_middleware_logs_error_and_reraises(tmp_path):
  log_path = tmp_path / "audit.log"
  mw = SecurityMiddleware()

  async def call_next(_context):
    raise RuntimeError("boom")

  with mock.patch.dict(os.environ, {"ADS_MCP_AUDIT_LOG_PATH": str(log_path)}):
    with pytest.raises(RuntimeError, match="boom"):
      asyncio.run(
          mw.on_call_tool(_context("propose_budget", {"customer_id": "123"}),
                          call_next)
      )

  record = json.loads(log_path.read_text(encoding="utf-8").strip())
  assert record["tool"] == "propose_budget"
  assert record["status"] == "error"
  assert "boom" in record["detail"]
