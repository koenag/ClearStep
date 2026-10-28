"""Test the live entry point's plumbing without spending API credits.

The script has no fake/offline runtime mode; the application factory is replaced
only inside these tests, exactly like other provider-boundary unit tests.
"""

import importlib.util
import json
from dataclasses import replace
from pathlib import Path

import pytest
from app.main import create_app
from conftest import DemoModel, final


def script_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "live_demo.py"
    spec = importlib.util.spec_from_file_location("live_demo_script", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_live_entry_exports_available_inputs_and_actual_saved_outputs(settings, monkeypatch):
    module = script_module()
    monkeypatch.setattr(module, "create_app", lambda config: create_app(config, DemoModel()))
    config = replace(settings, openai_api_key="synthetic_test_key")
    assert await module.run_demo(config, "Should I switch suppliers?") == 0
    folder = next((settings.data_dir / "runs").iterdir())
    inputs = json.loads((folder / "inputs.json").read_text())
    outputs = json.loads((folder / "outputs.json").read_text())
    assert inputs["question"] == "Should I switch suppliers?"
    assert inputs["available_facts"] and inputs["available_sources"]
    assert all(f["data"]["ai_eligible"] for f in inputs["available_facts"])
    assert outputs["run"]["data"]["status"] == "completed"
    assert (
        outputs["calculations"][0]["data"]["analysis"]["scenarios"][1]["result"]["net_benefit"]
        == 1880
    )
    assert outputs["tasks"] and outputs["events"] and outputs["artifacts"] and outputs["usage"]
    assert "synthetic_test_key" not in json.dumps(inputs) + json.dumps(outputs)


@pytest.mark.asyncio
async def test_blocked_live_entry_exports_reason_without_fake_success(settings, monkeypatch):
    module = script_module()

    class BlockedModel(DemoModel):
        async def respond(self, **kwargs):
            ctx = json.loads(kwargs["history"][0]["content"])
            if ctx["role"] == "risk":
                return final(status="blocked", summary="An unresolved constraint needs review.")
            return await super().respond(**kwargs)

    monkeypatch.setattr(module, "create_app", lambda config: create_app(config, BlockedModel()))
    result = await module.run_demo(
        replace(settings, openai_api_key="synthetic_test_key"), "Should I switch suppliers?"
    )
    assert result == 1
    output = json.loads(next((settings.data_dir / "runs").glob("*/outputs.json")).read_text())
    assert output["run"]["data"]["status"] == "blocked"
    assert output["run"]["data"]["report"] is None
    assert output["calculations"] == []
    assert any(
        t["data"].get("result", {}).get("summary") == "An unresolved constraint needs review."
        for t in output["tasks"]
        if t["data"].get("result")
    )


def test_live_entry_requires_key_before_creating_a_run(settings):
    import asyncio

    module = script_module()
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        asyncio.run(module.run_demo(settings, "Should I switch suppliers?"))
    assert not (settings.data_dir / "runs").exists()
