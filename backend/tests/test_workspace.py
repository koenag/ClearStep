import json

import pytest
from app.config import DomainError
from app.contracts import Answer, InputRef, Question
from app.demo import seed_demo
from app.tools import ToolSession
from conftest import DemoModel, final
from test_live_demo import script_module
from test_tools import make_scope


def entry_for(source, **changes):
    chunk = source["data"]["chunks"][0]
    return {
        "subject": "Supplier A",
        "attribute": "price",
        "value": "10",
        "unit": "USD/unit",
        "period": "November 2026",
        "status": "assumed",
        "notes": "Owner forecast, not historical fact",
        "evidence": [
            {"source_id": source["id"], "location": chunk["location"], "quote": chunk["text"][:100]}
        ],
        **changes,
    }


@pytest.mark.asyncio
async def test_workspace_evidence_scope_search_and_review(backend):
    app, client, _ = backend
    services = app.state.services
    business = services.store.create("business", {"name": "Uploaded business"})
    source = services.upload(
        business["id"], "notes.txt", b"Owner expects price to be $10 per unit in November 2026."
    )
    run, task, scope = make_scope(services, business, "data_parser")
    async with ToolSession(services, scope) as tools:
        context = await tools.call("get_context", {})
        assert "new_unit_cost" in context["input_contract"]["properties"]
        entry = entry_for(source)
        saved = await tools.call("save_workspace_entry", {"entry": entry})
        repeated = await tools.call("save_workspace_entry", {"entry": entry})
        assert repeated["id"] == saved["id"]
        invalid = entry_for(
            source, evidence=[{"source_id": source["id"], "location": "wrong", "quote": "invented"}]
        )
        assert (await tools.call("save_workspace_entry", {"entry": invalid}))["error"][
            "code"
        ] == "invalid_evidence"
        candidate = await tools.call(
            "propose_workspace_input",
            {
                "entry_id": saved["id"],
                "field": "new_unit_cost",
                "value": "10",
                "unit": "USD/unit",
            },
        )
        assert candidate["data"]["status"] == "candidate"
        assert candidate["data"]["workspace_entry_id"] == saved["id"]
        assert candidate["data"]["provenance"] == "assumed"
        assert candidate["run_id"] == run["id"]
    with pytest.raises(DomainError, match="accepted"):
        services.calculate_from_facts(
            business["id"],
            run["id"],
            "supplier_switch",
            [InputRef(field="new_unit_cost", fact_id=candidate["id"])],
        )
    question = services.new_question(
        run,
        Question(field="new_unit_cost", reason="Review", candidate_id=candidate["id"]),
        task["id"],
    )
    run = services.store.patch(run, {"status": "waiting_for_input"})
    services.answer_questions(run, [Answer(question_id=question["id"], accept_candidate=True)])
    accepted = next(
        f
        for f in services.eligible_facts(business["id"], "supplier_switch")
        if f["data"]["status"] == "accepted"
    )
    assert accepted["data"]["provenance"] == "assumed"
    assert accepted["data"]["workspace_entry_id"] == saved["id"]
    response = client.get(f"/api/runs/{run['id']}/workspace", params={"query": "supplier november"})
    assert response.json()["entries"][0]["id"] == saved["id"]
    assert client.get(f"/api/runs/{run['id']}/workspace", params={"limit": 11}).status_code == 422
    assert client.get("/api/runs/missing/workspace").status_code == 404
    other_run, _, other_scope = make_scope(services, business, "data_parser")
    async with ToolSession(services, other_scope) as tools:
        assert (await tools.call("query_workspace", {"query": "", "offset": 0, "limit": 10}))[
            "entries"
        ] == []
        denied = await tools.call(
            "propose_workspace_input",
            {
                "entry_id": saved["id"],
                "field": "new_unit_cost",
                "value": "10",
                "unit": "USD/unit",
            },
        )
        assert denied["error"]["code"] == "not_found"


@pytest.mark.asyncio
async def test_workspace_conflicts_pagination_and_role_permissions(seeded):
    services, business = seeded
    source = services.store.list("source", business["id"])[1]
    run, task, scope = make_scope(services, business, "data_parser")
    async with ToolSession(services, scope) as tools:
        entries = [entry_for(source, value=str(i), status="conflicting") for i in range(3)]
        saved = await tools.call("save_workspace_entries", {"entries": entries})
        ids = [r["id"] for r in saved["entries"]]
        page = await tools.call("query_workspace", {"query": "supplier", "offset": 0, "limit": 2})
        assert page["total"] == 3 and page["next_offset"] == 2
        assert (
            len(
                (await tools.call("query_workspace", {"query": "", "offset": 2, "limit": 2}))[
                    "entries"
                ]
            )
            == 1
        )
        result = await tools.call(
            "propose_workspace_input",
            {"entry_id": ids[0], "field": "new_unit_cost", "value": "10", "unit": "USD/unit"},
        )
        assert result["error"]["code"] == "unresolved_entry"
    from dataclasses import replace

    async with ToolSession(services, replace(scope, role="risk")) as tools:
        assert "query_workspace" in tools.schemas and "save_workspace_entry" not in tools.schemas
        assert (
            len(
                (await tools.call("query_workspace", {"query": "", "offset": 0, "limit": 10}))[
                    "entries"
                ]
            )
            == 3
        )
    outsider = services.store.create("business", {"name": "Other"})
    foreign = services.upload(outsider["id"], "private.txt", b"Private terms")
    async with ToolSession(services, scope) as tools:
        result = await tools.call("save_workspace_entry", {"entry": entry_for(foreign)})
        assert result["error"]["code"] == "not_found"
        assert "Private terms" not in json.dumps(result)


def test_demo_and_folder_start_without_prefilled_facts(backend, tmp_path):
    services = backend[0].state.services
    business = seed_demo(services)
    assert services.store.list("fact", business["id"]) == []
    folder = tmp_path / "inputs"
    folder.mkdir()
    (folder / "notes.txt").write_text("A supplier quote and owner notes.")
    (folder / "invoice.csv").write_text("supplier,amount\nA,100\n")
    module = script_module()
    loaded = module.load_folder(services, folder)
    assert module.load_folder(services, folder)["id"] == loaded["id"]
    assert len(services.store.list("source", loaded["id"])) == 2
    assert services.store.list("fact", loaded["id"]) == []
    (folder / "bad.csv").write_text("")
    before = len(services.store.list("business"))
    with pytest.raises(DomainError, match="empty"):
        module.load_folder(services, folder)
    assert len(services.store.list("business")) == before


@pytest.mark.asyncio
async def test_extraction_workspace_confirmation_and_financial_run(backend, seeded):
    from app.contracts import RunRequest

    app, _, _ = backend
    services, business = seeded
    old = next(
        f
        for f in services.eligible_facts(business["id"], "supplier_switch")
        if f["data"]["field"] == "new_unit_cost"
    )
    services.store.patch(old, {"status": "superseded"})
    source = services.source(old["data"]["source_id"], business["id"])

    class ExtractingModel(DemoModel):
        async def respond(self, **kwargs):
            context = json.loads(kwargs["history"][0]["content"])
            if context["role"] != "data_parser" or getattr(self, "proposed", False):
                return await super().respond(**kwargs)
            outputs = [
                json.loads(i["output"])
                for i in kwargs["history"]
                if i.get("type") == "function_call_output"
            ]
            if not outputs:
                return self.call(
                    "save_workspace_entry", {"entry": entry_for(source, status="observed")}
                )
            if len(outputs) == 1:
                return self.call(
                    "propose_workspace_input",
                    {
                        "entry_id": outputs[0]["id"],
                        "field": "new_unit_cost",
                        "value": "10",
                        "unit": "USD/unit",
                    },
                )
            self.proposed = True
            return final(
                status="needs_input",
                artifact_ids=[outputs[0]["id"]],
                questions=[
                    {
                        "field": "new_unit_cost",
                        "reason": "Review the extracted quote",
                        "candidate_id": outputs[-1]["id"],
                    }
                ],
            )

    app.state.executor.runner.model = ExtractingModel()
    run = app.state.executor.create_run(
        RunRequest(business_id=business["id"], question="Should I switch suppliers?")
    )
    await app.state.executor.execute(run["id"])
    run = services.store.get(run["id"])
    assert run["data"]["status"] == "waiting_for_input"
    assert services.store.list("calculation", run_id=run["id"]) == []
    question = services.store.list("question", run_id=run["id"])[0]
    services.answer_questions(run, [Answer(question_id=question["id"], accept_candidate=True)])
    await app.state.executor.execute(run["id"])
    result = services.store.get(run["id"])
    assert result["data"]["status"] == "completed", result["data"]
    calculation = services.store.list("calculation", run_id=run["id"])[0]
    assert calculation["data"]["analysis"]["scenarios"][1]["result"]["net_benefit"] == 1880
    fact = services.store.get(calculation["data"]["lineage"]["new_unit_cost"])
    workspace = services.store.get(fact["data"]["workspace_entry_id"])
    assert workspace["run_id"] == run["id"]
