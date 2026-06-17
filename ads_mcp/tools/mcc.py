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

"""MCC (My Client Center / manager account) hierarchy tools.

These tools let you navigate and inspect multi-level Google Ads account trees.
All queries use the customer_client GAQL resource, which is only available
when querying from a manager (MCC) account.

Typical usage:
  1. Call list_accessible_accounts() (from accounts.py) to find your MCC IDs.
  2. Call list_mcc_child_accounts(mcc_id) to see direct and indirect children.
  3. Call get_account_hierarchy(mcc_id) to get the full tree as nested dicts.

MCC note: set login_customer_id = the top-level MCC ID in your google-ads.yaml
or pass it explicitly to each call. The customer_id in the query must also be
the MCC, not a leaf account.
"""

from __future__ import annotations

from typing import Any

from ads_mcp.coordinator import mcp_server as mcp
from ads_mcp.guardrails import validate_accounts
from ads_mcp.guardrails import validate_customer_id
from ads_mcp.tools._utils import get_ads_client
from fastmcp.exceptions import ToolError
from google.ads.googleads.errors import GoogleAdsException


def _gaql(mcc_id: str, query: str, login_customer_id: str | None = None):
  """Run a GAQL query scoped to an MCC account."""
  ads_client = get_ads_client()
  effective_login = login_customer_id or mcc_id
  ads_client.login_customer_id = effective_login
  service = ads_client.get_service("GoogleAdsService")
  try:
    stream = service.search_stream(query=query, customer_id=mcc_id)
    rows = []
    for batch in stream:
      for row in batch.results:
        rows.append({path: _extract(row, path) for path in batch.field_mask.paths})
    return rows
  except GoogleAdsException as e:
    raise ToolError("\n".join(str(err) for err in e.failure.errors)) from e


def _extract(row, path: str):
  obj = row
  for part in path.split("."):
    try:
      obj = getattr(obj, part)
    except AttributeError:
      return None
  if hasattr(obj, "name"):
    return obj.name
  return obj


# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------

@mcp.tool()
def list_mcc_child_accounts(
    mcc_id: str,
    include_hidden: bool = False,
) -> list[dict[str, Any]]:
  """Lists all accounts (direct and indirect children) under an MCC.

  Queries the customer_client resource which returns the full flattened
  list of accounts accessible from this manager account.

  Args:
    mcc_id: The manager account (MCC) customer ID — digits only.
    include_hidden: If True, include accounts marked as hidden. Default False.

  Returns:
    List of account dicts, each with id, descriptive_name, currency_code,
    time_zone, level (depth from MCC), manager (True if it's itself an MCC),
    and status.
  """
  mcc_id = validate_customer_id(mcc_id, "mcc_id")
  query = """
    SELECT
      customer_client.id,
      customer_client.descriptive_name,
      customer_client.currency_code,
      customer_client.time_zone,
      customer_client.level,
      customer_client.manager,
      customer_client.status,
      customer_client.hidden,
      customer_client.test_account
    FROM customer_client
    WHERE customer_client.level > 0
  """
  if not include_hidden:
    query += " AND customer_client.hidden = FALSE"
  query += " ORDER BY customer_client.level, customer_client.id"

  rows = _gaql(mcc_id, query)
  return [
      {
          "id": str(r.get("customer_client.id", "")),
          "name": r.get("customer_client.descriptive_name", ""),
          "currency": r.get("customer_client.currency_code", ""),
          "timezone": r.get("customer_client.time_zone", ""),
          "level": r.get("customer_client.level", 0),
          "is_manager": r.get("customer_client.manager", False),
          "status": r.get("customer_client.status", "UNKNOWN"),
          "hidden": r.get("customer_client.hidden", False),
          "test_account": r.get("customer_client.test_account", False),
      }
      for r in rows
  ]


@mcp.tool()
def get_account_hierarchy(mcc_id: str) -> dict[str, Any]:
  """Returns the full account tree under an MCC as nested dicts.

  Builds a tree by fetching all customer_client records and then nesting
  them by manager relationship using the customer_client_link resource.

  Args:
    mcc_id: The manager account (MCC) customer ID — digits only.

  Returns:
    Nested dict representing the account tree. Each node has:
      id, name, currency, timezone, is_manager, status, children (list).
    The root node is the MCC itself.
  """
  mcc_id = validate_customer_id(mcc_id, "mcc_id")
  # Fetch all accounts in the hierarchy
  accounts = list_mcc_child_accounts(mcc_id, include_hidden=True)

  # Fetch manager links to build parent→children mapping
  link_query = """
    SELECT
      customer_manager_link.client_customer,
      customer_manager_link.manager_customer,
      customer_manager_link.status
    FROM customer_manager_link
    WHERE customer_manager_link.status = ACTIVE
  """
  try:
    link_rows = _gaql(mcc_id, link_query)
  except ToolError:
    # customer_manager_link may not be available in all API versions — fall back
    # to a flat list with level-based nesting hint.
    link_rows = []

  # Build id → account dict
  account_map: dict[str, dict] = {
      mcc_id: {
          "id": mcc_id,
          "name": f"MCC {mcc_id}",
          "is_manager": True,
          "status": "ENABLED",
          "children": [],
      }
  }
  for acc in accounts:
    account_map[acc["id"]] = {**acc, "children": []}

  # Wire up parent→child relationships from link data
  if link_rows:
    children_by_manager: dict[str, list[str]] = {}
    for link in link_rows:
      manager_rn = link.get("customer_manager_link.manager_customer", "")
      client_rn = link.get("customer_manager_link.client_customer", "")
      manager_id = str(manager_rn).split("/")[-1] if manager_rn else ""
      client_id = str(client_rn).split("/")[-1] if client_rn else ""
      if manager_id and client_id:
        children_by_manager.setdefault(manager_id, []).append(client_id)

    for manager_id, child_ids in children_by_manager.items():
      if manager_id in account_map:
        for child_id in child_ids:
          if child_id in account_map:
            account_map[manager_id]["children"].append(account_map[child_id])
  else:
    # Fallback: attach level-1 accounts directly to root, nest deeper ones
    for acc in accounts:
      node = account_map[acc["id"]]
      if acc.get("level") == 1:
        account_map[mcc_id]["children"].append(node)

  return account_map[mcc_id]


@mcp.tool()
def get_account_summary(
    customer_id: str,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Returns basic details and settings for a single Google Ads account.

  Useful when working with a specific child account selected from the MCC tree.

  Args:
    customer_id: Google Ads customer ID (digits only).
    login_customer_id: MCC account ID if customer is managed.

  Returns:
    Dict with account name, currency, timezone, status, and manager flag.
  """
  customer_id, login_customer_id = validate_accounts(
      customer_id, login_customer_id
  )
  ads_client = get_ads_client()
  if login_customer_id:
    ads_client.login_customer_id = login_customer_id
  service = ads_client.get_service("GoogleAdsService")

  query = """
    SELECT
      customer.id,
      customer.descriptive_name,
      customer.currency_code,
      customer.time_zone,
      customer.status,
      customer.manager,
      customer.test_account,
      customer.auto_tagging_enabled,
      customer.tracking_url_template
    FROM customer
    LIMIT 1
  """
  try:
    stream = service.search_stream(query=query, customer_id=customer_id)
    for batch in stream:
      for row in batch.results:
        c = row.customer
        return {
            "id": str(c.id),
            "name": c.descriptive_name,
            "currency": c.currency_code,
            "timezone": c.time_zone,
            "status": c.status.name if hasattr(c.status, "name") else str(c.status),
            "is_manager": c.manager,
            "test_account": c.test_account,
            "auto_tagging_enabled": c.auto_tagging_enabled,
            "tracking_url_template": c.tracking_url_template,
        }
  except GoogleAdsException as e:
    raise ToolError("\n".join(str(err) for err in e.failure.errors)) from e

  raise ToolError(f"No account data returned for customer_id={customer_id}")
