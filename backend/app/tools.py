"""Actual MCP tools. A separate scoped server is built for each agent execution."""

import hashlib
import json
from dataclasses import dataclass
from functools import wraps
from typing import Any

from mcp import Client
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from app.config import DomainError
from app.contracts import FactCandidate, InputRef, Question, RiskFinding

DOMAIN_ERROR_MARKER = "BUSINESS_TOOL_ERROR: "

ROLE_TOOLS = {
    "orchestrator": {"get_context", "get_artifact"},
    "data_parser": {
        "get_context",
        "list_sources",
        "read_source_excerpt",
        "get_facts",
        "submit_fact_candidate",
        "request_input",
    },
    "risk": {
        "get_context",
        "get_facts",
        "get_artifact",
        "read_source_excerpt",
        "submit_risk_findings",
        "request_input",
    },
    "scenario": {
        "get_context",
        "get_facts",
        "get_artifact",
        "run_supplier_model",
        "run_event_model",
        "request_input",
    },
    "research": set(),
}


@dataclass(frozen=True)
class ToolScope:
    business_id: str
    run_id: str
    task_id: str
    role: str


def strict_schema(schema):
    """Adapt the JSON Schema subset used by our tools to OpenAI strict mode.

    Optional properties become required but keep their original type. Models send
    their declared defaults explicitly; unsupported open dictionaries are rejected.
    """
    schema = json.loads(json.dumps(schema))

    def walk(node):
        if isinstance(node, dict):
            node.pop("default", None)
            if node.get("type") == "object":
                if node.get("additionalProperties") not in (None, False):
                    raise ValueError("Open-ended dictionaries are not valid strict tool arguments.")
                node["additionalProperties"] = False
                node["required"] = list(node.get("properties", {}))
            for value in list(node.values()):
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(schema)
    return schema


def create_server(services, scope: ToolScope):
    services.require_demo(scope.business_id)
    run = services.store.get(scope.run_id, "run", scope.business_id)
    server = MCPServer("Business tools: " + scope.role)
    allowed = ROLE_TOOLS[scope.role]

    def register(fn):
        if fn.__name__ in allowed:

            @wraps(fn)
            def guarded(*args, **kwargs):
                try:
                    return fn(*args, **kwargs)
                except DomainError as exc:
                    # Expected application failures are MCP tool errors, not SDK crashes.
                    payload = {"error": {"code": exc.code, "message": exc.message}}
                    raise ToolError(DOMAIN_ERROR_MARKER + json.dumps(payload)) from None

            server.tool(structured_output=True)(guarded)
        return fn

    def artifact(id):
        for kind in ["artifact", "calculation", "task"]:
            try:
                return services.store.get(id, kind, scope.business_id, scope.run_id)
            except DomainError as exc:
                if exc.code != "not_found":
                    raise
        raise DomainError("not_found", "Artifact not found in this run.", 404)

    def require_kind(kind):
        if run["data"].get("plan", {}).get("decision_type") != kind:
            raise DomainError("wrong_model", "The model must match the validated run plan.")

    @register
    def get_context() -> dict[str, Any]:
        """Get the scoped objective, eligible source metadata and capabilities. No real uploads."""
        sources = [
            services.source_view(s)
            for s in services.store.list("source", scope.business_id)
            if s["data"]["ai_eligible"]
        ]
        # Never return raw business name or descriptions from editable profile fields.
        return {
            "business": "Server-seeded fictional coffee shop",
            "question": run["data"]["question"],
            "plan": run["data"].get("plan"),
            "sources": sources,
            "research_enabled": False,
            "canonical_units": "USD/unit, units/month, units, USD, months, ratio, USD/visit, visits, visits/customer",
        }

    @register
    def list_sources() -> dict[str, Any]:
        """List only server-seeded sources approved for AI use."""
        return {
            "sources": [
                services.source_view(s)
                for s in services.store.list("source", scope.business_id)
                if s["data"]["ai_eligible"]
            ]
        }

    @register
    def read_source_excerpt(source_id: str, part: int) -> dict[str, Any]:
        """Read a 3000-character page/sheet excerpt. part is zero-based; exact location is preserved."""
        source = services.source(source_id, scope.business_id, for_ai=True)
        chunks = []
        for c in source["data"]["chunks"]:
            chunks.extend(
                {"location": c["location"], "text": c["text"][i : i + 3000]}
                for i in range(0, len(c["text"]), 3000)
            )
        if not 0 <= part < len(chunks):
            raise DomainError("invalid_part", "Part index is out of range.")
        return {"source_id": source_id, "part": part, "total_parts": len(chunks), **chunks[part]}

    @register
    def get_facts() -> dict[str, Any]:
        """Get accepted and candidate facts for the planned decision. Candidates require user review."""
        kind = run["data"]["plan"]["decision_type"]
        return {"facts": services.eligible_facts(scope.business_id, kind)}

    @register
    def get_artifact(artifact_id: str) -> dict[str, Any]:
        """Read an artifact, task result or calculation belonging to this run."""
        return artifact(artifact_id)

    @register
    def submit_fact_candidate(candidate: FactCandidate) -> dict[str, Any]:
        """Propose a numerical fact with exact evidence. It remains unaccepted until user confirmation."""
        require_kind(candidate.decision_type)
        return services.submit_candidate(scope.business_id, candidate)

    @register
    def request_input(questions: list[Question]) -> dict[str, Any]:
        """Record missing-input or candidate-review questions; return needs_input as final status."""
        return {
            "questions": [
                services.new_question(services.store.get(scope.run_id, "run"), q, scope.task_id)
                for q in questions
            ]
        }

    def calculate(kind, refs):
        require_kind(kind)
        risks = [
            a
            for a in services.store.list("artifact", scope.business_id, scope.run_id)
            if a["data"].get("type") == "risk"
        ]
        if any(f["severity"] == "review_required" for a in risks for f in a["data"]["findings"]):
            raise DomainError(
                "risk_review_required", "An unresolved material risk blocks simulation."
            )
        digest = hashlib.sha256(
            json.dumps([r.model_dump() for r in refs], sort_keys=True).encode()
        ).hexdigest()
        return services.calculate_from_facts(
            scope.business_id,
            scope.run_id,
            kind,
            refs,
            key=scope.run_id + ":" + kind + ":" + digest,
        )

    @register
    def run_supplier_model(inputs: list[InputRef]) -> dict[str, Any]:
        """Run deterministic supplier scenarios using an accepted fact ID for EVERY input field."""
        return calculate("supplier_switch", inputs)

    @register
    def run_event_model(inputs: list[InputRef]) -> dict[str, Any]:
        """Run deterministic event scenarios using an accepted fact ID for EVERY input field."""
        return calculate("promotional_event", inputs)

    @register
    def submit_risk_findings(findings: list[RiskFinding]) -> dict[str, Any]:
        """Store evidence-backed risk findings. review_required stops the run for explicit review."""
        for finding in findings:
            if not finding.evidence_ids:
                raise DomainError(
                    "evidence_required", "Risk findings need source/fact/artifact references."
                )
            for id in finding.evidence_ids:
                try:
                    if id.startswith("source_"):
                        services.source(id, scope.business_id, for_ai=True)
                    elif id.startswith("fact_"):
                        f = services.store.get(id, "fact", scope.business_id)
                        if not f["data"]["ai_eligible"]:
                            raise DomainError("ai_policy_denied", "Fact is local-only.", 403)
                    else:
                        artifact(id)
                except DomainError as exc:
                    if exc.code == "not_found":
                        raise DomainError(
                            "invalid_evidence_reference",
                            f"Evidence ID {id!r} is unavailable in this scope. "
                            "Call get_facts or get_context for facts/sources, or get_artifact "
                            "for a current-run artifact. Copy an exact returned ID and "
                            "resubmit the findings. Field names and guessed/truncated IDs "
                            "are not evidence IDs. No findings were saved.",
                        ) from None
                    raise
        data = {
            "type": "risk",
            "findings": [f.model_dump() for f in findings],
            "task_id": scope.task_id,
        }
        key = (
            scope.task_id
            + ":risk:"
            + hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
        )
        return services.store.create("artifact", data, scope.business_id, scope.run_id, key)

    return server


class ToolSession:
    """Allowlisted MCP bridge. The model never receives a client or a raw callable."""

    def __init__(self, services, scope):
        self.scope = scope
        self.client = Client(create_server(services, scope))
        self.definitions = []
        self.schemas = {}

    async def __aenter__(self):
        await self.client.__aenter__()
        tools = (await self.client.list_tools()).tools
        for t in tools:
            schema = strict_schema(t.input_schema)
            self.schemas[t.name] = schema
            self.definitions.append(
                {
                    "type": "function",
                    "name": t.name,
                    "description": t.description or t.name,
                    "parameters": schema,
                    "strict": True,
                }
            )
        return self

    async def __aexit__(self, *args):
        try:
            return await self.client.__aexit__(*args)
        except BaseExceptionGroup as group:
            # AnyIO nests the original caller error during transport teardown.
            # Preserve a single domain/cancellation error rather than misclassify
            # it as an internal failure. Multiple errors remain grouped.
            error = group
            while isinstance(error, BaseExceptionGroup) and len(error.exceptions) == 1:
                error = error.exceptions[0]
            raise error from None

    async def call(self, name, arguments):
        if name not in self.schemas:
            raise DomainError("tool_denied", "This tool is not available to this agent.", 403)
        from jsonschema import validate

        try:
            validate(arguments, self.schemas[name])
        except Exception as exc:
            raise DomainError(
                "invalid_tool_arguments", "Tool arguments do not match its schema."
            ) from exc
        result = await self.client.call_tool(name, arguments)
        if result.is_error:
            # Only decode the application-owned error envelope; arbitrary SDK errors
            # remain generic so unexpected failures cannot leak internal details.
            for content in result.content:
                if content.type != "text":
                    continue
                _, marker, encoded = content.text.partition(DOMAIN_ERROR_MARKER)
                if marker:
                    try:
                        payload = json.loads(encoded)
                    except ValueError:
                        continue
                    if (
                        isinstance(payload, dict)
                        and set(payload) == {"error"}
                        and isinstance(payload["error"], dict)
                        and set(payload["error"]) == {"code", "message"}
                        and all(isinstance(v, str) for v in payload["error"].values())
                    ):
                        return payload
            return {
                "error": {
                    "code": "tool_failed",
                    "message": "Tool rejected the operation. Check accepted facts, evidence, scope, units, and input requirements; ask for clarification if unresolved.",
                }
            }
        if result.structured_content is not None:
            return result.structured_content
        texts = [c.text for c in result.content if c.type == "text"]
        try:
            return json.loads("\n".join(texts))
        except ValueError as exc:
            raise DomainError(
                "invalid_tool_result", "Tool did not return structured JSON."
            ) from exc
