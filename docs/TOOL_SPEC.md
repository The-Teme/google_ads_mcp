# Google Ads MCP Server — Tool Specification

A build spec for a Google Ads MCP server. Hand this to Claude Code as the
source of truth for which tools to implement and how they should behave.

## Stack & conventions

- **Language / SDK:** TypeScript with the MCP TypeScript SDK (`server.registerTool`), Zod for input schemas. (Python/FastMCP works too if you prefer.)
- **Transport:** stdio for local use; streamable HTTP (stateless JSON) if hosted remotely.
- **Auth:** Google Ads API OAuth2 + developer token. Read `customer_id`, `login_customer_id` (MCC), `developer_token`, and OAuth credentials from env / config — never as tool params.
- **Tool prefix:** `gads_` on every tool, action-oriented names.
- **Annotations** (set on every tool): `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`.
- **Output:** return both text content and `structuredContent` with a defined `outputSchema` where practical.

Annotation shorthand used below: **R** = readOnly, **D** = destructive, **I** = idempotent.

---

## 1. Account & metadata

| Tool | Purpose | Key params | Annotations |
|---|---|---|---|
| `gads_list_accounts` | List accessible customer accounts under the MCC, with IDs, names, currency, timezone. | _(none)_ | R, I |
| `gads_get_account` | Fetch a single account's config (currency, timezone, status, MCC parent). | `customer_id` | R, I |
| `gads_list_resources` | List valid GAQL resources and their fields, so the agent can build queries without guessing. | `resource?` (optional filter) | R, I |

## 2. Reporting (read layer — the workhorse)

| Tool | Purpose | Key params | Annotations |
|---|---|---|---|
| `gads_run_gaql` | Run an arbitrary GAQL query. Covers nearly the whole read surface. | `customer_id`, `query`, `page_size?`, `page_token?` | R, I |
| `gads_get_campaign_performance` | Convenience wrapper: campaign metrics (impressions, clicks, cost, conv, ROAS) over a date range. | `customer_id`, `date_range` or `start_date`/`end_date`, `campaign_ids?` | R, I |
| `gads_get_ad_group_performance` | Same, at ad-group level. | `customer_id`, `date_range`, `campaign_ids?` | R, I |
| `gads_get_ad_performance` | Same, at ad level, with creative fields. | `customer_id`, `date_range`, `ad_group_ids?` | R, I |
| `gads_get_keyword_performance` | Keyword-level metrics + match type + quality score. | `customer_id`, `date_range`, `ad_group_ids?` | R, I |
| `gads_get_search_terms` | Search-terms report (what people actually queried). | `customer_id`, `date_range`, `campaign_ids?` | R, I |

> All reporting tools must paginate (`page_size` / `page_token`) and return a `next_page_token` when more rows exist.

## 3. Campaign structure (mutations)

> Every mutating tool below must accept `validate_only?: boolean` (maps to the Google Ads API `validateOnly` flag) and create new entities **PAUSED** by default.

| Tool | Purpose | Key params | Annotations |
|---|---|---|---|
| `gads_create_campaign` | Create a campaign (PAUSED). | `customer_id`, `name`, `channel_type`, `budget_id`, `bidding_strategy`, `start_date?`, `end_date?`, `validate_only?` | not-R, not-D, not-I |
| `gads_update_campaign` | Update name, dates, bidding, network settings. | `customer_id`, `campaign_id`, fields…, `validate_only?` | not-R, not-D, I |
| `gads_set_campaign_status` | Enable / pause / remove a campaign. | `customer_id`, `campaign_id`, `status`, `validate_only?` | not-R, D (on remove), I |
| `gads_create_ad_group` | Create an ad group (PAUSED). | `customer_id`, `campaign_id`, `name`, `cpc_bid?`, `validate_only?` | not-R, not-D, not-I |
| `gads_update_ad_group` | Update ad group fields. | `customer_id`, `ad_group_id`, fields…, `validate_only?` | not-R, not-D, I |
| `gads_set_ad_group_status` | Enable / pause / remove an ad group. | `customer_id`, `ad_group_id`, `status`, `validate_only?` | not-R, D, I |

## 4. Ads & creatives (mutations)

| Tool | Purpose | Key params | Annotations |
|---|---|---|---|
| `gads_create_responsive_search_ad` | Create an RSA (PAUSED) with headlines/descriptions. | `customer_id`, `ad_group_id`, `headlines[]`, `descriptions[]`, `final_urls[]`, `path1?`, `path2?`, `validate_only?` | not-R, not-D, not-I |
| `gads_update_ad` | Update an existing ad's assets/URLs. | `customer_id`, `ad_id`, fields…, `validate_only?` | not-R, not-D, I |
| `gads_set_ad_status` | Enable / pause / remove an ad. | `customer_id`, `ad_id`, `status`, `validate_only?` | not-R, D, I |
| `gads_list_assets` | List account assets (images, sitelinks, callouts). | `customer_id`, `asset_type?` | R, I |
| `gads_upload_image_asset` | Upload an image asset. | `customer_id`, `image_data` (base64) or `url`, `name`, `validate_only?` | not-R, not-D, not-I |

## 5. Keywords & targeting (mutations)

| Tool | Purpose | Key params | Annotations |
|---|---|---|---|
| `gads_add_keywords` | Add keywords with match types to an ad group. | `customer_id`, `ad_group_id`, `keywords[]` (`{text, match_type, cpc_bid?}`), `validate_only?` | not-R, not-D, not-I |
| `gads_add_negative_keywords` | Add negatives at ad-group or campaign level. | `customer_id`, `level` (`ad_group`/`campaign`), `parent_id`, `keywords[]`, `validate_only?` | not-R, not-D, I |
| `gads_remove_keywords` | Remove keyword criteria. | `customer_id`, `criterion_ids[]`, `validate_only?` | not-R, D, I |
| `gads_set_targeting` | Add/remove geo, language, device, audience criteria. | `customer_id`, `campaign_id` or `ad_group_id`, `criteria[]`, `validate_only?` | not-R, not-D, not-I |

## 6. Budgets & bidding (mutations — the money levers)

| Tool | Purpose | Key params | Annotations |
|---|---|---|---|
| `gads_create_budget` | Create a (shared or campaign) budget. | `customer_id`, `name`, `amount_micros`, `delivery_method?`, `validate_only?` | not-R, not-D, not-I |
| `gads_update_budget` | Change a budget's daily amount. | `customer_id`, `budget_id`, `amount_micros`, `validate_only?` | not-R, not-D, I |
| `gads_update_bidding_strategy` | Set/update campaign bidding (tCPA, tROAS, max conv, manual CPC). | `customer_id`, `campaign_id`, `strategy`, `target?`, `validate_only?` | not-R, not-D, I |

## 7. Optimization & planning (read + apply)

| Tool | Purpose | Key params | Annotations |
|---|---|---|---|
| `gads_list_recommendations` | List Google's auto-recommendations for the account. | `customer_id`, `types?` | R, I |
| `gads_apply_recommendation` | Apply a recommendation. | `customer_id`, `recommendation_id`, `validate_only?` | not-R, not-D, not-I |
| `gads_dismiss_recommendation` | Dismiss a recommendation. | `customer_id`, `recommendation_id` | not-R, not-D, I |
| `gads_generate_keyword_ideas` | Keyword Planner ideas + search volume/competition. | `customer_id`, `seed_keywords[]` or `url`, `geo?`, `language?` | R, I |
| `gads_list_conversion_actions` | List configured conversion actions. | `customer_id` | R, I |

---

## Cross-cutting requirements (apply to all tools)

1. **`validate_only` everywhere it mutates.** Wire it to the Google Ads API `validateOnly` flag so any write can be dry-run first. This is the single most important safety feature — it spends real money otherwise.
2. **New entities default to PAUSED.** Require an explicit `gads_set_*_status` call to go live.
3. **`customer_id` is an explicit param on every tool**, never ambient state. Validate it against `gads_list_accounts`.
4. **Mutations config flag.** Support a `GADS_ENABLE_MUTATIONS` (default `false`) so the same server can run read-only until you trust it. When off, only sections 1, 2, and the read tools in 7 are registered.
5. **Surface partial failures.** Google Ads mutate calls can partially succeed — return per-operation results, not a single pass/fail.
6. **Pagination** on every list/report tool (`page_size`, `page_token`, `next_page_token`).
7. **Actionable errors.** Map Google Ads API error codes to messages that tell the agent what to fix (e.g. "budget_id not found — call gads_create_budget first").
8. **Amounts in micros.** Be explicit in descriptions that budgets/bids use micros (1 EUR = 1,000,000 micros) to avoid 1,000,000× mistakes.

## Suggested build order

1. **Phase 1 (read-only, zero risk):** sections 1 + 2, plus `gads_list_recommendations` and `gads_generate_keyword_ideas`. Genuinely useful on its own.
2. **Phase 2 (safe writes):** sections 3 + 6 with `validate_only` and paused-by-default working end to end.
3. **Phase 3:** sections 4, 5, and recommendation-apply.