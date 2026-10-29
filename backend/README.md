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
.venv/bin/python backend/scripts/live_demo.py --question "Should I host a promotional event? Extract inputs from the supplied documents."
```

The default question now asks the parser to extract inputs and request review. If you want a financial simulation under
specified operational assumptions, explicitly provide those assumptions. For example:

```bash
.venv/bin/python backend/scripts/live_demo.py --question "Evaluate switching suppliers using the supplied documents. For this financial scenario, assume shipping is charged once per month in which an inventory purchase occurs; supplier quality and reliability are equivalent; no cancellation penalties or extra contractual obligations apply; and storage capacity is sufficient with no extra storage cost. Treat these as explicit fictional assumptions, disclose them, and do not present the simulation as a complete operational recommendation."
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
AI-eligible sources/facts are exported as available inputs. New uploads are eligible for
OpenAI analysis; older records explicitly marked ineligible remain excluded.

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

Existing historical runs, financial formulas, risk checks, and the frontend are preserved.

## Data policy and limits

Uploaded business files are now approved for agent analysis: relevant excerpts, questions,
and clarification answers may be sent to OpenAI. CSV, XLSX, UTF-8 TXT, and text-based PDF
remain supported. No OCR, live database connector, or web research is configured.
Previously stored sources marked ineligible stay excluded; reupload them if needed.

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

The raw fixture records are in [demo_data/coffee_shop](demo_data/coffee_shop).
They replace the old generated daily product totals and single assumptions file for
new demo runs. Existing historical runs are preserved.

The bundle uses a receipt-level POS CSV without product costs, supplier invoice text
copies, a supplier quote email and informal owner notes. The POS baseline now leaves
COGS/profit/margin unavailable instead of inventing costs. Generic CSV/XLSX tables are
retained as evidence without inferring an unsupported financial baseline. Known POS
and legacy cost-enriched sales schemas receive deterministic aggregation.

Use `GET /api/businesses/{id}/sources/{source_id}` for the actual stored source contents.
The CLI prints the input directory and records the fixture version/fingerprint in inputs.json.
The manifest's source-to-field index is reference material only: demo seeding no longer loads
it as accepted financial facts. Existing datasets/runs are retained; document-based demos
receive a separate business record.


## Run workspace and batches of files

The Data Parser now organizes relevant evidence into run-local JSON records in the existing
SQLite store. Each record contains subject, attribute, value, unit, period, status
(observed/assumed/uncertain/conflicting), notes, and exact source quotations. MCP tools
`save_workspace_entry` / `save_workspace_entries` write records; `query_workspace` searches
and paginates them. Only the parser writes; other agents can query. Evidence quotations
are checked against the scoped source, but this does not prove the interpretation is correct.
No vector database or generated SQL is used.

`propose_workspace_input` maps an organized record to a typed numerical candidate with
workspace lineage. Uncertain/conflicting records cannot be promoted. Candidates still
require user confirmation before deterministic calculation. The parser is required to
return a workspace artifact on completion. Organization is question-focused, not a guarantee
that every row in every file has been interpreted. Existing deterministic sales summaries
are available for supported table schemas.

Run a batch from the repository root:

```bash
.venv/bin/python backend/scripts/live_demo.py --input-folder "/absolute/path/to/records" --question "Would switching to Supplier B save money over 12 months?"
```

The folder is nonrecursive; only supported extensions are loaded. Unchanged batches reuse
the same source records. XLSX must contain one sheet for this CLI; use the upload API with
an explicit sheet for multi-sheet workbooks. Inputs are parsed before creating the business.
The default command still uses the coffee-shop documents, now without prefilled facts.

To upload through the API: create a business, POST each file to
`/api/businesses/{id}/sources`, then POST a run with that business ID. Inspect organized
records at `GET /api/runs/{id}/workspace?query=&offset=0&limit=10` or in the CLI export's
`outputs.json` → `workspace`. Query terms use case-insensitive substring AND matching,
not semantic search. Follow `next_offset` for more records. Raw records remain accessible
through the source endpoint. `outputs.json` also includes run-created facts and questions.

A first run will normally stop at `waiting_for_input` to review extracted numbers. Start
the API on the same database, GET the run's questions, and POST answers to
`/api/runs/{id}/answers`, for example:

```json
{"answers":[{"question_id":"question_...","accept_candidate":true}]}
```

Supply all open answers (or reject incorrect candidates); the existing workflow resumes
once all questions are answered. CLI exports are snapshots and do not refresh after API
resume. Accepted business facts can be reused on later runs; the workspace itself is scoped
to one run, survives pause/retry, and is retained for inspection rather than auto-deleted.
There is no cross-run organized-memory cache or automatic expiry.

Limits now allow 16 turns per agent and 48 model requests per run (previously 6 and 24)
to accommodate organizing documents and reviewing inputs. The existing cost, time, context,
and tool-call limits still apply. No paid evaluation was performed for this change, so real
extraction quality and large-batch behavior still require a live trial. Supported financial
questions remain supplier switching and one promotional event; organizing more kinds of
records does not add financial models.
