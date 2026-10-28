import json
from dataclasses import replace
from decimal import Decimal

import httpx
import pytest
from app.agents import AgentRunner
from app.config import DomainError
from app.llm import OpenAIModel
from app.tools import ToolScope
from openai import AsyncOpenAI


def response(output):
    return {
        "id": "resp_test",
        "object": "response",
        "created_at": 0,
        "model": "gpt-6-luna",
        "status": "completed",
        "output": output,
        "usage": {
            "input_tokens": 300,
            "output_tokens": 50,
            "total_tokens": 350,
            "input_tokens_details": {"cached_tokens": 100},
            "output_tokens_details": {"reasoning_tokens": 10},
        },
    }


@pytest.mark.asyncio
async def test_actual_openai_sdk_serialization_without_network(settings):
    captured = []
    final = {
        "status": "completed",
        "summary": "Reviewed.",
        "artifact_ids": [],
        "questions": [],
        "plan": None,
    }

    async def handler(request):
        captured.append(json.loads(request.content))
        return httpx.Response(
            200,
            json=response(
                [
                    {
                        "id": "msg_test",
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {"type": "output_text", "text": json.dumps(final), "annotations": []}
                        ],
                    }
                ]
            ),
        )

    transport = httpx.MockTransport(handler)
    model = OpenAIModel(replace(settings, openai_api_key="synthetic_test_key"))
    model.client = AsyncOpenAI(
        api_key="synthetic_test_key",
        http_client=httpx.AsyncClient(transport=transport),
        max_retries=0,
    )
    turn = await model.respond(
        instructions="Fictional test.", history=[{"role": "user", "content": "Test"}], tools=[]
    )
    assert (
        turn.result == final
        and turn.input_tokens == 300
        and turn.cached_tokens == 100
        and turn.output_tokens == 50
    )
    assert captured[0]["model"] == "gpt-6-luna"
    assert captured[0]["store"] is False
    assert captured[0]["include"] == ["reasoning.encrypted_content"]
    assert captured[0]["text"]["format"]["strict"] is True
    assert "synthetic_test_key" not in json.dumps(captured)
    await model.close()


@pytest.mark.asyncio
async def test_provider_error_is_sanitized_and_not_retried(settings):
    calls = []

    async def handler(request):
        calls.append(request)
        return httpx.Response(
            401,
            json={
                "error": {
                    "message": "sensitive upstream detail",
                    "type": "authentication_error",
                    "code": "invalid_api_key",
                }
            },
        )

    model = OpenAIModel(replace(settings, openai_api_key="synthetic_test_key"))
    model.client = AsyncOpenAI(
        api_key="synthetic_test_key",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        max_retries=0,
    )
    with pytest.raises(DomainError) as error:
        await model.respond(instructions="test", history=[], tools=[])
    assert error.value.code == "model_unavailable"
    assert "sensitive" not in error.value.message
    assert len(calls) == 1
    await model.close()


@pytest.mark.asyncio
async def test_missing_key_never_constructs_a_client(settings):
    model = OpenAIModel(settings)
    with pytest.raises(DomainError, match="OPENAI_API_KEY"):
        await model.respond(instructions="test", history=[], tools=[])
    assert model.client is None


def test_usage_estimate_includes_cached_inputs(backend, seeded):
    app, _, model = backend
    services, b = seeded
    from app.llm import Turn

    run = services.store.create("run", {"status": "running"}, b["id"])
    scope = ToolScope(b["id"], run["id"], "task_test", "scenario")
    AgentRunner(services, model).record_usage(scope, Turn([], [], None, 300, 50, 100))
    usage = services.store.list("usage", run_id=run["id"])[0]["data"]
    # 200*0.10/1M + 100*0.01/1M + 50*0.50/1M = 0.000046
    assert Decimal(usage["estimated_cost_usd"]) == Decimal(".000046")


def test_configuration_does_not_reveal_api_key(settings):
    assert "private_test_key" not in repr(replace(settings, openai_api_key="private_test_key"))


@pytest.mark.asyncio
async def test_incomplete_provider_response_never_executes_a_partial_call(settings):
    async def handler(request):
        payload = response(
            [
                {
                    "id": "fc_test",
                    "type": "function_call",
                    "name": "run_supplier_model",
                    "call_id": "call_test",
                    "arguments": "{}",
                    "status": "in_progress",
                }
            ]
        )
        payload["status"] = "incomplete"
        payload["incomplete_details"] = {"reason": "max_output_tokens"}
        return httpx.Response(200, json=payload)

    model = OpenAIModel(replace(settings, openai_api_key="test_key"))
    model.client = AsyncOpenAI(
        api_key="test_key",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        max_retries=0,
    )
    turn = await model.respond(instructions="test", history=[], tools=[])
    assert turn.calls == [] and turn.result is None
    assert turn.input_tokens == 300  # still account for the billed request
    await model.close()
