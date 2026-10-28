import json
from dataclasses import replace
from decimal import Decimal

import pytest
from app.agents import AgentRunner
from app.config import DomainError, LimitReached
from app.contracts import Answer, FactCandidate, InputRef, Question
from app.tools import ToolScope, ToolSession, strict_schema
from conftest import plan


def make_scope(services, business, role="scenario"):
    run = services.store.create(
        "run",
        {"question": "Should I switch suppliers?", "plan": plan(), "status": "running"},
        business["id"],
    )
    task = services.store.create(
        "task",
        {
            "role": role,
            "phase": "execute",
            "objective": "Review fictional data.",
            "dependency_ids": [],
            "status": "running",
        },
        business["id"],
        run["id"],
    )
    return run, task, ToolScope(business["id"], run["id"], task["id"], role)


@pytest.mark.asyncio
async def test_actual_mcp_tools_and_calculation(seeded):
    services, b = seeded
    run, task, scope = make_scope(services, b)
    async with ToolSession(services, scope) as tools:
        assert "run_supplier_model" in tools.schemas
        assert "submit_fact_candidate" not in tools.schemas
        facts = (await tools.call("get_facts", {}))["facts"]
        result = await tools.call(
            "run_supplier_model",
            {"inputs": [{"field": f["data"]["field"], "fact_id": f["id"]} for f in facts]},
        )
        assert result["data"]["analysis"]["scenarios"][1]["result"]["net_benefit"] == 1880
        assert result["data"]["analysis"]["scenarios"][1]["result"]["break_even_month"] == 3
        again = await tools.call(
            "run_supplier_model",
            {"inputs": [{"field": f["data"]["field"], "fact_id": f["id"]} for f in facts]},
        )
        assert result["id"] == again["id"]
        with pytest.raises(DomainError, match="not available"):
            await tools.call("submit_risk_findings", {"findings": []})
        with pytest.raises(DomainError, match="schema"):
            await tools.call("get_facts", {"business_id": "someone_else"})
        wrong = await tools.call("run_event_model", {"inputs": []})
        assert wrong["error"]["code"] == "tool_failed"


@pytest.mark.asyncio
async def test_real_uploads_never_enter_model_context(backend, seeded):
    app, client, model = backend
    services, b = seeded
    local = services.upload(b["id"], "private.txt", b"PRIVATE_FINANCIAL_SENTINEL")
    run, task, scope = make_scope(services, b, "data_parser")
    async with ToolSession(services, scope) as tools:
        ctx = await tools.call("get_context", {})
        assert local["id"] not in json.dumps(ctx)
        assert "PRIVATE_FINANCIAL_SENTINEL" not in json.dumps(ctx)
        denied = await tools.call("read_source_excerpt", {"source_id": local["id"], "part": 0})
        assert denied["error"]["code"] == "tool_failed"
    from app.contracts import RunRequest

    fresh = app.state.executor.create_run(
        RunRequest(business_id=b["id"], question="Should I switch suppliers?")
    )
    await app.state.executor.execute(fresh["id"])
    assert services.store.get(fresh["id"])["data"]["status"] == "completed"
    assert "PRIVATE_FINANCIAL_SENTINEL" not in json.dumps(model.requests)


@pytest.mark.asyncio
async def test_candidate_requires_review_and_preserves_original_facts(seeded):
    services, b = seeded
    run, task, scope = make_scope(services, b, "data_parser")
    source = next(s for s in services.store.list("source", b["id"]) if s["data"]["format"] == "txt")
    chunk = source["data"]["chunks"][0]
    candidate = services.submit_candidate(
        b["id"],
        FactCandidate(
            decision_type="supplier_switch",
            field="new_unit_cost",
            value="10",
            unit="USD/unit",
            source_id=source["id"],
            location=chunk["location"],
            evidence="new_unit_cost = 10 USD/unit",
        ),
    )
    assert candidate["data"]["status"] == "candidate"
    refs = [
        InputRef(field=f["data"]["field"], fact_id=f["id"])
        for f in services.eligible_facts(b["id"], "supplier_switch")
        if f["data"]["status"] == "accepted" and f["data"]["field"] != "new_unit_cost"
    ] + [InputRef(field="new_unit_cost", fact_id=candidate["id"])]
    with pytest.raises(DomainError, match="accepted"):
        services.calculate_from_facts(b["id"], run["id"], "supplier_switch", refs)
    q = services.new_question(
        run,
        Question(
            field="new_unit_cost", reason="Review the extraction.", candidate_id=candidate["id"]
        ),
        task["id"],
    )
    services.store.patch(task, {"status": "needs_input"})
    run = services.store.patch(run, {"status": "waiting_for_input"})
    services.answer_questions(run, [Answer(question_id=q["id"], accept_candidate=True)])
    assert services.store.get(candidate["id"])["data"]["status"] == "confirmed"
    accepted = [
        f
        for f in services.eligible_facts(b["id"], "supplier_switch")
        if f["data"]["field"] == "new_unit_cost" and f["data"]["status"] == "accepted"
    ]
    assert len(accepted) == 1 and accepted[0]["data"]["confirmed_by_user"] is True
    assert accepted[0]["data"]["provenance"] == "observed"


def test_fake_evidence_and_bad_units_rejected(seeded):
    services, b = seeded
    source = next(s for s in services.store.list("source", b["id"]) if s["data"]["format"] == "txt")
    base = dict(
        decision_type="supplier_switch",
        field="new_unit_cost",
        value="10",
        unit="USD/unit",
        source_id=source["id"],
        location=source["data"]["chunks"][0]["location"],
        evidence="does not exist",
    )
    with pytest.raises(DomainError, match="exact excerpt"):
        services.submit_candidate(b["id"], FactCandidate(**base))
    base["unit"] = "USD/kg"
    with pytest.raises(DomainError, match="canonical unit"):
        services.submit_candidate(b["id"], FactCandidate(**base))


@pytest.mark.asyncio
async def test_cross_run_artifact_denied(seeded):
    services, b = seeded
    run, task, scope = make_scope(services, b)
    other = services.store.create("artifact", {"sensitive": "other run"}, b["id"], "different_run")
    async with ToolSession(services, scope) as tools:
        result = await tools.call("get_artifact", {"artifact_id": other["id"]})
        assert "error" in result and "sensitive" not in json.dumps(result)


def test_context_and_budget_limits(backend, seeded):
    app, _, model = backend
    services, b = seeded
    run, task, scope = make_scope(services, b)
    runner = AgentRunner(services, model)
    services.settings = replace(services.settings, run_budget_usd=Decimal(".00001"))
    with pytest.raises(LimitReached, match="budget"):
        runner.budget(run["id"], 100)
    services.settings = replace(services.settings, run_budget_usd=Decimal(".10"), max_run_calls=1)
    services.store.create("event", {"type": "model_request"}, b["id"], run["id"])
    with pytest.raises(LimitReached, match="requests"):
        runner.budget(run["id"], 100)


def test_strict_schema_is_closed():
    schema = strict_schema(
        {"type": "object", "properties": {"x": {"type": "integer", "default": 0}}}
    )
    assert schema["additionalProperties"] is False and schema["required"] == ["x"]
    assert "default" not in schema["properties"]["x"]
    with pytest.raises(ValueError):
        strict_schema({"type": "object", "additionalProperties": {"type": "string"}})


def test_conflicting_candidates_can_be_accepted_or_rejected(seeded):
    services, b = seeded
    run, task, scope = make_scope(services, b, "data_parser")
    source = next(s for s in services.store.list("source", b["id"]) if s["data"]["format"] == "txt")
    kwargs = dict(
        decision_type="supplier_switch",
        field="new_unit_cost",
        unit="USD/unit",
        source_id=source["id"],
        location=source["data"]["chunks"][0]["location"],
        evidence="new_unit_cost = 10 USD/unit",
    )
    first = services.submit_candidate(b["id"], FactCandidate(value="10", **kwargs))
    second = services.submit_candidate(b["id"], FactCandidate(value="9", **kwargs))
    q1 = services.new_question(
        run,
        Question(field="new_unit_cost", reason="Review first.", candidate_id=first["id"]),
        task["id"],
    )
    q2 = services.new_question(
        run,
        Question(field="new_unit_cost", reason="Review second.", candidate_id=second["id"]),
        task["id"],
    )
    assert q1["id"] != q2["id"]
    assert (
        services.new_question(
            run,
            Question(field="new_unit_cost", reason="Repeated call.", candidate_id=first["id"]),
            task["id"],
        )["id"]
        == q1["id"]
    )
    run = services.store.patch(run, {"status": "waiting_for_input"})
    with pytest.raises(DomainError, match="only one"):
        services.answer_questions(
            run,
            [
                Answer(question_id=q1["id"], accept_candidate=True),
                Answer(question_id=q2["id"], accept_candidate=True),
            ],
        )
    assert (
        services.store.get(first["id"])["data"]["status"] == "candidate"
    )  # entire transaction rolled back
    services.answer_questions(
        run,
        [
            Answer(question_id=q1["id"], accept_candidate=True),
            Answer(question_id=q2["id"], reject_candidate=True),
        ],
    )
    assert services.store.get(first["id"])["data"]["status"] == "confirmed"
    assert services.store.get(second["id"])["data"]["status"] == "rejected"


def test_optimistic_updates_do_not_overwrite_newer_state(seeded):
    services, b = seeded
    record = services.store.create("artifact", {"value": 1}, b["id"])
    services.store.patch(record, {"value": 2})
    with pytest.raises(DomainError, match="changed"):
        services.store.patch(record, {"value": 3})
    assert services.store.get(record["id"])["data"]["value"] == 2
