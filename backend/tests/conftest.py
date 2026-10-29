import json

import pytest
from app.config import Settings
from app.llm import Turn
from app.main import create_app
from fastapi.testclient import TestClient


def final(summary="Reviewed the fictional inputs.", **kwargs):
    return Turn(
        [],
        [],
        {
            "status": "completed",
            "summary": summary,
            "artifact_ids": [],
            "questions": [],
            "plan": None,
            **kwargs,
        },
        200,
        50,
    )


def plan(kind="supplier_switch"):
    return {
        "decision_type": kind,
        "objective": "Compare the fictional alternatives.",
        "steps": [
            {
                "id": "extract",
                "role": "data_parser",
                "objective": "Review sources and facts.",
                "depends_on": [],
            },
            {
                "id": "constraints",
                "role": "risk",
                "objective": "Check constraints.",
                "depends_on": ["extract"],
            },
            {
                "id": "simulate",
                "role": "scenario",
                "objective": "Run deterministic scenarios.",
                "depends_on": ["constraints"],
            },
            {
                "id": "review",
                "role": "risk",
                "objective": "Review calculation sensitivity.",
                "depends_on": ["simulate"],
            },
        ],
    }


class DemoModel:
    """Explicit test double; all real MCP handlers and financial tools still execute."""

    def __init__(self, kind="supplier_switch"):
        self.kind = kind
        self.requests = []
        self.count = 0

    def call(self, name, args):
        self.count += 1
        item = {
            "type": "function_call",
            "name": name,
            "arguments": json.dumps(args),
            "call_id": f"call_{self.count}",
        }
        return Turn([item], [item], None, 200, 50)

    async def respond(self, *, instructions, history, tools):
        self.requests.append(
            json.loads(
                json.dumps({"instructions": instructions, "history": history, "tools": tools})
            )
        )
        ctx = json.loads(history[0]["content"])
        outputs = [
            json.loads(i["output"]) for i in history if i.get("type") == "function_call_output"
        ]
        if ctx["phase"] == "plan":
            return final(
                plan=plan(self.kind)
                if self.kind != "unsupported"
                else {
                    "decision_type": "unsupported",
                    "objective": "Unsupported question.",
                    "steps": [],
                }
            )
        if ctx["phase"] == "synthesize":
            ids = [
                id
                for t in ctx["upstream_results"]
                for id in t["data"]["result"]["artifact_ids"]
                if id.startswith("calculation_")
            ]
            return final(
                "Compare quality and operational assumptions before acting.", artifact_ids=ids
            )
        role = ctx["role"]
        if not outputs:
            return self.call("get_facts", {})
        if role == "data_parser":
            if len(outputs) == 1:
                return self.call("query_workspace", {"query": "", "offset": 0, "limit": 10})
            if outputs[1]["entries"]:
                return final(artifact_ids=[outputs[1]["entries"][0]["id"]])
            if len(outputs) == 2:
                return self.call("list_sources", {})
            if len(outputs) == 3:
                return self.call(
                    "read_source_excerpt",
                    {"source_id": outputs[-1]["sources"][-1]["id"], "part": 0},
                )
            if len(outputs) == 4:
                excerpt = outputs[-1]
                return self.call(
                    "save_workspace_entry",
                    {
                        "entry": {
                            "subject": "Test records",
                            "attribute": "context",
                            "value": "Fixture context",
                            "unit": "",
                            "period": "",
                            "status": "observed",
                            "notes": "Test-only extraction",
                            "evidence": [
                                {
                                    "source_id": excerpt["source_id"],
                                    "location": excerpt["location"],
                                    "quote": excerpt["text"][:100],
                                }
                            ],
                        }
                    },
                )
            return final(artifact_ids=[outputs[-1]["id"]])
        if role == "risk":
            if len(outputs) == 1:
                return self.call("submit_risk_findings", {"findings": []})
            return final(artifact_ids=[outputs[-1]["id"]])
        if role == "scenario":
            if len(outputs) == 1:
                return self.call(
                    "run_supplier_model" if self.kind == "supplier_switch" else "run_event_model",
                    {
                        "inputs": [
                            {"field": f["data"]["field"], "fact_id": f["id"]}
                            for f in outputs[0]["facts"]
                            if f["data"]["status"] == "accepted"
                        ]
                    },
                )
            if outputs[-1].get("status") == "needs_input":
                return final(
                    status="needs_input",
                    questions=[
                        {
                            "field": field,
                            "reason": "Please supply the missing fictional input.",
                            "candidate_id": None,
                        }
                        for field in outputs[-1]["missing"]
                    ],
                )
            return final(artifact_ids=[outputs[-1]["id"]])
        raise AssertionError("Unexpected test role")

    async def close(self):
        pass


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path, database_url="sqlite://")


@pytest.fixture
def backend(settings):
    model = DemoModel()
    app = create_app(settings, model)
    with TestClient(app) as client:
        yield app, client, model


@pytest.fixture
def seeded(backend):
    app, client, model = backend
    b = client.post("/api/demo/seed").json()
    # Explicit test-only financial fixtures; production demo seeding loads no facts.
    from app.demo import load_bundle
    from app.service import input_unit

    services = app.state.services
    manifest, _, _ = load_bundle()
    sources = {s["data"]["filename"]: s for s in services.store.list("source", b["id"])}
    for fact in manifest["facts"]:
        source = sources[fact["source"]]
        location = next(
            c["location"] for c in source["data"]["chunks"] if fact["evidence"] in c["text"]
        )
        services.store.create(
            "fact",
            {
                **{
                    k: fact[k]
                    for k in ["decision_type", "field", "value", "evidence", "provenance"]
                },
                "unit": input_unit(fact["field"]),
                "source_id": source["id"],
                "location": location,
                "status": "accepted",
                "ai_eligible": True,
            },
            b["id"],
        )
    return services, b
