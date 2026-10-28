"""Application services shared by REST and MCP. All mutations are explicit."""

import hashlib
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from app.config import DomainError
from app.contracts import EventInput, FactCandidate, SupplierInput
from app.data import parse_file
from app.financial.engine import analyze, money

INPUT_MODELS = {"supplier_switch": SupplierInput, "promotional_event": EventInput}


def input_unit(field):
    if field == "horizon":
        return "months"
    if any(t in field for t in ["rate", "margin", "variation", "escalation"]):
        return "ratio"
    if field in ["current_unit_cost", "new_unit_cost"]:
        return "USD/unit"
    if field == "monthly_quantity":
        return "units/month"
    if field in ["current_moq", "new_moq"]:
        return "units"
    if field == "average_spend":
        return "USD/visit"
    if field == "incremental_visits":
        return "visits"
    if field == "repeat_visits":
        return "visits/customer"
    return "USD"


class Services:
    def __init__(self, store, settings):
        self.store, self.settings = store, settings

    def business(self, id):
        return self.store.get(id, "business")

    def require_demo(self, business_id):
        b = self.business(business_id)
        if not b["data"].get("seeded_demo"):
            raise DomainError(
                "ai_policy_denied",
                "Agent runs are restricted to server-seeded synthetic demo businesses.",
                403,
            )
        return b

    def source(self, id, business_id, for_ai=False):
        s = self.store.get(id, "source", business_id)
        if for_ai:
            self.require_demo(business_id)
            if not s["data"]["ai_eligible"]:
                raise DomainError(
                    "ai_policy_denied",
                    "Uploaded sources are local-only and cannot enter agent context.",
                    403,
                )
        return s

    def upload(self, business_id, filename, content, sheet=None, *, seeded=False, _parsed=None):
        self.business(business_id)
        parsed = (
            _parsed if _parsed is not None else parse_file(filename, content, self.settings, sheet)
        )
        folder = self.settings.data_dir / "sources"
        folder.mkdir(parents=True, exist_ok=True)
        name = uuid4().hex + Path(filename).suffix.lower()
        path = folder / name
        path.write_bytes(content)
        path.chmod(0o600)
        try:
            return self.store.create(
                "source",
                {
                    "filename": Path(filename).name,
                    "storage_name": name,
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "ai_eligible": seeded,
                    "status": "parsed",
                    **parsed,
                },
                business_id,
            )
        except Exception:
            path.unlink(missing_ok=True)
            raise

    def source_view(self, s):
        return {
            **s,
            "data": {k: v for k, v in s["data"].items() if k not in ["chunks", "storage_name"]},
        }

    def baseline(self, business_id):
        sources = [
            s for s in self.store.list("source", business_id) if s["data"]["baseline"] is not None
        ]
        if not sources:
            return None
        s = sources[-1]
        return {
            **s["data"]["baseline"],
            "source_id": s["id"],
            "warnings": s["data"]["baseline"]["warnings"]
            + s["data"]["warnings"]
            + [
                "Latest sales upload is the replacement snapshot; sources are never automatically merged."
            ],
        }

    def validate_field(self, kind, field, value):
        cls = INPUT_MODELS[kind]
        if field not in cls.model_fields:
            raise DomainError("unknown_input", "Unknown input field: " + field)
        # Validate one field using the same rules as the full financial model.
        from pydantic import TypeAdapter

        annotation = cls.model_fields[field].rebuild_annotation()
        return TypeAdapter(annotation).validate_python(value)

    def submit_candidate(self, business_id, candidate: FactCandidate):
        source = self.source(candidate.source_id, business_id, for_ai=True)
        self.validate_field(candidate.decision_type, candidate.field, candidate.value)
        if candidate.unit != input_unit(candidate.field):
            raise DomainError(
                "unit_mismatch",
                "Expected canonical unit "
                + input_unit(candidate.field)
                + ". Ask the user about unit conversions.",
            )
        if not any(
            c["location"] == candidate.location and candidate.evidence in c["text"]
            for c in source["data"]["chunks"]
        ):
            raise DomainError(
                "invalid_evidence",
                "Evidence must be an exact excerpt at the specified source location.",
            )
        # The candidate value is not authoritative even when its quotation exists.
        key = hashlib.sha256(candidate.model_dump_json().encode()).hexdigest()
        return self.store.create(
            "fact",
            {
                **candidate.model_dump(mode="json"),
                "status": "candidate",
                "provenance": "observed",
                "ai_eligible": True,
            },
            business_id,
            key="candidate:" + business_id + ":" + key,
        )

    def eligible_facts(self, business_id, kind):
        self.require_demo(business_id)
        return [
            f
            for f in self.store.list("fact", business_id)
            if f["data"]["decision_type"] == kind
            and f["data"]["ai_eligible"]
            and f["data"]["status"] in ["accepted", "candidate"]
        ]

    def calculate(
        self, business_id, kind, inputs, provenance=None, run_id=None, lineage=None, key=None
    ):
        self.business(business_id)
        result = analyze(kind, inputs, provenance)
        return self.store.create(
            "calculation",
            {
                "analysis": result,
                "lineage": lineage or {},
                "model_version": result["calculation_version"],
            },
            business_id,
            run_id,
            key,
        )

    def calculate_from_facts(self, business_id, run_id, kind, refs, key=None):
        inputs = {}
        lineage = {}
        provenance = {}
        for ref in refs:
            f = self.store.get(ref.fact_id, "fact", business_id)
            p = f["data"]
            if (
                not p["ai_eligible"]
                or p["status"] != "accepted"
                or p["field"] != ref.field
                or p["decision_type"] != kind
            ):
                raise DomainError(
                    "unaccepted_fact", "Use accepted, eligible facts matching the input and model."
                )
            if ref.field in inputs:
                raise DomainError(
                    "duplicate_input", "Each input must have exactly one selected fact."
                )
            if p["unit"] != input_unit(ref.field):
                raise DomainError("unit_mismatch", "Input units do not match.")
            inputs[ref.field] = p["value"]
            lineage[ref.field] = f["id"]
            provenance[ref.field] = p["provenance"]
        # Defaults are assumptions too: an agent must select an accepted value for every input.
        missing = set(INPUT_MODELS[kind].model_fields) - set(inputs)
        if missing:
            return {"status": "needs_input", "missing": sorted(missing)}
        return self.calculate(business_id, kind, inputs, provenance, run_id, lineage, key)

    def new_question(self, run, question, task_id):
        kind = run["data"]["plan"]["decision_type"]
        self.validate_field(kind, question.field, 0 if question.field != "horizon" else 1)
        if question.candidate_id:
            f = self.store.get(question.candidate_id, "fact", run["business_id"])
            if (
                f["data"]["status"] != "candidate"
                or f["data"]["field"] != question.field
                or f["data"]["decision_type"] != kind
                or not f["data"]["ai_eligible"]
            ):
                raise DomainError("invalid_candidate", "Question candidate is invalid.")
        for existing in self.store.list("question", run_id=run["id"]):
            data = existing["data"]
            if (
                data["status"] == "open"
                and data["task_id"] == task_id
                and data["field"] == question.field
                and data["candidate_id"] == question.candidate_id
            ):
                return existing
        return self.store.create(
            "question",
            {**question.model_dump(), "task_id": task_id, "status": "open"},
            run["business_id"],
            run["id"],
        )

    def answer_questions(self, run, answers):
        if run["data"]["status"] != "waiting_for_input":
            raise DomainError("invalid_state", "Run is not waiting for input.", 409)
        if len({a.question_id for a in answers}) != len(answers):
            raise DomainError("duplicate_answer", "Question IDs must be unique.")
        kind = run["data"]["plan"]["decision_type"]
        selected_fields = set()
        with self.store.transaction() as db:
            for a in answers:
                q = self.store.get(a.question_id, "question", run["business_id"], run["id"], db)
                if q["data"]["status"] != "open":
                    raise DomainError(
                        "already_answered", "Question has already been answered.", 409
                    )
                field = q["data"]["field"]
                if a.reject_candidate:
                    if a.accept_candidate or a.value is not None or not q["data"]["candidate_id"]:
                        raise DomainError(
                            "invalid_answer", "Reject a candidate OR accept/supply a value."
                        )
                    candidate = self.store.get(
                        q["data"]["candidate_id"], "fact", run["business_id"], session=db
                    )
                    if candidate["data"]["status"] != "candidate":
                        raise DomainError(
                            "stale_candidate",
                            "This candidate was already reviewed; reload before answering.",
                            409,
                        )
                    self.store.patch(candidate, {"status": "rejected"}, db)
                    self.store.patch(q, {"status": "answered"}, db)
                    continue
                if field in selected_fields:
                    raise DomainError(
                        "conflicting_answers", "Choose only one accepted value per input field."
                    )
                selected_fields.add(field)
                if a.accept_candidate:
                    if a.value is not None or not q["data"]["candidate_id"]:
                        raise DomainError("invalid_answer", "Accept a candidate OR supply a value.")
                    candidate = self.store.get(
                        q["data"]["candidate_id"], "fact", run["business_id"], session=db
                    )
                    if candidate["data"]["status"] != "candidate":
                        raise DomainError(
                            "stale_candidate",
                            "This candidate was already reviewed; reload before answering.",
                            409,
                        )
                    self.store.patch(candidate, {"status": "confirmed"}, db)
                    value = candidate["data"]["value"]
                    unit = candidate["data"]["unit"]
                    provenance = "observed"
                    source_data = {
                        k: candidate["data"].get(k) for k in ["source_id", "location", "evidence"]
                    }
                else:
                    if a.value is None or a.unit != input_unit(field):
                        raise DomainError(
                            "invalid_answer",
                            "Supply a value and canonical unit " + input_unit(field),
                        )
                    value = a.value
                    unit = a.unit
                    provenance = "user"
                    source_data = {}
                value = self.validate_field(kind, field, value)
                for old in self.store.list("fact", run["business_id"], session=db):
                    if (
                        old["data"]["status"] == "accepted"
                        and old["data"]["field"] == field
                        and old["data"]["decision_type"] == kind
                    ):
                        self.store.patch(old, {"status": "superseded"}, db)
                self.store.create(
                    "fact",
                    {
                        "decision_type": kind,
                        "field": field,
                        "value": str(value),
                        "unit": unit,
                        "status": "accepted",
                        "provenance": provenance,
                        "ai_eligible": True,
                        "confirmed_by_user": True,
                        **source_data,
                    },
                    run["business_id"],
                    run["id"],
                    session=db,
                )
                self.store.patch(q, {"status": "answered"}, db)
            remaining = [
                q
                for q in self.store.list("question", run_id=run["id"], session=db)
                if q["data"]["status"] == "open"
            ]
            if not remaining:
                for task in self.store.list("task", run_id=run["id"], session=db):
                    if task["data"].get("phase") == "execute":
                        self.store.patch(task, {"status": "pending", "result": None}, db)
                return self.store.patch(run, {"status": "created"}, db)
            return run

    def save_decision(self, req):
        calc = self.store.get(req.calculation_id, "calculation", req.business_id)
        return self.store.create(
            "decision",
            {
                "title": req.title,
                "status": "planned",
                "selected_scenario": req.selected_scenario,
                "calculation_id": calc["id"],
                "snapshot": calc["data"]["analysis"],
            },
            req.business_id,
        )

    def record_outcome(self, decision_id, req):
        d = self.store.get(decision_id, "decision")
        snapshot = d["data"]["snapshot"]
        selected = next(
            s for s in snapshot["scenarios"] if s["name"] == d["data"]["selected_scenario"]
        )
        result = selected["result"]
        inputs = selected["inputs"]
        if req.period > result["horizon"]:
            raise DomainError("invalid_period", "Period exceeds original forecast.")
        existing = self.store.list("outcome", d["business_id"])
        if any(
            o["data"]["decision_id"] == d["id"]
            and (
                o["data"]["period"] == req.period
                or snapshot["decision_type"] == "promotional_event"
            )
            for o in existing
        ):
            raise DomainError(
                "duplicate_outcome",
                "One supplier observation per month or one cumulative event observation is supported.",
                409,
            )
        actual = req.model_dump(mode="json")
        if snapshot["decision_type"] == "supplier_switch":
            if req.actual_savings is None:
                raise DomainError("missing_actual", "Actual procurement savings are required.")
            net = req.actual_savings
            expected = {
                "net_benefit": result["timeline"][req.period - 1]["savings"],
                "basis": "Monthly procurement savings before switching cost",
            }
        else:
            if any(v is None for v in [req.attendance, req.revenue, req.costs]):
                raise DomainError(
                    "missing_actual",
                    "Incremental attendance, revenue and total costs are required.",
                )
            net = (
                req.revenue * Decimal(inputs["contribution_margin"])
                - req.costs
                + (req.repeat_contribution or Decimal(0))
            )
            pending = req.repeat_contribution is None
            expected = {
                "net_benefit": money(
                    Decimal(str(result["event_contribution"]))
                    - Decimal(str(result["total_cost"]))
                    + (Decimal(0) if pending else Decimal(str(result["repeat_contribution"])))
                ),
                "repeat_pending": pending,
                "full_horizon_net_benefit": result["net_benefit"],
                "margin_assumption": inputs["contribution_margin"],
                "time_comparable": pending or req.period == result["horizon"],
                "basis": "Event-only; repeat visits pending"
                if pending
                else "Full horizon"
                if req.period == result["horizon"]
                else "Observed repeat contribution is partial; no monthly repeat timing forecast exists",
            }
        actual["net_benefit"] = money(net)
        return self.store.create(
            "outcome",
            {
                "decision_id": d["id"],
                "period": req.period,
                "actual": actual,
                "expected": expected,
                "variance": money(net - Decimal(str(expected["net_benefit"])))
                if expected.get("time_comparable", True)
                else None,
            },
            d["business_id"],
            key=f"outcome:{d['id']}:{req.period if snapshot['decision_type'] == 'supplier_switch' else 'cumulative'}",
        )
