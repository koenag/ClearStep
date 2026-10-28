# Business Decision Agents — backend

A small FastAPI application with separate OpenAI agent executions, actual embedded MCP tools, provenance-aware input review, and deterministic financial calculations. Backend only; the previous frontend has deliberately not been changed or integrated with this API.

## Run

Python 3.11+ (tested on 3.13). From the repository root:

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
cd backend
../.venv/bin/uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/docs. Or run `bash scripts/dev.sh` from the repository root; this installs runtime dependencies and starts only the backend. Use one worker. `--reload` is optional for development; it interrupts active runs.

No key is needed to seed data, parse uploads, calculate financial scenarios, save decisions, or record outcomes. Live agent runs need an API key and explicit enablement. There is no fake/no-key agent in the application. Automated tests inject an explicitly simulated model while executing the real agent runner, MCP handlers, and financial engine.

## Configuration and keys

Copy the root `.env.example` to a root `.env`. Put the OpenAI key there, never in source files, prompts or chat:

```dotenv
OPENAI_API_KEY=your-private-key
OPENAI_MODEL=gpt-6-luna
LIVE_API_CALLS_ENABLED=false
RUN_BUDGET_USD=0.10
```

`.env` is ignored by Git. Shell variables override `.env`. `DATA_DIR` defaults to `backend/var`; `DATABASE_URL` optionally overrides the SQLite location. `CORS_ORIGINS` is an explicit comma-separated origin list. Research is hard-disabled; no search provider, search key, browser tool, or hosted OpenAI web-search fallback is configured.

Check configuration without any paid calls:

```bash
.venv/bin/python backend/scripts/check_configuration.py
```

To opt into live agent execution, set `LIVE_API_CALLS_ENABLED=true` and restart. A run is created only by an explicit `POST /api/runs` or the live script below. Startup does not invoke OpenAI. The model is `gpt-6-luna` using Responses API function calling and strict structured final output. Other model names are rejected until their pricing and compatibility are deliberately configured.

Pricing estimates use configured standard short-context rates of $0.10/M input tokens, $0.01/M cached input tokens and $0.50/M output tokens. The default estimated run budget is $0.10, not a guaranteed invoice ceiling. Each request reserves an estimate before execution; failed/unknown requests retain that reservation. Reported usage replaces the reservation. Automatic OpenAI retries are disabled. Limits also bound model calls (24), tool calls (60), agent turns (6), context size and run duration (300 seconds). These are application defaults in `config.py`, not claims about provider account limits. Billing, account model access, rate limits and live model behavior have not been verified by the offline tests.

Official references: [function calling](https://developers.openai.com/api/docs/guides/function-calling), [model/pricing](https://developers.openai.com/api/docs/models/gpt-6-luna), [MCP SDK](https://py.sdk.modelcontextprotocol.io/).

## Data policy

**Only server-seeded synthetic data is eligible for agent use.** Business creation cannot set the server-managed demo flag. Ordinary uploads are local-only even when attached to the fictional business. Source-reading tools reject ineligible sources, and agent context excludes them. Agent financial tools accept only eligible, explicitly accepted facts. Editable business profile text is not copied into agent context.

User query text and clarification answers are sent to the model for demo runs. The application cannot reliably detect real secrets or financial information typed into those fields. Use fictional queries and answers. This policy is enforced at application boundaries, not an OS sandbox. SQLite and source files are local and unencrypted. The service is unauthenticated and intended for a single user on loopback; it is not ready for public hosting or real multi-tenant records.

## Minimal architecture

```text
app/
  main.py                 App factory, lifecycle and HTTP routes
  config.py               Settings and safe domain errors
  contracts.py            Pydantic HTTP/agent/tool/financial contracts
  db.py                   Scoped SQLite JSON record store; optimistic writes
  data.py                 CSV/XLSX/TXT/text-PDF adapters and limits
  service.py              Sources, facts, review, calculations, decisions, actuals
  demo.py                 Server-controlled fictional sources and assumptions
  tools.py                Role allowlists, scoped MCP servers, OpenAI schema bridge
  llm.py                  OpenAI Responses adapter (lazy client, no automatic retries)
  agents.py               Separate context/history per task; bounded tool loop; usage
  workflow.py             Plan validation, dependency execution, pause/resume/recovery
  financial/engine.py     Pure Decimal supplier/event models and scenario generation
  services/ingestion.py   Sales normalization and deterministic baseline aggregation
  prompts/                Common rules and one instruction file per agent role
```

This intentionally consolidates the earlier implementation map. There are no separate services, task queue, vector store, OpenClaw dependency, agent framework, or unnecessary repository layers. Persisted business/source/fact/run/task/artifact/calculation/decision/outcome/event/usage records share one indexed JSON record table, with typed validation at application boundaries. Source and fact IDs preserve lineage; calculation and decision snapshots are not overwritten by actual outcomes. This new schema uses a new data directory and does not silently import the previous MVP database. There is no database migration framework yet; schema changes need an explicit migration plan. The retained financial implementation is version 2.0.0; future changes must retain compatible calculation code or explicitly migrate version support.

### Execution flow

1. API creates a run for the server-seeded demo business.
2. Orchestrator returns a typed plan; runtime rejects unsupported roles, cycles, unknown dependencies and excess steps. Unsupported questions return `unsupported` without fake calculations.
3. A supported plan has 4–8 steps: data extraction, a pre-simulation risk check, exactly one Scenario task, and a later risk review. Research cannot be scheduled.
4. Each task receives its own prompt, relevant dependency results and scoped MCP client/server. No task inherits another task's raw model conversation.
5. The OpenAI model requests a function call; the bridge checks the allowlist/schema, invokes MCP, and returns structured output. All response items needed for reasoning continuity are replayed in memory. Hidden reasoning is not recorded in application events.
6. Document-extracted numerical candidates remain unaccepted. Runtime pauses for review even if the parser mistakenly claims completion. Accept, reject, or supply a canonical-unit value through `/answers`.
7. Scenario tools require accepted fact IDs for **every** model input, including explicit default/sensitivity assumptions. They do not accept arbitrary numbers from the model. Missing inputs pause the run. Canonical units must already match; ambiguous conversions require user input.
8. Material `review_required` risk findings block completion. No arbitrary financial formulas or unsupported contract modeling are invented.
9. Final financial summary, scenario tables and chart-ready series come from the calculation snapshot. Orchestrator commentary is separate, model-generated qualitative text.
10. Saved decisions reference the selected scenario and original snapshot. Actual observations are stored separately.

Tasks execute serially for simplicity. Different runs have independent histories and scopes. A clarification answer resets execution tasks so downstream calculations are recomputed from the new fact versions; old calculation snapshots remain stored. Completed artifacts can be reused on failed/interrupted run retry. Facts changed since simulation are detected before publishing a report.

The runtime stores observable tasks, tool names, status changes, safe errors, and token usage. It does not store raw model reasoning or print keys. On restart, active runs become `interrupted`; retry is explicit. In-process jobs are not crash-durable workers. Shutdown cancels them cleanly. `limit_reached` and materially blocked runs cannot be silently restarted to evade limits.

### Agent tools

- **Orchestrator:** scoped context and artifact retrieval. Plans and synthesis are structured final outputs, not recursive agent calls inside an MCP handler.
- **Data Parser:** eligible sources/excerpts, facts, candidate submission and clarification requests.
- **Risk:** evidence/artifact retrieval, risk findings and clarification requests. No financial execution tools.
- **Scenario:** accepted facts/artifacts, deterministic supplier/event tools and clarification requests. No source mutation or candidate acceptance.
- **Research:** disabled; no external research tools or provider adapter.

MCP is embedded in memory through the installed SDK's actual protocol layer. It is not a direct Python function dispatcher pretending to be MCP. The bridge closes input schemas for OpenAI strict mode, validates calls locally, and scopes each server to one role and run. Moving to stdio/HTTP later requires explicit transport/authentication work; no public `/mcp` endpoint is exposed now.

## Files and baseline

Supported: UTF-8 CSV/TXT, XLSX, and text-based PDF. Maximum upload 5 MB, table 20,000 rows/100 columns, PDF 50 pages, extracted text 150,000 characters. Invalid rows produce warnings with ending CSV line numbers. Dates must be unambiguous ISO dates/datetimes. Duplicate normalized headers, missing required columns, NaN/infinite/negative quantities/prices, empty documents and invalid formats are rejected.

Sales schema:

```csv
date,product,quantity,unit_price,unit_cost
2026-08-01,Latte,15,5.50,1.80
```

Aliases include qty/price/cost/product_name/sale_date/order_id. Transaction counts require populated transaction IDs on all accepted rows; line items are never treated as unique transactions. Fixed expenses and net profit are unavailable. Monthly totals represent recorded dates without extrapolation. The latest uploaded sales file is a replacement baseline; uploads are not automatically merged.

For multi-sheet XLSX, send an explicit `sheet` form field. Formula cells are rejected: export calculated values first. Macros are not supported or executed. Expanded ZIP limits protect against oversized workbooks. TXT/PDF extraction preserves line/page references. PDF table extraction is best-effort text only; scanned and encrypted documents are unsupported. Ambiguous numerical extractions require explicit confirmation. Real uploaded content is parsed locally but remains inaccessible to agents under the current data policy.

## Financial conventions

Supplier purchasing: zero opening stock, constant monthly demand per scenario, order the greater of shortage and minimum order when needed, carry remaining inventory, FIFO consumption, shipping once per purchasing month. No storage/spoilage/financing costs or terminal resale credit. Cash spend and consumed inventory are kept separate. Effective annual cost escalation compounds monthly. Net benefit compares purchasing cash flows and subtracts switching cost once. ROI uses switching cost as its explicitly stated investment basis; zero investment yields undefined ROI. Payback must remain nonnegative for the rest of the horizon, so an early crossing reversed by a bulk order is not sustained break-even.

Event contribution: incremental visits × spend × margin, plus assumed retained customers' cumulative repeat contribution, minus event and additional staffing expenses once. Repeat purchase timing is not invented. Break-even visits round up. Scenarios are editable sensitivities, not calibrated probabilities or validated acquisition predictions.

All authoritative monetary arithmetic uses Decimal; API monetary outputs use ROUND_HALF_UP to cents. Small rounding differences can exist between rounded monthly lines and aggregate totals. Sales product units retain their quantity precision. USD only; no currency conversion. Procurement-unit demand is supplied explicitly, never inferred from café cups sold.

Actual supplier savings compare the original selected month's procurement savings before switching cost. Event actual contribution uses original margin × actual incremental revenue − actual total costs; blank repeat contribution leaves repeats pending and compares event-only figures. Explicit repeat contribution at the horizon compares against the full projection. If repeat contribution is observed before the horizon, variance is left null and the comparison is labeled not time-comparable; no monthly repeat forecast is invented. One observation per supplier month or one cumulative event observation is supported; editing/deleting observations is deferred. Attendance/revenue are user-attributed incremental figures, not proof of causality.

## API and demo

All stored objects use `{id, kind, business_id, run_id, revision, created_at, data}`. Errors use `{error: {code, message}}`. Request schemas and endpoint details are in `/docs`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Readiness, model, policy and disabled research |
| POST/GET | `/api/businesses` | Create/list local businesses |
| GET | `/api/businesses/{id}` | Business |
| POST | `/api/demo/seed` | Idempotently load the fictional café |
| POST/GET | `/api/businesses/{id}/sources` | Multipart upload/list metadata |
| GET | `/api/businesses/{id}/baseline` | Latest sales baseline |
| GET | `/api/businesses/{id}/facts` | Facts and review states |
| POST | `/api/businesses/{id}/analyses` | Deterministic structured-input analysis; no LLM |
| GET | `/api/calculations/{id}` | Original calculation and lineage |
| POST | `/api/runs` | Start a live agent run; returns 202 |
| GET | `/api/runs/{id}` | State, tasks, questions, report and usage |
| GET | `/api/runs/{id}/events` | Observable execution progress |
| POST | `/api/runs/{id}/answers` | Accept/reject candidates or supply values; resume when resolved |
| POST | `/api/runs/{id}/cancel` | Cancel an active/waiting run |
| POST | `/api/runs/{id}/retry` | Retry failed/interrupted work within existing limits |
| POST/GET | `/api/decisions` | Save/list original forecasts |
| GET/PATCH | `/api/decisions/{id}` | Reopen/update status |
| POST/GET | `/api/decisions/{id}/outcomes` | Record/list actual observations |

Start by invoking `POST /api/demo/seed` in `/docs`. Copy its business ID. `POST /api/businesses/{id}/analyses` accepts:

```json
{"decision_type":"supplier_switch","inputs":{"current_unit_cost":12,"new_unit_cost":10,"monthly_quantity":100,"current_shipping":40,"new_shipping":50,"switching_cost":400}}
```

Expected base result: $190 average monthly savings, $1,880 net benefit over 12 months, sustained payback in month 3. Save using `POST /api/decisions` with business_id, calculation_id and title. Record month 1 actual_savings of 175: variance −$15 versus the original $190. The event demo defaults yield $332.80 net benefit. Fictional sales: $72,793 revenue − $23,566 variable costs = $49,227 contribution profit; 15,235 units over July–September 2026.

A live run request is `{"business_id":"<seeded ID>","question":"Should I switch coffee bean suppliers?"}`. Ordinary created businesses are rejected by AI policy even with a key. Poll `/api/runs/{id}`. Clarification answers look like:

```json
{"answers":[{"question_id":"<id>","value":"9.50","unit":"USD/unit"}]}
```

For extracted candidates use `accept_candidate:true` or `reject_candidate:true` instead of a value. Multiple conflicting candidates can be accepted/rejected explicitly, but only one accepted value per field is allowed in an answer batch. Review is transactional.

## Tests

```bash
.venv/bin/pip install -r backend/requirements-dev.txt
cd backend
../.venv/bin/python -m pytest -q
cd ..
.venv/bin/ruff check backend
```

Unit/API tests use temporary databases and files. Agent tests use an explicit simulated model with real MCP discovery/invocation, permissions and calculations. OpenAI adapter tests use the installed SDK with mocked HTTP responses, including request serialization, sanitized errors and no automatic retry. No automated test makes a paid/provider request. Tests cover financial expectations, file types/limits, data policy, source evidence, review/conflicts, workflow dependencies, interruption/cancellation, usage estimates, persistence and actual outcomes.

An optional **paid live integration check** is available after configuring and explicitly enabling live calls:

```bash
.venv/bin/python backend/scripts/live_demo.py
```

This uses only the seeded fictional café. It is not run as part of this implementation's offline verification. It may stop for clarification or fail if the chosen model does not follow the contracts; inspect the run state rather than assume success. The token cost estimates do not guarantee model quality or account access.

## Deliberate limits

No frontend integration, OCR, database/accounting connectors, web research, autonomous financial actions, arbitrary decision models, production authentication, migrations, background worker infrastructure or durable distributed execution. No automatic plan-revision loop: invalid plans fail safely; clarification retries execute the same validated plan. Material unmodeled risk stops the run. Qualitative agent commentary is not fully fact-verifiable by deterministic code. Inspect output quality with live synthetic evaluations before considering broader use.

Detailed executed results are recorded in [VERIFICATION.md](VERIFICATION.md). To rerun the non-LLM HTTP smoke test against an already running server, use `.venv/bin/python backend/scripts/http_smoke.py` from the repository root. This creates fictional calculation/decision/outcome records but does not start agent runs.
