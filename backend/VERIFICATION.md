# Minimal owner interface — October 28, 2026

- Backend suite: **91 passed** (27.05 seconds); frontend logic: **6 passed**.
- Static routes serve the interface and all assets alongside the existing API.
- Review regression verifies that correcting an extracted value rejects the old
  proposal and resolves duplicate questions rather than causing another review loop.
- Frontend logic covers conflicting candidates, explicit selection, percent conversion,
  validation, supported folder files, and human-readable financial values.
- JavaScript syntax checks and backend Ruff checks passed.
- Browser automation host was unavailable, so visual layout and browser end-to-end
  interaction remain unverified. No paid OpenAI request was made.

# Extraction error recovery — October 28, 2026

- Backend suite: **89 passed** (25.65 seconds); Ruff and compileall passed.
- Regression tests exercise mixed valid/invalid quotation batches, idempotent successful
  writes, canonical-field schema rejection and corrected shipping questions, and a
  13-request agent sequence that compacts context while preserving tool-call pairs.
- Batch errors now identify failed indexes and repair guidance while returning saved IDs.
- Canonical field enums prevent combined clarification fields in MCP requests.
- Context compaction is bounded and emits an event; existing limits remain enforced.
- Inspected the saved failed run without modifying it. No paid model request was made;
  live extraction accuracy and success after these changes remain unverified.

# Evidence workspace update — October 28, 2026

- Backend suite: **86 passed** (25.76 seconds); Ruff and compileall passed.
- Added real embedded MCP checks for workspace writes, exact source quotations,
  idempotency, search/pagination, role permissions, business/run isolation,
  unresolved-entry rejection, and preservation of assumed provenance/lineage.
- A provider-boundary test exercises organization → input candidate → user review →
  resume → deterministic calculation, retaining the workspace evidence chain.
- Folder ingestion tests cover mixed CSV/TXT input, unchanged-batch reuse,
  document-only seeding, and parse failure before business creation.
- Real uploads are now AI eligible as authorized. Prior explicitly ineligible records
  remain excluded. New demo seeds contain raw documents and no accepted facts.
- No paid model request was executed. Extraction quality, complete document coverage,
  live cost, and behavior on large unfamiliar batches have not been established.
- Financial formulas and supported question types remain unchanged.

Earlier verification describes preceding versions.

# Realistic business-record demo update — October 28, 2026

- Backend suite: **82 passed** (22.67 seconds); Ruff passed.
- Preview opened in headless Chrome and visually inspected: local source links,
  POS preview, complete invoice/email/owner-note content, and normalized fact table.
- Independent CSV reconciliation: $57,855.75 net sales, 11,478 lines, 8,297 receipts.
- Tests verify revenue after discounts/excluding tax, unknown product costs/margin,
  generic table retention without fake baseline metrics, source quotations/provenance,
  deterministic fixture rebuilding, versioned seeds, preservation of historical runs,
  validation before database writes, and scoped source-content retrieval.
- Supplier and event model base results remain $1,880 and $332.80 under the prepared,
  explicitly labeled input assumptions. Existing model/agent regression tests passed.
- No paid model call was launched. No general document-extraction capability is claimed.

Earlier verification below describes preceding versions.

# Evidence-reference error fix — October 28, 2026

- Backend suite: **76 passed** (3.73 seconds); Ruff passed.
- Actual embedded MCP regression checks confirm expected application failures return
  `is_error=True` without unexpected-exception tracebacks.
- Missing or inaccessible risk evidence returns `invalid_evidence_reference` with
  instructions to retrieve exact IDs. Invalid batches write no risk artifact.
- Tests cover correcting and resubmitting a reference, cross-business facts,
  cross-run artifacts, local-only sources, and a genuine internal exception that
  remains logged while its details stay out of model-facing results.
- Changed app/tools.py, prompts/risk.md and tests/test_tools.py. No financial formulas,
  acceptance rules, scope permissions, saved data or run limits were changed.
- No paid model run was launched. Live model recovery is prompted and supported by
  the tool response, not guaranteed by offline tests.

The earlier verification below describes the preceding live-only cleanup.

# Live-only update verification — October 28, 2026

- Backend automated suite: **71 passed** (6.49 seconds).
- `ruff check backend`: all checks passed.
- Configuration check: key configured, model gpt-6-luna, run mode live, research disabled, seeded-demo-only data policy, estimated budget $0.10/run. The key itself was not printed.
- Live CLI `--help`: only `--question` and help options; no offline/dry-run/simulated mode.
- No paid OpenAI request was launched or rerun during this cleanup.

Regression coverage includes fail-fast missing-key startup, rejection/removal of the old
standalone analysis route (404 and absent from OpenAPI), real embedded MCP execution,
financial calculations, review/resume, persistence, outcome tracking and scope enforcement.
New live-entry tests verify input/output exports, exclusion of credentials, and honest
blocked results without fabricated financial outputs.

Tests replace provider boundaries to avoid charges. These test doubles are not selectable
through application environment variables, HTTP, or the live CLI. They do not establish
real-model quality or guarantee that a live question completes without clarification.

## Exact scope of the cleanup

Changed runtime files:
- app/config.py: removed the live/offline setting; a key is required for normal startup.
- app/main.py: removed direct-analysis HTTP execution; health reports run_mode=live.
- app/llm.py: removed the disabled-mode branch; missing keys fail rather than falling back.
- app/contracts.py: removed the standalone AnalyzeRequest contract.
- scripts/check_configuration.py: reports live mode instead of an enablement toggle.
- scripts/live_demo.py: added --question, run-ID/input-path output, inputs.json/outputs.json
  exports and stopped-task reasons. Default question remains unchanged.
- ../.env.example: removed LIVE_API_CALLS_ENABLED; the user's private .env was not edited.

Deleted redundant alternate demo scripts:
- scripts/http_smoke.py (non-agent calculation demonstration).
- scripts/seed_demo.py (standalone seed helper; input seeding remains internal/API setup).

Updated tests and documentation. Financial engine, agent prompts, tool permissions,
source-data policy and existing database records were not changed. No auto-unblocking,
risk override, research provider, frontend change or full model-transcript recording was added.
