# Business Decision Agents — live demos

One demo execution path: OpenAI agents → scoped MCP tools → deterministic financial models.
There is no offline run mode, mock-model CLI option, or direct-calculation HTTP endpoint.
Financial arithmetic still executes in Python through the Scenario agent's tools.

## Launch a live demo

From the repository root (`SmallBusinessConsultant`):

```bash
.venv/bin/pip install -r backend/requirements.txt
.venv/bin/python backend/scripts/check_configuration.py
.venv/bin/python backend/scripts/live_demo.py
```

If `.venv` does not exist, create it first with `python3 -m venv .venv`.

The repository-root `.env` must contain:

```dotenv
OPENAI_API_KEY=your-private-key
OPENAI_MODEL=gpt-6-luna
RUN_BUDGET_USD=0.10
```

Do not put the key in chat, source files, or command-line arguments. The old
`LIVE_API_CALLS_ENABLED` setting has been removed; an existing entry is ignored and
can be deleted. A key is required for normal startup. Every new agent run uses OpenAI
and may incur charges. Configuration checks and server startup do not invoke the model.

The live script automatically loads the fictional café, creates a new run, and waits
for completion or a stopped state. No API server is required for this command. The
existing database and previous runs are preserved; the script does not reset them.

To supply a different question:

```bash
.venv/bin/python backend/scripts/live_demo.py --question "Should I host a promotional event? Use the accepted fictional inputs."
```

The original default question is unchanged. If you want a financial simulation under
specified operational assumptions, explicitly provide those assumptions. For example:

```bash
.venv/bin/python backend/scripts/live_demo.py --question "Evaluate switching suppliers using the accepted fictional inputs. For this financial scenario, assume shipping is charged once per month in which an inventory purchase occurs; supplier quality and reliability are equivalent; no cancellation penalties or extra contractual obligations apply; and storage capacity is sufficient with no extra storage cost. Treat these as explicit fictional assumptions, disclose them, and do not present the simulation as a complete operational recommendation."
```

Only use assumptions you actually intend for the fictional scenario. Risk checks have
not been weakened: a live run can still block, ask for information, hit a limit, or fail.
The script returns exit code 0 only for `completed`, otherwise 1, and prints stopped-task
reasons. A completed financial report is not guaranteed by calling the live API.

## Inspect inputs and outputs

The script prints the run ID and absolute paths to:

```text
backend/var/runs/<run_id>/inputs.json
backend/var/runs/<run_id>/outputs.json
```

`DATA_DIR` changes the parent directory if configured.

- `inputs.json`: question, model, business ID, eligible source metadata and available facts at launch.
- `outputs.json`: saved run/report, all task results, questions, risk artifacts, calculations,
  events, and per-request usage estimates.
- Exact financial inputs and all scenario outputs are in `outputs.json → calculations[].data.analysis`.
- Original evidence IDs are in each calculation's `data.lineage`.
- Blocking risk descriptions are in `artifacts[].data.findings` and stopped task results.

These exports are not full model request/response transcripts. Raw tool arguments/results
and model reasoning are not newly recorded. Export files contain no API key. Only
AI-eligible demo sources/facts are exported as available inputs, even if local-only files
were uploaded to the same business.

To inspect a finished run through HTTP, start the API:

```bash
cd backend
../.venv/bin/uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/docs. Use the same `.env`, `DATA_DIR`, and database as the script.
Run one execution host at a time against a database: don't launch the CLI while another
process has an active analysis in that database. For server-hosted runs, use `POST /api/runs`.

Useful endpoints:

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Mode `live`, model, policy, limits |
| POST | `/api/demo/seed` | Initialize fictional input data; this does not execute an analysis |
| GET | `/api/businesses` | Find the fictional business ID |
| POST | `/api/runs` | Start a live analysis, returning 202 and its run ID |
| GET | `/api/runs/{id}` | Status, plan, tasks, questions, usage, final report |
| GET | `/api/runs/{id}/events` | Tool names and task transitions |
| POST | `/api/runs/{id}/answers` | Resolve clarification questions and resume |
| POST | `/api/runs/{id}/cancel` | Cancel an active/waiting run |
| POST | `/api/runs/{id}/retry` | Retry failed/interrupted work within existing limits |
| GET | `/api/businesses/{id}/facts` | Input facts and acceptance states |
| GET | `/api/businesses/{id}/sources` | Source metadata |
| GET | `/api/businesses/{id}/baseline` | Recorded sales baseline |
| GET | `/api/calculations/{id}` | Saved financial inputs, scenarios, lineage |
| POST/GET | `/api/decisions` | Save/list original forecasts |
| GET/PATCH | `/api/decisions/{id}` | Reopen/update status |
| POST/GET | `/api/decisions/{id}/outcomes` | Record/list actual outcomes |

A server-hosted run body is:

```json
{"business_id":"<seeded business ID>","question":"Should I switch coffee bean suppliers?"}
```

The CLI writes exports automatically; HTTP-created runs are inspected through the API
and persisted SQLite records. `blocked` remains terminal; it is not silently approved
or retried. Create a new run with clarified assumptions when appropriate.

## Architecture retained

- `config.py`: required key, model and execution limits.
- `main.py`: FastAPI factory, lifecycle and routes; no standalone analysis endpoint.
- `agents.py`, `llm.py`, `tools.py`: independent role contexts/history, real OpenAI Responses,
  actual embedded MCP discovery/invocation, role-specific allowlists, usage accounting.
- `workflow.py`: validated dependency plans, serial task execution, clarification/resume,
  cancellation, interruption recovery, and limits.
- `data.py`, `services/ingestion.py`, `service.py`: source parsing, baseline metrics, evidence
  review, accepted facts, calculation persistence and actual outcomes.
- `financial/engine.py`: Decimal supplier and event models. Python arithmetic is not a
  non-live demo mode; it is the authoritative tool implementation used by live agents.
- `db.py`: scoped SQLite JSON records and serialized short transactions.
- `demo.py`: controlled fictional business inputs, never canned agent responses.
- `prompts/`: common instructions and role-specific instructions. Research remains disabled.

The source store, existing runs, calculation semantics, prompts, financial engine,
review requirements, risk blocking, and frontend were not changed by the live-only update.

## Data policy and limits

Live refers to real API execution, not permission to transmit real business records.
Only server-seeded fictional data is AI-eligible. Ordinary uploads remain local-only.
CSV, XLSX, UTF-8 TXT, and text-based PDF parsing remain supported. No OCR, live database
connector, search provider, or hosted web-search fallback is configured. User query text
and clarification answers are sent to OpenAI, so use fictional content in those fields.

The backend is single-user, local-only and unauthenticated. Bind to loopback. SQLite/source
files are unencrypted. No production hosting, multi-tenancy, migrations or durable worker
queue is implemented. Background jobs interrupted by restart require explicit retry.

Financial inputs must have accepted provenance and canonical units. Numerical document
extractions require review. Missing/contradictory values are not silently invented. Risk
findings can block. Monthly event-repeat timing is not invented; partial repeat observations
are not given a misleading time-matched variance. Saved forecasts are not overwritten.

The default estimated budget remains $0.10/run, with request/tool/context/time limits.
Usage estimates are not invoice guarantees; failed requests may have unknown usage.
OpenAI account access and output quality require actual live evaluation. See
[official model pricing](https://developers.openai.com/api/docs/models/gpt-6-luna).

## Verification and tests

```bash
.venv/bin/pip install -r backend/requirements-dev.txt
cd backend
../.venv/bin/python -m pytest -q
cd ..
.venv/bin/ruff check backend
```

Automated tests still replace the provider boundary to avoid spending credits. Those test
fixtures are not an application/demo mode and cannot be selected through CLI, environment,
or HTTP. Tests exercise real MCP handlers, orchestration and calculations. Nothing silently
falls back to simulated responses in production. No paid run was launched as part of the
live-only cleanup. See [VERIFICATION.md](VERIFICATION.md).

Expected tool-validation failures are returned as MCP errors with their application
code and a safe message. For `invalid_evidence_reference`, the Risk agent must retrieve
facts/sources again and copy exact returned IDs before resubmitting. No findings are
saved for a failed submission. Out-of-scope references remain unavailable; genuine
internal bugs still produce diagnostic logs and a generic model-facing error.

## Revised, inspectable business-record demo

The current fixture bundle is documented in [demo_data/coffee_shop/README.md](demo_data/coffee_shop/README.md).
Open [the local preview](demo_data/coffee_shop/index.html) to see the raw records and
normalized inputs. It replaces the old generated daily product totals and single
assumptions file for **new** demo runs. Existing historical runs are preserved.

The bundle uses a receipt-level POS CSV without product costs, supplier invoice text
copies, a supplier quote email and informal owner notes. The POS baseline now leaves
COGS/profit/margin unavailable instead of inventing costs. Generic CSV/XLSX tables are
retained as evidence without inferring an unsupported financial baseline. Known POS
and legacy cost-enriched sales schemas receive deterministic aggregation.

Use `GET /api/businesses/{id}/sources/{source_id}` for the actual stored source contents.
The CLI prints the preview path and records the fixture version/fingerprint in inputs.json.
The fixture's explicit source-to-field index remains prepared demo wiring; general document
extraction, agent structure, financial formulas and supported decision types are unchanged.
