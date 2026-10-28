"""One small runner; role-specific prompts, contexts and MCP sessions are isolated."""

import json
from decimal import Decimal
from pathlib import Path

from app.config import DomainError, LimitReached
from app.contracts import AgentResult
from app.tools import ToolScope, ToolSession

PROMPTS = Path(__file__).parent / "prompts"


class AgentRunner:
    def __init__(self, services, model):
        self.services, self.model = services, model

    def context(self, run, task, phase):
        self.services.require_demo(run["business_id"])
        upstream = []
        for id in task["data"].get("dependency_ids", []):
            upstream.append(self.services.store.get(id, "task", run["business_id"], run["id"]))
        return {
            "run_id": run["id"],
            "task_id": task["id"],
            "phase": phase,
            "role": task["data"]["role"],
            "question": run["data"]["question"],
            "objective": task["data"]["objective"],
            "plan": run["data"].get("plan"),
            "upstream_results": upstream,
            "research_enabled": False,
            "data_policy": "seeded_demo_only",
        }

    def budget(self, run_id, next_input_chars):
        settings = self.services.settings
        run = self.services.store.get(run_id, "run")
        if run["data"]["status"] == "canceled":
            raise DomainError("canceled", "Run canceled.", 409)
        usages = self.services.store.list("usage", run_id=run_id)
        attempts = [
            e
            for e in self.services.store.list("event", run_id=run_id)
            if e["data"]["type"] == "model_request"
        ]
        if len(attempts) >= settings.max_run_calls:
            raise LimitReached("Maximum model requests reached.")
        spent = sum((Decimal(u["data"]["estimated_cost_usd"]) for u in usages), Decimal(0))
        # Conservative character-based reservation, not a billing guarantee.
        reserve = (
            Decimal(next_input_chars) * settings.input_price_per_million / 1000000
            + Decimal(settings.max_output_tokens) * settings.output_price_per_million / 1000000
        )
        if spent + reserve > settings.run_budget_usd:
            raise LimitReached("Estimated model budget would be exceeded.")
        return reserve

    def record_usage(self, scope, turn, reservation=None):
        s = self.services.settings
        cached = min(turn.cached_tokens, turn.input_tokens)
        cost = (
            Decimal(turn.input_tokens - cached) * s.input_price_per_million
            + Decimal(cached) * s.cached_price_per_million
            + Decimal(turn.output_tokens) * s.output_price_per_million
        ) / 1000000
        data = {
            "task_id": scope.task_id,
            "model": s.openai_model,
            "input_tokens": turn.input_tokens,
            "output_tokens": turn.output_tokens,
            "cached_input_tokens": cached,
            "estimated_cost_usd": str(cost),
            "status": "reported",
            "pricing_basis": "Configured standard short-context token rates; not an invoice.",
        }
        if reservation:
            self.services.store.patch(reservation, data)
        else:
            self.services.store.create("usage", data, scope.business_id, scope.run_id)

    async def run(self, run, task, phase="execute"):
        role = task["data"]["role"]
        settings = self.services.settings
        if role == "research":
            raise DomainError("research_disabled", "Web research is not configured.", 409)
        scope = ToolScope(run["business_id"], run["id"], task["id"], role)
        instructions = (
            (PROMPTS / "common.md").read_text() + "\n" + (PROMPTS / (role + ".md")).read_text()
        )
        history = [
            {
                "role": "user",
                "content": json.dumps(self.context(run, task, phase), ensure_ascii=False),
            }
        ]
        async with ToolSession(self.services, scope) as tools:
            for _ in range(settings.max_agent_turns):
                size = (
                    len(instructions)
                    + len(json.dumps(history))
                    + len(json.dumps(tools.definitions))
                )
                if size > settings.max_context_chars:
                    raise LimitReached("Context limit reached; narrow the task or source excerpts.")
                reserve = self.budget(run["id"], size)
                reservation = self.services.store.create(
                    "usage",
                    {
                        "task_id": scope.task_id,
                        "model": settings.openai_model,
                        "status": "reserved",
                        "estimated_cost_usd": str(reserve),
                        "pricing_basis": "Pre-request estimate retained when actual usage is unknown.",
                    },
                    scope.business_id,
                    scope.run_id,
                )
                self.services.store.create(
                    "event",
                    {"type": "model_request", "task_id": scope.task_id},
                    scope.business_id,
                    scope.run_id,
                )
                try:
                    turn = await self.model.respond(
                        instructions=instructions, history=history, tools=tools.definitions
                    )
                except BaseException:
                    self.services.store.patch(reservation, {"status": "unknown"})
                    raise
                self.record_usage(scope, turn, reservation)
                # Preserve all returned response items, including encrypted reasoning continuity.
                history.extend(turn.items)
                if not turn.calls:
                    if turn.result is None:
                        raise DomainError(
                            "invalid_agent_result",
                            "Model did not complete a valid structured result.",
                        )
                    result = AgentResult.model_validate(turn.result)
                    if phase != "plan" and result.plan is not None:
                        raise DomainError(
                            "unexpected_plan", "Only the planning phase may propose a plan."
                        )
                    for id in result.artifact_ids:
                        item = self.services.store.get(
                            id, business_id=scope.business_id, run_id=scope.run_id
                        )
                        if item["kind"] not in ["artifact", "calculation"]:
                            raise DomainError(
                                "invalid_artifact", "Agent referenced a non-artifact."
                            )
                    return result
                for call in turn.calls:
                    tool_events = [
                        e
                        for e in self.services.store.list("event", run_id=scope.run_id)
                        if e["data"]["type"] == "tool_call"
                    ]
                    if len(tool_events) >= settings.max_tool_calls:
                        raise LimitReached("Maximum tool calls reached.")
                    self.services.store.create(
                        "event",
                        {"type": "tool_call", "task_id": scope.task_id, "tool": call["name"]},
                        scope.business_id,
                        scope.run_id,
                    )
                    try:
                        args = json.loads(call["arguments"])
                        output = await tools.call(call["name"], args)
                    except DomainError as exc:
                        output = {"error": {"code": exc.code, "message": exc.message}}
                    except (ValueError, TypeError):
                        output = {
                            "error": {
                                "code": "invalid_arguments",
                                "message": "Tool arguments must be valid JSON.",
                            }
                        }
                    text = json.dumps(output, allow_nan=False)
                    if len(text) > 20000:
                        raise LimitReached(
                            "Tool output exceeds context limit; request a smaller excerpt."
                        )
                    history.append(
                        {"type": "function_call_output", "call_id": call["call_id"], "output": text}
                    )
            raise LimitReached("Maximum agent turns reached.")
