# Business Decision Agents — local app and live demos

One demo execution path: OpenAI agents → scoped MCP tools → deterministic financial models.
There is no offline run mode, mock-model CLI option, or direct-calculation HTTP endpoint.
Financial arithmetic still executes in Python through the Scenario agent's tools.

## Open the owner interface

From the repository root:

```bash
cd backend
../.venv/bin/uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000**. Choose a folder or individual files, ask a question,
review the extracted numbers, and read/save the calculated answer. No separate frontend
server, npm installation, or build is needed. See [frontend/README.md](../frontend/README.md).
Normal startup uses the root `.env`; OpenAI calls begin only when an analysis starts.
The API at `/docs` remains available. Run a single execution host per database.

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

Existing historical runs, financial formulas, and risk checks are preserved. The frontend
has been replaced by the minimal owner interface linked above.

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

Default limits now allow 32 turns per agent task, 96 model requests per run, 160 MCP
tool calls per run, and 600 seconds per execution/resume segment. The existing estimated
spending budget and context limit still apply. No paid evaluation was performed for this change, so real
extraction quality and large-batch behavior still require a live trial. Supported financial
questions remain supplier switching and one promotional event; organizing more kinds of
records does not add financial models.

### Recoverable extraction errors

Workspace batch writes return both `entries` (successful IDs) and `errors` (failed
entry indexes, codes, and repair guidance). Successful entries remain saved; correct
only the failed entries. Source quotations and locations must still match exactly.
Clarification/input MCP schemas enumerate canonical contract field names; use separate
questions for separate inputs, such as `current_shipping` and `new_shipping`.

When accumulated history reaches the existing context limit, the runner replaces older
complete tool exchanges with an explicitly abbreviated data summary, retaining the latest
response/tool-output exchange intact. Saved workspace records remain available through
tools. Compaction emits a `context_compacted` event; it does not increase the budget or
guarantee that oversized individual exchanges fit. Abbreviated quotes must be reread
before use as evidence. A previously `limit_reached` run stays unchanged; launch a new
run after updating the code.


### Avoiding repeated extraction and excessive tool calls

Agent task context now supplies the input contract, accepted/candidate facts, missing
fields, source inventory, and compact workspace summaries. For initial extraction it also
supplies up to 12,000 characters of source excerpts (first parts of text/PDF sources), with
source IDs and exact locations. This is partial coverage, not an assertion that all files
were read. Larger documents and tables remain accessible through MCP source tools.

The parser can propose up to 25 financial inputs with one `propose_workspace_inputs` MCP
call instead of a separate call for each input. A same-value proposal reuses an input
already confirmed by the user within that run; different values still need review.
The runner pauses as soon as a tool saves clarification questions, avoiding additional
model turns while waiting for the user. When all financial fields are confirmed and a
workspace exists, a paused extraction task is marked completed without another LLM
extraction pass. Completed extraction remains completed on subsequent clarification
resumes. Risk/scenario tasks are reset so confirmed changes receive fresh checks and math.
The orchestrator is instructed to use four specialist steps, with no separate confirmation
agent task. Existing compatible saved plans remain supported.

Execution limits can now be changed in the root `.env` (restart required):

```dotenv
MAX_AGENT_TURNS=32
MAX_RUN_CALLS=96
MAX_TOOL_CALLS=160
MAX_RUN_SECONDS=600
```

These are finite safeguards, not a guarantee that every batch finishes. Model/tool counts
remain cumulative across clarification resumes, and `RUN_BUDGET_USD` is unchanged. Runs
that previously reached a terminal limit retain that status; start a new analysis after
restarting the server. No paid live evaluation was performed for this change.


### POC supplier dataset v2

The coffee-shop records now explicitly define one supplier comparison unit as one pound
of roasted coffee: USD/unit = USD/lb and units/month = lb/month. The forward quantity
is 100 lb/month. The three months of historical exports are explicitly separated from
the 12-month forecast (November 2026 through October 2027). Both fictional suppliers
provide written fixed prices/delivery charges for that full period and 50–200 lb orders.
The proposed supplier's acceptance deadline is separate from the 12-month price term.
Prices, volumes, transition cost, POS history and event estimates remain numerically
unchanged. The reference supplier calculation projects $1,880 net savings over 12 months.
It is a conditional estimate, not a prediction of actual business performance.

For a fresh POC in the UI, start a new question and reselect
`backend/demo_data/coffee_shop`. Ask: “Would switching from Riverbend Roasters to Cedar
Crest save money over the next 12 months?” At review, confirm a 12-month horizon. Existing
uploads and blocked runs keep their original data; a previously confirmed value of 3
months is not silently overwritten by edited source files. CLI seeding detects the new
fixture fingerprint automatically. No financial formulas or risk checks were relaxed.

### Conditional financial results and operational caveats

The output is a conditional financial comparison, not a complete supplier-selection
recommendation. Unverified quality/reliability and assumed equivalent performance are
reported as informational limitations; uncertainty alone should not block displaying
calculated savings. Conflicting required inputs, omitted material costs, or known
constraints that invalidate the calculation still require review and can block it.
The risk agent classifies findings under these instructions; this is not automatic
verification of operational suitability. Completed reports include `risk_findings`,
which are displayed under “Keep these things in mind” and included in saved text answers.
Previously blocked runs are retained; restart the backend and create a new analysis
for updated agent instructions to apply. No further demo facts were invented to claim
that quality or reliability had been verified.
