"""OpenAI adapter. Construction is lazy and disabled unless explicitly configured."""

import json
from dataclasses import dataclass

from openai import AsyncOpenAI, OpenAIError

from app.config import DomainError
from app.contracts import AgentResult
from app.tools import strict_schema


@dataclass
class Turn:
    items: list[dict]
    calls: list[dict]
    result: dict | None
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0


class OpenAIModel:
    def __init__(self, settings):
        self.settings = settings
        self.client = None

    async def respond(self, *, instructions, history, tools):
        if not self.settings.live_api_calls_enabled:
            raise DomainError(
                "live_api_disabled",
                "Live API calls are disabled. Set LIVE_API_CALLS_ENABLED=true explicitly.",
                503,
            )
        if self.client is None:
            self.client = AsyncOpenAI(
                api_key=self.settings.openai_api_key, max_retries=0, timeout=45
            )
        try:
            response = await self.client.responses.create(
                model=self.settings.openai_model,
                instructions=instructions,
                input=history,
                tools=tools,
                store=False,
                service_tier="default",
                include=["reasoning.encrypted_content"],
                reasoning={"effort": "low"},
                max_output_tokens=self.settings.max_output_tokens,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "agent_result",
                        "schema": strict_schema(AgentResult.model_json_schema()),
                        "strict": True,
                    }
                },
            )
        except OpenAIError as exc:
            raise DomainError(
                "model_unavailable",
                "OpenAI request failed. Check account access, model availability, billing, and rate limits. No automatic retry was made; usage may be unknown.",
                503,
            ) from exc
        items = [i.model_dump(mode="json", exclude_none=True) for i in response.output]
        usage = response.usage
        if usage is None:
            raise DomainError(
                "usage_unknown",
                "Provider omitted token usage; the reserved estimate is retained.",
                503,
            )
        calls = (
            [i for i in items if i["type"] == "function_call"]
            if response.status == "completed"
            else []
        )
        result = None
        if response.status == "completed" and not calls and response.output_text:
            try:
                result = json.loads(response.output_text)
            except ValueError:
                pass
        return Turn(
            items,
            calls,
            result,
            usage.input_tokens if usage else 0,
            usage.output_tokens if usage else 0,
            (
                usage.input_tokens_details.cached_tokens
                if usage and usage.input_tokens_details
                else 0
            ),
        )

    async def close(self):
        if self.client:
            await self.client.close()
