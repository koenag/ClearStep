# Backend verification

Executed October 28, 2026 with Python 3.13.7. Installed integration versions: MCP SDK 2.3.0, OpenAI SDK 2.54.0. Exact environment versions are recorded in requirements.lock.txt.

- `cd backend && ../.venv/bin/python -m pytest -q`: **68 passed**, repeated three consecutive times after the SQLite synchronization fix (1.57s, 1.52s, 1.61s).
- `.venv/bin/ruff check backend`: **all checks passed**.
- `.venv/bin/python -m compileall -q backend/app backend/scripts`: **passed**.
- `.venv/bin/pip check`: **no broken requirements**.
- `.venv/bin/python backend/scripts/check_configuration.py`: configuration valid, model gpt-6-luna, key absent, live calls disabled, research disabled, demo-only AI policy.
- Actual localhost HTTP smoke test: **passed** for health, seeding, reconciled sales baseline, supplier/event arithmetic, save/reopen, actual savings variance and OpenAPI.

Agent tests execute the actual embedded MCP protocol, role-specific tool permissions, financial handlers, and workflow runtime with an explicitly simulated model. The installed OpenAI SDK is exercised against mocked HTTP responses, not a paid provider call. Tests cover schema conversion, request serialization, incomplete output, error sanitization, and preservation/accounting of tool-loop state.

Coverage includes CSV/XLSX/TXT/text-PDF parsing, invalid/encrypted/scanned files, file/expansion limits, transaction semantics, source evidence, confirmation/rejection of conflicting candidates, scope/privacy enforcement, hand-calculated financial cases, dependency validation, clarification/resume, failed/interrupted retries, cancellation/timeouts, budget/tool limits, immutable forecasts, actual-outcome comparisons and SQLite persistence.

An intermittent native SQLite crash was found during concurrent background/HTTP test execution. Repository reads and transactions are now serialized with a reentrant lock; a regression test executes 100 write/read operations across eight threads. The final full suite passed three consecutive runs. No model/network request is performed while holding a repository transaction.

No live OpenAI call was made, no API key was read out or printed, no real uploaded records were transmitted, no search provider was configured, and no deployment was performed. Model account access and real-model planning/output quality remain unverified. Use scripts/live_demo.py only after deliberately configuring the key and enabling paid calls.

The frontend was not modified or tested. It uses the previous API and is not integrated with this backend.
