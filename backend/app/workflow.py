"""Bounded dependency executor. Single process, serial tasks, persisted checkpoints."""

import asyncio

from app.config import DomainError, LimitReached
from app.contracts import Plan, Question

TERMINAL = {
    "completed",
    "unsupported",
    "failed",
    "canceled",
    "blocked",
    "limit_reached",
    "interrupted",
}


def validate_plan(plan: Plan):
    if plan.decision_type == "unsupported":
        if plan.steps:
            raise DomainError("invalid_plan", "Unsupported questions must have no analysis steps.")
        return
    steps = {s.id: s for s in plan.steps}
    if len(steps) != len(plan.steps) or not 4 <= len(steps) <= 8:
        raise DomainError("invalid_plan", "Use 4-8 uniquely identified steps.")
    if any(s.role == "research" for s in plan.steps):
        raise DomainError("research_disabled", "Research cannot be scheduled without a provider.")
    visited = set()
    ancestors = {}
    while len(visited) < len(steps):
        ready = [s for s in plan.steps if s.id not in visited and set(s.depends_on) <= visited]
        if not ready:
            raise DomainError(
                "invalid_plan", "Plan has unknown dependencies or a dependency cycle."
            )
        for step in ready:
            ancestors[step.id] = set(step.depends_on)
            for dep in step.depends_on:
                ancestors[step.id] |= ancestors[dep]
            visited.add(step.id)
    scenarios = [s for s in plan.steps if s.role == "scenario"]
    if len(scenarios) != 1:
        raise DomainError("invalid_plan", "Exactly one scenario step is supported per run.")
    scenario = scenarios[0]
    before = [steps[id].role for id in ancestors[scenario.id]]
    if "data_parser" not in before or "risk" not in before:
        raise DomainError(
            "invalid_plan", "Scenario must depend on data extraction and a prior risk check."
        )
    if not any(s.role == "risk" and scenario.id in ancestors[s.id] for s in plan.steps):
        raise DomainError("invalid_plan", "A risk review must follow the scenario.")


class Executor:
    def __init__(self, services, runner):
        self.services, self.runner = services, runner
        self.jobs = {}

    def create_run(self, request):
        self.services.require_demo(request.business_id)
        return self.services.store.create(
            "run",
            {
                "question": request.question,
                "status": "created",
                "plan": None,
                "report": None,
                "error": None,
            },
            request.business_id,
        )

    def event(self, run, type, **details):
        self.services.store.create(
            "event", {"type": type, **details}, run["business_id"], run["id"]
        )

    def schedule(self, id):
        run = self.services.store.get(id, "run")
        if id in self.jobs and not self.jobs[id].done():
            raise DomainError("already_running", "Run is already executing.", 409)
        if run["data"]["status"] not in ["created", "interrupted", "failed"]:
            raise DomainError("invalid_state", "Run is not ready to execute.", 409)
        self.jobs[id] = asyncio.create_task(self.execute(id))
        return run

    def recover(self):
        for run in self.services.store.list("run"):
            if run["data"]["status"] in ["planning", "running", "synthesizing"]:
                self.services.store.patch(run, {"status": "interrupted"})
                for t in self.services.store.list("task", run_id=run["id"]):
                    if t["data"]["status"] == "running":
                        self.services.store.patch(t, {"status": "pending"})

    async def close(self):
        active = [t for t in self.jobs.values() if not t.done()]
        for task in active:
            task.cancel()
        if active:
            await asyncio.gather(*active, return_exceptions=True)

    def change_run(self, id, **changes):
        return self.services.store.patch(self.services.store.get(id, "run"), changes)

    async def agent_task(self, run, task, phase="execute"):
        task = self.services.store.patch(task, {"status": "running"})
        self.event(run, "task_started", task_id=task["id"], role=task["data"]["role"])
        result = await self.runner.run(run, task, phase)
        if (
            phase == "execute"
            and task["data"]["role"] == "data_parser"
            and result.status == "completed"
        ):
            candidates = [
                f
                for f in self.services.eligible_facts(
                    run["business_id"], run["data"]["plan"]["decision_type"]
                )
                if f["data"]["status"] == "candidate"
            ]
            if candidates:
                result = result.model_copy(
                    update={
                        "status": "needs_input",
                        "questions": [
                            Question(
                                field=f["data"]["field"],
                                reason="Review extracted numerical input before financial use.",
                                candidate_id=f["id"],
                            )
                            for f in candidates
                        ],
                    }
                )
        if result.status == "needs_input":
            if not result.questions:
                raise DomainError(
                    "missing_questions", "needs_input requires at least one question."
                )
            for q in result.questions:
                self.services.new_question(run, q, task["id"])
        elif result.questions:
            raise DomainError("unexpected_questions", "Questions require needs_input status.")
        if phase == "execute" and result.status == "completed":
            artifacts = [
                self.services.store.get(id, business_id=run["business_id"], run_id=run["id"])
                for id in result.artifact_ids
            ]
            role = task["data"]["role"]
            if role == "scenario" and not any(a["kind"] == "calculation" for a in artifacts):
                raise DomainError(
                    "missing_calculation",
                    "Scenario completion requires an actual calculation artifact.",
                )
            if role == "risk":
                risks = [
                    a
                    for a in artifacts
                    if a["kind"] == "artifact"
                    and a["data"].get("type") == "risk"
                    and a["data"].get("task_id") == task["id"]
                ]
                if not risks:
                    raise DomainError(
                        "missing_risk_review", "Risk completion requires a recorded risk review."
                    )
                if any(
                    f["severity"] == "review_required" for a in risks for f in a["data"]["findings"]
                ):
                    result = result.model_copy(update={"status": "blocked"})
        task = self.services.store.patch(
            task, {"status": result.status, "result": result.model_dump(mode="json")}
        )
        self.event(run, "task_finished", task_id=task["id"], status=result.status)
        return task, result

    async def execute(self, id):
        try:
            async with asyncio.timeout(self.services.settings.max_run_seconds):
                await self._execute(id)
        except asyncio.CancelledError:
            run = self.services.store.get(id, "run")
            if run["data"]["status"] != "canceled":
                self.change_run(id, status="interrupted")
            raise
        except (DomainError, ValueError, TimeoutError) as exc:
            code = (
                exc.code
                if isinstance(exc, DomainError)
                else "timeout"
                if isinstance(exc, TimeoutError)
                else "invalid_result"
            )
            message = (
                exc.message
                if isinstance(exc, DomainError)
                else "Workflow timed out."
                if isinstance(exc, TimeoutError)
                else "Agent output failed validation."
            )
            self.change_run(
                id,
                status="limit_reached"
                if isinstance(exc, (LimitReached, TimeoutError))
                else "canceled"
                if code == "canceled"
                else "failed",
                error={"code": code, "message": message},
            )
        except Exception:
            self.change_run(
                id,
                status="failed",
                error={
                    "code": "internal_error",
                    "message": "Unexpected execution failure. Original artifacts are preserved.",
                },
            )
        finally:
            run = self.services.store.get(id, "run")
            if run["data"]["status"] in TERMINAL:
                for t in self.services.store.list("task", run_id=id):
                    if t["data"]["status"] == "running":
                        self.services.store.patch(t, {"status": "pending"})

    async def _execute(self, id):
        run = self.services.store.get(id, "run")
        self.services.require_demo(run["business_id"])
        if not run["data"]["plan"]:
            run = self.change_run(id, status="planning", error=None)
            task = self.services.store.create(
                "task",
                {
                    "role": "orchestrator",
                    "phase": "plan",
                    "objective": "Plan the supported decision workflow.",
                    "status": "pending",
                    "dependency_ids": [],
                },
                run["business_id"],
                id,
            )
            _, result = await self.agent_task(run, task, "plan")
            if result.status != "completed" or result.plan is None:
                raise DomainError("invalid_plan", "Orchestrator must return a complete plan.")
            validate_plan(result.plan)
            if result.plan.decision_type == "unsupported":
                self.change_run(
                    id,
                    status="unsupported",
                    report={
                        "summary": result.summary,
                        "supported": ["supplier_switch", "promotional_event"],
                    },
                )
                return
            task_ids = {}
            # create only after plan validation; dependencies can be in any order
            with self.services.store.transaction() as db:
                for step in result.plan.steps:
                    t = self.services.store.create(
                        "task",
                        {
                            "step_id": step.id,
                            "role": step.role,
                            "phase": "execute",
                            "objective": step.objective,
                            "status": "pending",
                            "dependency_ids": [],
                        },
                        run["business_id"],
                        id,
                        session=db,
                    )
                    task_ids[step.id] = t["id"]
                for step in result.plan.steps:
                    t = self.services.store.get(task_ids[step.id], session=db)
                    self.services.store.patch(
                        t, {"dependency_ids": [task_ids[d] for d in step.depends_on]}, db
                    )
                run = self.services.store.patch(
                    run, {"plan": result.plan.model_dump(mode="json")}, db
                )
        run = self.change_run(id, status="running", error=None)
        while True:
            if self.services.store.get(id, "run")["data"]["status"] == "canceled":
                return
            tasks = [
                t
                for t in self.services.store.list("task", run_id=id)
                if t["data"]["phase"] == "execute"
            ]
            done = {t["id"] for t in tasks if t["data"]["status"] == "completed"}
            if len(done) == len(tasks):
                break
            ready = [
                t
                for t in tasks
                if t["data"]["status"] == "pending" and set(t["data"]["dependency_ids"]) <= done
            ]
            if not ready:
                raise DomainError(
                    "no_ready_tasks", "No dependency-ready tasks remain; review the run state."
                )
            task, result = await self.agent_task(self.services.store.get(id, "run"), ready[0])
            if result.status in ["needs_input", "blocked"]:
                self.change_run(
                    id, status="waiting_for_input" if result.status == "needs_input" else "blocked"
                )
                return
        run = self.change_run(id, status="synthesizing")
        tasks = [
            t
            for t in self.services.store.list("task", run_id=id)
            if t["data"]["phase"] == "execute"
        ]
        calc_ids = [
            a
            for t in tasks
            for a in t["data"]["result"]["artifact_ids"]
            if a.startswith("calculation_")
        ]
        if not calc_ids:
            raise DomainError("missing_calculation", "No calculation was produced.")
        calc = self.services.store.get(calc_ids[-1], "calculation", run["business_id"], id)
        # Detect a fact changed during a run, rather than publishing stale projections.
        for fact_id in calc["data"]["lineage"].values():
            if (
                self.services.store.get(fact_id, "fact", run["business_id"])["data"]["status"]
                != "accepted"
            ):
                raise DomainError(
                    "stale_calculation",
                    "Inputs changed after simulation. Retry with current facts.",
                )
        synthesis = self.services.store.create(
            "task",
            {
                "role": "orchestrator",
                "phase": "synthesize",
                "objective": "Interpret results qualitatively; preserve computed values and unresolved limitations.",
                "dependency_ids": [t["id"] for t in tasks],
                "status": "pending",
            },
            run["business_id"],
            id,
        )
        _, result = await self.agent_task(run, synthesis, "synthesize")
        if result.status != "completed":
            raise DomainError("incomplete_report", "Final synthesis did not complete.")
        report = {
            "summary": calc["data"]["analysis"]["summary"],
            "calculation_id": calc["id"],
            "analysis": calc["data"]["analysis"],
            "qualitative_commentary": result.summary,
            "risk_artifacts": [
                a
                for t in tasks
                if t["data"]["role"] == "risk"
                for a in t["data"]["result"]["artifact_ids"]
            ],
            "limitations": [
                "Web research disabled. All business data is fictional.",
                "Narrative is model-generated; financial tables and summary are populated by deterministic calculations.",
            ],
        }
        self.change_run(id, status="completed", report=report)
