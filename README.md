# Google Ads MCP Server

The Google Ads MCP Server is an implementation of the Model Context Protocol (MCP) that enables Large Language Models (LLMs), such as Gemini, to interact directly with the Google Ads API.

> [!NOTE]
> This is NOT an officially supported Google product. It is mainly for experimental purposes and not intended for production use. Consider using the official [Google Ads MCP Server](https://github.com/google-ads/google-ads-mcp-python) instead.

## Disclaimer

Copyright Google LLC. Supported by Google LLC and/or its affiliate(s). This solution, including any related sample code or data, is made available on an “as is,” “as available,” and “with all faults” basis, solely for illustrative purposes, and without warranty or representation of any kind. This solution is experimental, unsupported and provided solely for your convenience. Your use of it is subject to your agreements with Google, as applicable, and may constitute a beta feature as defined under those agreements. To the extent that you make any data available to Google in connection with your use of the solution, you represent and warrant that you have all necessary and appropriate rights, consents and permissions to permit Google to use and process that data. By using any portion of this solution, you acknowledge, assume and accept all risks, known and unknown, associated with its usage and any processing of data by Google, including with respect to your deployment of any portion of this solution in your systems, or usage in connection with your business, if at all. With respect to the entrustment of personal information to Google, you will verify that the established system is sufficient by checking Google's privacy policy and other public information, and you agree that no further information will be provided by Google.

## Getting Started

Follow these instructions to configure and run the Google Ads MCP Server.

### 1. Configure Python Environment

#### For Direct Use

This project needs Python 3.12 with `pipx` or `uv`.

#### For Development

This project uses [`uv`](https://github.com/astral-sh/uv) for dependency management.

Install `uv` and then run the following command to install the required Python packages:

```bash
uv pip sync
```

### 2. Configure Google Ads credentials

This tool requires you to have a `google-ads.yaml` file with your Google Ads API credentials. By default, the application will look for this file in your home directory.

If you don't have one, you can generate it by running the following example from the `google-ads-python` library:
[authentication example](https://github.com/googleads/google-ads-python/blob/main/examples/authentication/generate_user_credentials.py)

Make sure your `google-ads.yaml` file contains the following keys:

- `client_id`
- `client_secret`
- `refresh_token`
- `developer_token`
- `login_customer_id` (optional, but recommended)

### 3. Configuration

The server can be configured using the following environment variables:

- `ADS_MCP_ENABLE_MUTATIONS`: Set to `true` to enable mutation tools. Defaults to `false`.
- `GOOGLE_ADS_CREDENTIALS`: Path to the `google-ads.yaml` file.
- `USE_GOOGLE_OAUTH_ACCESS_TOKEN`: Set to enable Google OAuth token verification.

### 4. Launch MCP Server

#### For Direct Use with Gemini CLI

Update your Gemini configuration to include the `google-ads-mcp` server. The following is an example of a local MCP server configuration:

```json5
{
  // Other configs...
  mcpServers: {
    GoogleAds: {
      command: "pipx",
      args: [
        "run",
        "--spec",
        "git+https://github.com/google-marketing-solutions/google_ads_mcp.git",
        "run-mcp-server",
      ],
      env: {
        GOOGLE_ADS_CREDENTIALS: "PATH_TO_YAML",
      },
      timeout: 30000,
      trust: false,
    },
  },
}
```

Once the server is running, you can interact with it using the Gemini CLI. Type `/mcp` in Gemini to see the `Google Ads API` server listed in the results.

#### For Local Development with Gemini CLI

Update your Gemini configuration to include the `google-ads-mcp` server. `[DIRECTORY]` will be the absolute path to the project. The following is an example of a local MCP server configuration:

```json5
{
  // Other configs...
  mcpServers: {
    GoogleAds: {
      command: "uv",
      args: ["run", "--directory", "[DIRECTORY]", "-m", "ads_mcp.server"],
      cwd: "[DIRECTORY]",
      timeout: 30000,
      trust: false,
    },
  },
}
```

Once the server is running, you can interact with it using the Gemini CLI. Type `/mcp` in Gemini to see the `Google Ads API` server listed in the results.

You can then ask questions like:

- "list all campaigns"
- "show me metrics for campaign `[CAMPAIGN_ID]`"
- "get all ad groups"

#### Direct Launch

To start the server directly, in the project path, run the following command:

```bash
uv run -m ads_mcp.server
```

The server will start and be ready to accept requests.

## Features and Tools

The server exposes tools for interacting with Google Ads. Some tools are read-only, while others allow mutations (modifications).

### Read-Only Tools (Always Available)

- **GAQL Execution**: Query Google Ads data using GAQL.
- **Account Management**: List accessible accounts.
- **MCC Navigation**: List child accounts, inspect account hierarchy, and get account summaries.
- **Documentation**: Access documentation for GAQL and reporting views.

#### Account & Metadata (`gads_*`)

Read-only (`R`), idempotent (`I`). Always available.

| Tool | Purpose | Key params | |
| --- | --- | --- | --- |
| `gads_list_accounts` | List accessible accounts with IDs, names, currency, timezone. | `login_customer_id?` | R, I |
| `gads_get_account` | Fetch a single account's config (currency, timezone, status, manager). | `customer_id`, `login_customer_id?` | R, I |
| `gads_list_resources` | List valid GAQL resources, or one resource's fields. | `resource?` | R, I |

#### Optimization & Planning — read tools (`gads_*`)

Read-only (`R`), idempotent (`I`). Always available. (The apply/dismiss tools are mutations — see below.)

| Tool | Purpose | Key params | |
| --- | --- | --- | --- |
| `gads_list_recommendations` | List Google's auto-recommendations for the account. | `customer_id`, `types?` | R, I |
| `gads_generate_keyword_ideas` | Keyword Planner ideas + search volume/competition. Requires Basic+ API access. | `customer_id`, `seed_keywords?` / `url?`, `geo_target_ids?`, `language_id?` | R, I |
| `gads_list_conversion_actions` | List configured conversion actions. | `customer_id` | R, I |
| `gads_list_assets` | List account assets (images, sitelinks, callouts). | `customer_id`, `asset_type?` | R, I |

#### Performance Reporting (`gads_*`)

Convenience wrappers over GAQL for everyday reporting. All are read-only (`R`)
and idempotent (`I`).

| Tool | Purpose | Key params | |
| --- | --- | --- | --- |
| `gads_run_gaql` | Run an arbitrary GAQL query. Covers nearly the whole read surface. | `customer_id`, `query`, `page_size?`, `page_token?` | R, I |
| `gads_get_campaign_performance` | Campaign metrics (impressions, clicks, cost, conversions, ROAS) over a date range. | `customer_id`, `date_range?` or `start_date?` / `end_date?`, `campaign_ids?` | R, I |
| `gads_get_ad_group_performance` | Same, at ad-group level. | `customer_id`, `date_range?`, `campaign_ids?` | R, I |
| `gads_get_ad_performance` | Same, at ad level, with creative fields (headlines, descriptions, final URLs). | `customer_id`, `date_range?`, `ad_group_ids?` | R, I |
| `gads_get_keyword_performance` | Keyword-level metrics + match type + Quality Score. | `customer_id`, `date_range?`, `ad_group_ids?` | R, I |
| `gads_get_search_terms` | Search-terms report (what people actually queried). | `customer_id`, `date_range?`, `campaign_ids?` | R, I |

**Conventions shared by these tools:**

- **`login_customer_id` (optional)** — every tool accepts this. When omitted,
  the `login_customer_id` from your `google-ads.yaml` is used. Set it to the
  manager (MCC) account ID when querying a managed client account, exactly as
  with `execute_gaql`.
- **`date_range`** — a predefined Google Ads range such as `LAST_7_DAYS`,
  `LAST_30_DAYS` (default), `THIS_MONTH`, or `LAST_MONTH`. For a custom window,
  pass `start_date` and `end_date` as `YYYY-MM-DD` instead (these take
  precedence over `date_range`).
- **Metrics** — monetary values are returned in account-currency units (micros
  are converted), and `roas` is derived as `conversions_value / cost`.
- **ID filters** — `campaign_ids` / `ad_group_ids` accept digit-only IDs and are
  validated before being used in the query.
- **`page_size`** — accepted by `gads_run_gaql` for compatibility but ignored;
  the Google Ads API fixes the page size at 10000 rows. Use `page_token`
  (returned as `next_page_token`) to page through results.

### Mutation Tools (Disabled by Default)

To enable these tools, set `ADS_MCP_ENABLE_MUTATIONS=true`.

The original direct-execute tools remain available (Campaign Budgets,
Campaigns, Ad Groups, Ads, Criteria), as do the `propose_*` approval-gated
tools and `preview_*` diff tools.

#### Approval-gated `gads_*` mutations (spec §3–§7)

All of the `gads_*` mutation tools below route through the **approval
workflow** — calling one stages a pending change and returns a `change_id`;
nothing hits the Google Ads API until you call `approve_change(change_id)`
(or discard it with `reject_change`). Use `list_pending_changes` to review.

Annotation shorthand: **R** = read-only, **D** = destructive, **I** = idempotent.

Two safety behaviours apply throughout:

- **`validate_only` (optional, default false)** — when the staged change is
  approved, it runs as a Google Ads API `validateOnly` dry-run (no
  persistence) and returns `{"validated_only": true}`. (`gads_apply_recommendation`
  is the exception — the API has no dry-run for it, so passing `validate_only`
  raises.)
- **New entities are created PAUSED.** Use a `gads_set_*_status` tool to go live.
- **Amounts are in micros** (1,000,000 micros = 1 currency unit).
- **`login_customer_id` (optional)** — manager (MCC) ID for managed accounts.

**Campaign structure (§3)**

| Tool | Purpose | Key params | |
| --- | --- | --- | --- |
| `gads_create_campaign` | Create a campaign (PAUSED). | `customer_id`, `name`, `channel_type`, `budget_id`, `bidding_strategy?`, `start_date?`, `end_date?`, `validate_only?` | not-R, not-D, not-I |
| `gads_update_campaign` | Update name and/or dates. | `customer_id`, `campaign_id`, `name?`, `start_date?`, `end_date?`, `validate_only?` | not-R, not-D, I |
| `gads_set_campaign_status` | Enable / pause / remove a campaign. | `customer_id`, `campaign_id`, `status`, `validate_only?` | not-R, D, I |
| `gads_create_ad_group` | Create an ad group (PAUSED). | `customer_id`, `campaign_id`, `name`, `cpc_bid_micros?`, `validate_only?` | not-R, not-D, not-I |
| `gads_update_ad_group` | Update name and/or CPC bid. | `customer_id`, `ad_group_id`, `name?`, `cpc_bid_micros?`, `validate_only?` | not-R, not-D, I |
| `gads_set_ad_group_status` | Enable / pause / remove an ad group. | `customer_id`, `ad_group_id`, `status`, `validate_only?` | not-R, D, I |

**Ads & creatives (§4)**

| Tool | Purpose | Key params | |
| --- | --- | --- | --- |
| `gads_create_responsive_search_ad` | Create an RSA (PAUSED). | `customer_id`, `ad_group_id`, `headlines[]`, `descriptions[]`, `final_urls[]`, `path1?`, `path2?`, `validate_only?` | not-R, not-D, not-I |
| `gads_update_ad` | Update an RSA's assets/URLs. | `customer_id`, `ad_id`, `headlines?`, `descriptions?`, `final_urls?`, `path1?`, `path2?`, `validate_only?` | not-R, not-D, I |
| `gads_set_ad_status` | Enable / pause / remove an ad. | `customer_id`, `ad_group_id`, `ad_id`, `status`, `validate_only?` | not-R, D, I |
| `gads_upload_image_asset` | Upload an image asset. | `customer_id`, `name`, `image_data?` (base64) / `url?`, `validate_only?` | not-R, not-D, not-I |

**Keywords & targeting (§5)**

| Tool | Purpose | Key params | |
| --- | --- | --- | --- |
| `gads_add_keywords` | Add keywords (ENABLED) to an ad group. | `customer_id`, `ad_group_id`, `keywords[]` (`{text, match_type, cpc_bid_micros?}`), `validate_only?` | not-R, not-D, not-I |
| `gads_add_negative_keywords` | Add negatives at ad-group or campaign level. | `customer_id`, `level`, `parent_id`, `keywords[]`, `match_type?`, `validate_only?` | not-R, not-D, I |
| `gads_remove_keywords` | Remove keyword criteria. | `customer_id`, `ad_group_id`, `criterion_ids[]`, `validate_only?` | not-R, D, I |
| `gads_set_targeting` | Add/remove geo, language, device, audience criteria. | `customer_id`, `campaign_id?` / `ad_group_id?`, `criteria[]` (`{type, value, negative?}`), `validate_only?` | not-R, not-D, not-I |

**Budgets & bidding (§6)**

| Tool | Purpose | Key params | |
| --- | --- | --- | --- |
| `gads_create_budget` | Create a campaign budget. | `customer_id`, `name`, `amount_micros`, `delivery_method?`, `validate_only?` | not-R, not-D, not-I |
| `gads_update_budget` | Change a budget's daily amount. | `customer_id`, `budget_id`, `amount_micros`, `validate_only?` | not-R, not-D, I |
| `gads_update_bidding_strategy` | Set campaign bidding (manual CPC, tCPA, tROAS, max conv/value, target spend). | `customer_id`, `campaign_id`, `strategy`, `target?`, `validate_only?` | not-R, not-D, I |

**Optimization & planning — apply (§7)**

| Tool | Purpose | Key params | |
| --- | --- | --- | --- |
| `gads_apply_recommendation` | Apply a recommendation. | `customer_id`, `recommendation_id` | not-R, not-D, not-I |
| `gads_dismiss_recommendation` | Dismiss a recommendation. | `customer_id`, `recommendation_id` | not-R, not-D, I |

> **A note on params:** the spec suggests reading `customer_id` / `login_customer_id`
> from env only. This server keeps them as explicit params (consistent with
> `execute_gaql` and the reporting tools) so multiple accounts and MCC clients
> can be addressed without reconfiguring. A few tools also require an extra
> parent ID the spec omits (e.g. `gads_set_ad_status` needs `ad_group_id`,
> `gads_remove_keywords` needs `ad_group_id`) because the underlying Google Ads
> resource is keyed by it.

## Contributing

We welcome contributions! Please see our [CONTRIBUTING.md](CONTRIBUTING.md) guide for details.

## License

Google Ads MCP Server is an open-source project licensed under the [APACHE-2.0 License](LICENSE).

## Contact

If you have any questions, suggestions, or feedback, please feel free to open an issue.
