import json
from dataclasses import replace

import pytest
from app.config import Settings
from app.contracts import Answer, RunRequest
from app.demo import load_bundle, seed_demo
from conftest import DemoModel


@pytest.mark.asyncio
async def test_batch_extract_confirm_resume_completes_under_small_limits(backend):
    app, _, _ = backend
    services = app.state.services
    services.settings = replace(
        services.settings, max_tool_calls=15, max_run_calls=16, max_agent_turns=8
    )
    business = seed_demo(services)
    manifest, _, _ = load_bundle()
    fixture = [f for f in manifest["facts"] if f["decision_type"] == "supplier_switch"]
    source_map = {s["data"]["filename"]: s for s in services.store.list("source", business["id"])}

    class BatchModel(DemoModel):
        parser_requests = 0

        async def respond(self, **kwargs):
            ctx = json.loads(kwargs["history"][0]["content"])
            if ctx["role"] != "data_parser":
                return await super().respond(**kwargs)
            self.parser_requests += 1
            assert ctx["input_contract"] and ctx["sources"] and ctx["source_excerpts"]
            outputs = [
                json.loads(i["output"])
                for i in kwargs["history"]
                if i.get("type") == "function_call_output"
            ]
            if not outputs:
                entries = []
                for fact in fixture:
                    source = source_map[fact["source"]]
                    chunk = next(
                        c for c in source["data"]["chunks"] if fact["evidence"] in c["text"]
                    )
                    entries.append(
                        {
                            "subject": "Fixture supplier comparison",
                            "attribute": fact["field"],
                            "value": fact["value"],
                            "unit": "See proposed canonical input",
                            "period": "Fixture period",
                            "status": fact["provenance"],
                            "notes": "Explicit test fixture mapping, not production extraction",
                            "evidence": [
                                {
                                    "source_id": source["id"],
                                    "location": chunk["location"],
                                    "quote": fact["evidence"],
                                }
                            ],
                        }
                    )
                return self.call("save_workspace_entries", {"entries": entries})
            if len(outputs) == 1:
                from app.service import input_unit

                return self.call(
                    "propose_workspace_inputs",
                    {
                        "inputs": [
                            {
                                "entry_id": entry["id"],
                                "field": fact["field"],
                                "value": fact["value"],
                                "unit": input_unit(fact["field"]),
                            }
                            for entry, fact in zip(outputs[0]["entries"], fixture, strict=True)
                        ]
                    },
                )
            if len(outputs) == 2:
                assert not outputs[1]["errors"]
                return self.call(
                    "request_input",
                    {
                        "questions": [
                            {
                                "field": f["field"],
                                "candidate_id": f["id"],
                                "reason": "Check the extracted value",
                            }
                            for f in outputs[1]["facts"]
                        ]
                    },
                )
            raise AssertionError("The runner must pause as soon as questions are saved")

    model = BatchModel()
    app.state.executor.runner.model = model
    run = app.state.executor.create_run(
        RunRequest(business_id=business["id"], question="Would switching suppliers save money?")
    )
    await app.state.executor.execute(run["id"])
    run = services.store.get(run["id"])
    assert run["data"]["status"] == "waiting_for_input", run["data"]
    assert model.parser_requests == 3
    questions = services.store.list("question", run_id=run["id"])
    assert len(questions) == 13
    first = [Answer(question_id=q["id"], accept_candidate=True) for q in questions[:6]]
    assert services.answer_questions(run, first)["data"]["status"] == "waiting_for_input"
    services.answer_questions(
        run, [Answer(question_id=q["id"], accept_candidate=True) for q in questions[6:]]
    )
    parser = next(
        t
        for t in services.store.list("task", run_id=run["id"])
        if t["data"]["role"] == "data_parser"
    )
    assert parser["data"]["status"] == "completed"
    # An accidental re-proposal after confirmation reuses the confirmed fact.
    from app.tools import ToolScope, ToolSession

    async with ToolSession(
        services, ToolScope(business["id"], run["id"], parser["id"], "data_parser")
    ) as tools:
        candidate = services.store.get(questions[0]["data"]["candidate_id"])
        data = candidate["data"]
        reused = await tools.call(
            "propose_workspace_inputs",
            {
                "inputs": [
                    {
                        "entry_id": data["workspace_entry_id"],
                        "field": data["field"],
                        "value": data["value"],
                        "unit": data["unit"],
                    }
                ]
            },
        )
        assert reused["facts"][0]["status"] == "accepted"
        assert not any(
            f["data"]["status"] == "candidate"
            for f in services.eligible_facts(business["id"], "supplier_switch", run["id"])
        )
    await app.state.executor.execute(run["id"])
    result = services.store.get(run["id"])
    assert result["data"]["status"] == "completed", result["data"]
    assert model.parser_requests == 3  # No extraction restart after confirmation.
    events = services.store.list("event", run_id=run["id"])
    assert sum(e["data"]["type"] == "tool_call" for e in events) == 9
    assert sum(e["data"]["type"] == "model_request" for e in events) == 14
    assert result["data"]["report"]["analysis"]["scenarios"][1]["result"]["net_benefit"] == 1880


def test_execution_limits_from_environment_are_validated(monkeypatch):
    for name, value in {
        "MAX_AGENT_TURNS": "40",
        "MAX_RUN_CALLS": "110",
        "MAX_TOOL_CALLS": "200",
        "MAX_RUN_SECONDS": "720",
    }.items():
        monkeypatch.setenv(name, value)
    settings = Settings.from_env()
    assert (
        settings.max_agent_turns,
        settings.max_run_calls,
        settings.max_tool_calls,
        settings.max_run_seconds,
    ) == (40, 110, 200, 720)
    settings.validate(require_api_key=False)
    for field in ["max_agent_turns", "max_run_calls", "max_tool_calls", "max_run_seconds"]:
        with pytest.raises(ValueError, match=field.upper()):
            replace(settings, **{field: 0}).validate(require_api_key=False)
