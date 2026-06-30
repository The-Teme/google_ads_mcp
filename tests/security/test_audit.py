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

"""Tests for the append-only audit log."""

import json
import os
from unittest import mock

from ads_mcp.security import audit


def test_log_appends_one_record_per_call(tmp_path):
  log_path = tmp_path / "audit.log"
  with mock.patch.dict(
      os.environ, {"ADS_MCP_AUDIT_LOG_PATH": str(log_path)}
  ):
    audit.log("execute_gaql", {"customer_id": "123"}, "ok")
    audit.log("approve_change", {"change_id": "abcd1234"}, "ok")

  lines = log_path.read_text(encoding="utf-8").strip().splitlines()
  assert len(lines) == 2
  first = json.loads(lines[0])
  assert first["tool"] == "execute_gaql"
  assert first["customer_id"] == "123"
  assert first["status"] == "ok"
  assert "ts" in first


def test_log_truncates_long_values(tmp_path):
  log_path = tmp_path / "audit.log"
  with mock.patch.dict(
      os.environ, {"ADS_MCP_AUDIT_LOG_PATH": str(log_path)}
  ):
    audit.log("execute_gaql", {"query": "x" * 5000}, "ok")

  record = json.loads(log_path.read_text(encoding="utf-8").strip())
  assert len(record["args"]["query"]) < 5000
  assert "chars>" in record["args"]["query"]


def test_log_never_raises_on_bad_path():
  # A directory that cannot be created must not blow up the tool call.
  with mock.patch.dict(
      os.environ, {"ADS_MCP_AUDIT_LOG_PATH": "/proc/cannot/write/here.log"}
  ):
    audit.log("execute_gaql", {"customer_id": "123"}, "ok")  # no exception
