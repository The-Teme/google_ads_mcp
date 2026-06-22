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

"""Account & metadata tools (spec §1) — read-only.

  gads_list_accounts   – accessible customer accounts with name/currency/tz
  gads_get_account     – a single account's config
  gads_list_resources  – valid GAQL resources and their fields

These are always-on (no mutations). `customer_id` / `login_customer_id` are
explicit params, consistent with the rest of this server (the spec's
"from env only" guidance is intentionally relaxed for multi-account use).
"""

from __future__ import annotations

from typing import Any

from ads_mcp.coordinator import mcp_server as mcp
from ads_mcp.tools._utils import get_ads_client
from fastmcp.exceptions import ToolError
from google.ads.googleads.errors import GoogleAdsException

_READ = {"readOnlyHint": True, "idempotentHint": True}


def _search_rows(customer_id: str, query: str, login_customer_id: str | None):
  """Runs a GAQL query and yields raw GoogleAdsRow objects."""
  client = get_ads_client()
  if login_customer_id:
    client.login_customer_id = login_customer_id
  service = client.get_service("GoogleAdsService")
  try:
    stream = service.search_stream(query=query, customer_id=customer_id)
    rows = []
    for batch in stream:
      rows.extend(batch.results)
    return rows
  except GoogleAdsException as e:
    raise ToolError("\n".join(str(err) for err in e.failure.errors)) from e


@mcp.tool(name="gads_list_accounts", annotations=_READ)
def gads_list_accounts(
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Lists accessible Google Ads accounts with IDs, names, currency, timezone.

  Combines two sources: every account your credentials can reach
  (CustomerService.list_accessible_customers) enriched with descriptive
  metadata pulled from the manager account's customer_client tree. Accounts
  reachable but not under the manager are returned id-only.

  Args:
    login_customer_id: Manager (MCC) account ID to enumerate children from.
      Defaults to the login_customer_id configured in google-ads.yaml.

  Returns:
    Dict with ``accounts`` (list of {id, name, currency, timezone,
    is_manager, status, level, has_metadata}) and ``manager_id`` used.
  """
  client = get_ads_client()
  if login_customer_id:
    client.login_customer_id = login_customer_id
  manager_id = login_customer_id or getattr(client, "login_customer_id", None)

  # 1) All directly accessible customer IDs.
  customer_service = client.get_service("CustomerService")
  try:
    accessible = customer_service.list_accessible_customers().resource_names
  except GoogleAdsException as e:
    raise ToolError("\n".join(str(err) for err in e.failure.errors)) from e
  accessible_ids = [rn.split("/")[-1] for rn in accessible]

  # 2) Rich metadata for children of the manager account (best-effort).
  meta: dict[str, dict[str, Any]] = {}
  if manager_id:
    query = """
      SELECT
        customer_client.id,
        customer_client.descriptive_name,
        customer_client.currency_code,
        customer_client.time_zone,
        customer_client.manager,
        customer_client.status,
        customer_client.level
      FROM customer_client
    """
    try:
      for row in _search_rows(str(manager_id), query, str(manager_id)):
        c = row.customer_client
        meta[str(c.id)] = {
            "id": str(c.id),
            "name": c.descriptive_name,
            "currency": c.currency_code,
            "timezone": c.time_zone,
            "is_manager": c.manager,
            "status": c.status.name,
            "level": c.level,
            "has_metadata": True,
        }
    except ToolError:
      # Manager id isn't actually a manager, or no access — fall back below.
      pass

  accounts = []
  for cid in accessible_ids:
    if cid in meta:
      accounts.append(meta[cid])
    else:
      accounts.append({
          "id": cid,
          "name": None,
          "currency": None,
          "timezone": None,
          "is_manager": None,
          "status": None,
          "level": None,
          "has_metadata": False,
      })
  return {"accounts": accounts, "manager_id": str(manager_id) if manager_id else None}


@mcp.tool(name="gads_get_account", annotations=_READ)
def gads_get_account(
    customer_id: str,
    login_customer_id: str | None = None,
) -> dict[str, Any]:
  """Fetches a single account's config (currency, timezone, status, manager).

  Args:
    customer_id: Google Ads customer ID (digits only).
    login_customer_id: Manager (MCC) account ID if this account is managed.
      For a standalone account, pass its own ID (or omit and configure it in
      google-ads.yaml).

  Returns:
    Dict with id, name, currency, timezone, status, is_manager, test_account,
    auto_tagging_enabled, and tracking_url_template.
  """
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
  rows = _search_rows(customer_id, query, login_customer_id)
  if not rows:
    raise ToolError(f"No account data returned for customer_id={customer_id}")
  c = rows[0].customer
  return {
      "id": str(c.id),
      "name": c.descriptive_name,
      "currency": c.currency_code,
      "timezone": c.time_zone,
      "status": c.status.name,
      "is_manager": c.manager,
      "test_account": c.test_account,
      "auto_tagging_enabled": c.auto_tagging_enabled,
      "tracking_url_template": c.tracking_url_template,
  }


@mcp.tool(name="gads_list_resources", annotations=_READ)
def gads_list_resources(resource: str | None = None) -> dict[str, Any]:
  """Lists valid GAQL resources, or the fields of one resource.

  Helps build GAQL queries without guessing field names. With no argument it
  returns the list of queryable resources; with ``resource`` it returns that
  resource's fields and their attributes (data type, selectable, filterable,
  sortable).

  Args:
    resource: Optional resource name to introspect, e.g. "campaign" or
      "ad_group". When omitted, all resources are listed.

  Returns:
    Dict with ``resource`` (echoed filter or None) and ``fields``: a list of
    {name, category, data_type, selectable, filterable, sortable,
    is_repeated}.
  """
  client = get_ads_client()
  service = client.get_service("GoogleAdsFieldService")

  if resource:
    safe = resource.strip().replace("'", "")
    query = (
        "SELECT name, category, data_type, selectable, filterable, sortable, "
        f"is_repeated WHERE name LIKE '{safe}.%' ORDER BY name"
    )
  else:
    query = (
        "SELECT name, category, data_type, selectable, filterable, sortable "
        "WHERE category = RESOURCE ORDER BY name"
    )

  try:
    response = service.search_google_ads_fields(query=query)
    fields = []
    for f in response:
      fields.append({
          "name": f.name,
          "category": f.category.name,
          "data_type": f.data_type.name,
          "selectable": f.selectable,
          "filterable": f.filterable,
          "sortable": f.sortable,
          "is_repeated": f.is_repeated,
      })
  except GoogleAdsException as e:
    raise ToolError("\n".join(str(err) for err in e.failure.errors)) from e

  return {"resource": resource, "fields": fields}
