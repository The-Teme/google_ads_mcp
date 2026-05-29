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

"""JSON-backed store for pending Google Ads change approvals.

Changes are written to ~/.google_ads_mcp/pending_changes.json.
The store is thread-safe via a threading.Lock.

Typical lifecycle:
  1. A mutation tool calls PendingStore.add(change) and returns the change_id.
  2. The user (or LLM) calls list_pending_changes() to review.
  3. approve_change(id) executes the stored callable and marks the change
     as APPROVED. reject_change(id) marks it REJECTED without executing.
"""

from __future__ import annotations

import dataclasses
import datetime
import json
import os
import pathlib
import threading
import uuid
from collections.abc import Callable
from typing import Any, Literal

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

ChangeStatus = Literal["pending", "approved", "rejected"]


@dataclasses.dataclass
class PendingChange:
  """A proposed Google Ads mutation waiting for approval."""

  change_id: str
  tool_name: str          # e.g. "create_search_campaign"
  customer_id: str
  summary: str            # human-readable description of what will happen
  params: dict[str, Any]  # the raw tool arguments for the record
  created_at: str         # ISO-8601
  status: ChangeStatus = "pending"
  result: Any = None      # populated after approval
  error: str | None = None

  def to_dict(self) -> dict[str, Any]:
    return dataclasses.asdict(self)

  @classmethod
  def from_dict(cls, d: dict[str, Any]) -> "PendingChange":
    return cls(**d)


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class PendingStore:
  """Thread-safe JSON store for PendingChange records.

  Usage::

    store = PendingStore()
    change_id = store.add(change)
    store.set_status(change_id, "approved", result={...})
  """

  _DEFAULT_PATH = pathlib.Path.home() / ".google_ads_mcp" / "pending_changes.json"

  def __init__(self, path: pathlib.Path | None = None) -> None:
    self._path = path or self._DEFAULT_PATH
    self._lock = threading.Lock()
    self._path.parent.mkdir(parents=True, exist_ok=True)
    if not self._path.exists():
      self._write({})

  # ------------------------------------------------------------------
  # Public API
  # ------------------------------------------------------------------

  def add(self, change: PendingChange) -> str:
    """Persist a new pending change and return its change_id."""
    with self._lock:
      data = self._read()
      data[change.change_id] = change.to_dict()
      self._write(data)
    return change.change_id

  def get(self, change_id: str) -> PendingChange | None:
    """Return a change by ID, or None if not found."""
    with self._lock:
      data = self._read()
    record = data.get(change_id)
    return PendingChange.from_dict(record) if record else None

  def list_all(self, status: ChangeStatus | None = None) -> list[PendingChange]:
    """Return all changes, optionally filtered by status."""
    with self._lock:
      data = self._read()
    changes = [PendingChange.from_dict(v) for v in data.values()]
    if status:
      changes = [c for c in changes if c.status == status]
    return sorted(changes, key=lambda c: c.created_at, reverse=True)

  def set_status(
      self,
      change_id: str,
      status: ChangeStatus,
      result: Any = None,
      error: str | None = None,
  ) -> PendingChange | None:
    """Update a change's status (and optionally its result/error)."""
    with self._lock:
      data = self._read()
      if change_id not in data:
        return None
      data[change_id]["status"] = status
      if result is not None:
        data[change_id]["result"] = result
      if error is not None:
        data[change_id]["error"] = error
      self._write(data)
    return PendingChange.from_dict(data[change_id])

  # ------------------------------------------------------------------
  # Internal helpers
  # ------------------------------------------------------------------

  def _read(self) -> dict[str, Any]:
    try:
      return json.loads(self._path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, FileNotFoundError):
      return {}

  def _write(self, data: dict[str, Any]) -> None:
    self._path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

# Override path via env var for testing / CI
_store_path = os.getenv("ADS_MCP_PENDING_STORE_PATH")
store = PendingStore(pathlib.Path(_store_path) if _store_path else None)


# ---------------------------------------------------------------------------
# Factory helper
# ---------------------------------------------------------------------------

def make_change(
    tool_name: str,
    customer_id: str,
    summary: str,
    params: dict[str, Any],
) -> PendingChange:
  """Create a new PendingChange with a generated ID and current timestamp."""
  return PendingChange(
      change_id=str(uuid.uuid4())[:8],
      tool_name=tool_name,
      customer_id=customer_id,
      summary=summary,
      params=params,
      created_at=datetime.datetime.now(datetime.UTC).isoformat(),
  )
