import asyncio
from dataclasses import replace

import pytest
from app.config import DomainError
from app.contracts import Answer, Plan, RunRequest
from app.workflow import validate_plan
from conftest import final, plan


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,expected", [("supplier_switch", 1880), ("promotional_event", 332.8)])
async def test_complete_agent_workflow_with_real_mcp(backend, seeded, kind, expected):
    app, client, model = backend
    services, b = seeded
    model.kind = kind
    executor = app.state.executor
    run = executor.create_run(
        RunRequest(
            business_id=b["id"],
            question="Should I switch suppliers?"
            if kind == "supplier_switch"
            else "Should I host an event?",
        )
    )
    await executor.execute(run["id"])
    result = services.store.get(run["id"])
    assert result["data"]["status"] == "completed", result["data"]
    assert result["data"]["report"]["analysis"]["scenarios"][1]["result"]["net_benefit"] == expected
    tasks = services.store.list("task", run_id=run["id"])
    assert [t["data"]["role"] for t in tasks] == [
        "orchestrator",
        "data_parser",
        "risk",
        "scenario",
        "risk",
        "orchestrator",
    ]
    assert all(t["data"]["status"] == "completed" for t in tasks)
    assert len(services.store.list("usage", run_id=run["id"])) == len(model.requests)
    assert any(
        e["data"].get("tool") == "get_facts" for e in services.store.list("event", run_id=run["id"])
    )
    # Each task starts with its own context; it never inherits other tasks' model history.
    starts = [r for r in model.requests if len(r["history"]) == 1]
    assert len(starts) == 6


@pytest.mark.asyncio
async def test_missing_input_pause_answer_resume(backend, seeded):
    app, client, model = backend
    services, b = seeded
    fact = next(
        f
        for f in services.eligible_facts(b["id"], "supplier_switch")
        if f["data"]["field"] == "new_unit_cost"
    )
    services.store.patch(fact, {"status": "superseded"})
    executor = app.state.executor
    run = executor.create_run(
        RunRequest(business_id=b["id"], question="Should I switch suppliers?")
    )
    await executor.execute(run["id"])
    paused = services.store.get(run["id"])
    assert paused["data"]["status"] == "waiting_for_input", paused["data"]
    q = services.store.list("question", run_id=run["id"])[0]
    resumed = services.answer_questions(
        paused, [Answer(question_id=q["id"], value=9, unit="USD/unit")]
    )
    assert resumed["data"]["status"] == "created"
    await executor.execute(run["id"])
    result = services.store.get(run["id"])
    assert result["data"]["status"] == "completed", result["data"]
    assert result["data"]["report"]["analysis"]["scenarios"][1]["result"]["net_benefit"] == 3080


@pytest.mark.asyncio
async def test_unsupported_question(backend, seeded):
    app, client, model = backend
    services, b = seeded
    model.kind = "unsupported"
    r = app.state.executor.create_run(
        RunRequest(business_id=b["id"], question="Should I hire an employee?")
    )
    await app.state.executor.execute(r["id"])
    assert services.store.get(r["id"])["data"]["status"] == "unsupported"
    assert services.store.list("calculation", run_id=r["id"]) == []


@pytest.mark.parametrize(
    "change", ["cycle", "unknown_dependency", "research", "no_risk_after", "duplicate", "no_data"]
)
def test_invalid_plans(change):
    p = plan()
    if change == "cycle":
        p["steps"][0]["depends_on"] = ["review"]
    if change == "unknown_dependency":
        p["steps"][1]["depends_on"] = ["missing"]
    if change == "research":
        p["steps"][0]["role"] = "research"
    if change == "no_risk_after":
        p["steps"][3]["role"] = "data_parser"
    if change == "duplicate":
        p["steps"][1]["id"] = "extract"
    if change == "no_data":
        p["steps"][0]["role"] = "risk"
    with pytest.raises(DomainError):
        validate_plan(Plan.model_validate(p))


@pytest.mark.asyncio
async def test_failure_and_recovery(backend, seeded):
    app, _, model = backend
    services, b = seeded
    r = app.state.executor.create_run(
        RunRequest(business_id=b["id"], question="Should I switch suppliers?")
    )

    async def broken(**kwargs):
        raise DomainError("model_unavailable", "Simulated unavailable provider.", 503)

    original = model.respond
    model.respond = broken
    await app.state.executor.execute(r["id"])
    assert services.store.get(r["id"])["data"]["error"]["code"] == "model_unavailable"
    model.respond = original
    await app.state.executor.execute(r["id"])
    assert services.store.get(r["id"])["data"]["status"] == "completed"
    services.store.patch(services.store.get(r["id"]), {"status": "running"})
    app.state.executor.recover()
    assert services.store.get(r["id"])["data"]["status"] == "interrupted"


@pytest.mark.asyncio
async def test_bounded_execution(backend, seeded):
    app, _, model = backend
    services, b = seeded
    services.settings = replace(services.settings, max_run_calls=1)
    r = app.state.executor.create_run(
        RunRequest(business_id=b["id"], question="Should I switch suppliers?")
    )
    await app.state.executor.execute(r["id"])
    assert services.store.get(r["id"])["data"]["status"] == "limit_reached"
    assert len(model.requests) == 1


@pytest.mark.asyncio
async def test_cancellation_and_timeout_are_not_internal_errors(backend, seeded):
    app, _, model = backend
    services, b = seeded
    started = asyncio.Event()

    async def slow(**kwargs):
        started.set()
        await asyncio.sleep(10)
        return final()

    model.respond = slow
    run = app.state.executor.create_run(
        RunRequest(business_id=b["id"], question="Should I switch suppliers?")
    )
    job = asyncio.create_task(app.state.executor.execute(run["id"]))
    await started.wait()
    services.store.patch(services.store.get(run["id"]), {"status": "canceled"})
    job.cancel()
    with pytest.raises(asyncio.CancelledError):
        await job
    assert services.store.get(run["id"])["data"]["status"] == "canceled"
    assert services.store.list("usage", run_id=run["id"])[0]["data"]["status"] == "unknown"
    services.settings = replace(services.settings, max_run_seconds=0.01)
    other = app.state.executor.create_run(
        RunRequest(business_id=b["id"], question="Should I switch suppliers?")
    )
    await app.state.executor.execute(other["id"])
    assert services.store.get(other["id"])["data"]["status"] == "limit_reached"


@pytest.mark.asyncio
async def test_tool_limit(backend, seeded):
    app, _, _ = backend
    services, b = seeded
    services.settings = replace(services.settings, max_tool_calls=0)
    run = app.state.executor.create_run(
        RunRequest(business_id=b["id"], question="Should I switch suppliers?")
    )
    await app.state.executor.execute(run["id"])
    assert services.store.get(run["id"])["data"]["status"] == "limit_reached"


@pytest.mark.asyncio
async def test_unreviewed_extraction_cannot_be_ignored(backend, seeded):
    app, _, _ = backend
    services, b = seeded
    from app.contracts import FactCandidate

    source = next(
        s
        for s in services.store.list("source", b["id"])
        if s["data"]["filename"] == "alternative_supplier_quote_email.txt"
    )
    services.submit_candidate(
        b["id"],
        FactCandidate(
            decision_type="supplier_switch",
            field="new_unit_cost",
            value="10",
            unit="USD/unit",
            source_id=source["id"],
            location=source["data"]["chunks"][0]["location"],
            evidence="(equivalent to $10.00 per lb).",
        ),
    )
    run = app.state.executor.create_run(
        RunRequest(business_id=b["id"], question="Should I switch suppliers?")
    )
    await app.state.executor.execute(run["id"])
    assert services.store.get(run["id"])["data"]["status"] == "waiting_for_input"
    assert services.store.list("calculation", run_id=run["id"]) == []


@pytest.mark.asyncio
async def test_plan_and_task_creation_are_atomic(backend, seeded, monkeypatch):
    app, _, _ = backend
    services, b = seeded
    original = services.store.create

    def fail(kind, data, *args, **kwargs):
        if kind == "task" and data.get("step_id") == "simulate":
            raise RuntimeError("Simulated database failure")
        return original(kind, data, *args, **kwargs)

    monkeypatch.setattr(services.store, "create", fail)
    run = app.state.executor.create_run(
        RunRequest(business_id=b["id"], question="Should I switch suppliers?")
    )
    await app.state.executor.execute(run["id"])
    assert services.store.get(run["id"])["data"]["plan"] is None
    assert not [
        t for t in services.store.list("task", run_id=run["id"]) if t["data"]["phase"] == "execute"
    ]
    monkeypatch.setattr(services.store, "create", original)
    await app.state.executor.execute(run["id"])
    assert services.store.get(run["id"])["data"]["status"] == "completed"
