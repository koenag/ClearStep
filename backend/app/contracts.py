"""Contracts shared by HTTP, agents, MCP and deterministic calculations."""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Kind = Literal["supplier_switch", "promotional_event"]
Role = Literal["orchestrator", "data_parser", "risk", "scenario", "research"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, validate_default=True)


class SupplierInput(Strict):
    current_unit_cost: Decimal = Field(ge=0, le=1000000)
    new_unit_cost: Decimal = Field(ge=0, le=1000000)
    monthly_quantity: Decimal = Field(ge=0, le=10000000)
    current_shipping: Decimal = Field(default=0, ge=0, le=1000000)
    new_shipping: Decimal = Field(default=0, ge=0, le=1000000)
    switching_cost: Decimal = Field(default=0, ge=0, le=10000000)
    current_moq: int = Field(default=0, ge=0, le=10000000)
    new_moq: int = Field(default=0, ge=0, le=10000000)
    horizon: int = Field(default=12, ge=1, le=60)
    current_escalation: Decimal = Field(default=0, ge=0, le=1)
    new_escalation: Decimal = Field(default=0, ge=0, le=1)
    demand_variation: Decimal = Field(default=Decimal(".2"), ge=0, le=1)
    cost_variation: Decimal = Field(default=Decimal(".05"), ge=0, le=1)


class EventInput(Strict):
    event_cost: Decimal = Field(ge=0, le=10000000)
    incremental_visits: Decimal = Field(ge=0, le=10000000)
    average_spend: Decimal = Field(ge=0, le=1000000)
    contribution_margin: Decimal = Field(ge=0, le=1)
    repeat_rate: Decimal = Field(default=0, ge=0, le=1)
    repeat_visits: Decimal = Field(default=0, ge=0, le=1000)
    staffing_cost: Decimal = Field(default=0, ge=0, le=10000000)
    horizon: int = Field(default=12, ge=1, le=60)
    attendance_variation: Decimal = Field(default=Decimal(".25"), ge=0, le=1)
    spend_variation: Decimal = Field(default=Decimal(".1"), ge=0, le=1)
    expense_variation: Decimal = Field(default=Decimal(".1"), ge=0, le=1)
    repeat_variation: Decimal = Field(default=Decimal(".25"), ge=0, le=1)


class CashMonth(Strict):
    month: int
    current_cost: float
    proposed_cost: float
    savings: float
    cumulative: float
    current_inventory: float
    proposed_inventory: float


class SupplierResult(Strict):
    net_benefit: float
    monthly_savings: float
    current_monthly_cost: float
    proposed_monthly_cost: float
    switching_cost: float
    upfront_cash: float
    roi: float | None
    roi_basis: str
    break_even_month: int | None
    horizon: int
    current_total: float
    proposed_total: float
    consumed_cost_savings: float
    ending_current_inventory: float
    ending_proposed_inventory: float
    timeline: list[CashMonth]


class EventResult(Strict):
    net_benefit: float
    event_revenue: float
    event_contribution: float
    repeat_contribution: float
    total_cost: float
    upfront_cash: float
    roi: float | None
    roi_basis: str
    break_even_visits: int | None
    horizon: int
    timeline: list[CashMonth]


class Assumption(Strict):
    name: str
    value: float
    unit: str
    provenance: Literal["user", "assumed", "observed"]
    editable: bool


class Scenario(Strict):
    name: Literal["Pessimistic", "Base case", "Optimistic"]
    inputs: dict[str, str | int | float]
    result: SupplierResult | EventResult


class AnalysisOutput(Strict):
    decision_type: Kind
    inputs: dict[str, str | int | float]
    scenarios: list[Scenario]
    summary: str
    assumptions: list[Assumption]
    risks: list[str]
    calculation_version: str
    scenario_note: str


class BusinessCreate(Strict):
    name: str = Field(min_length=1, max_length=120)
    industry: str = Field(default="Coffee shop", max_length=120)


class RunRequest(Strict):
    business_id: str
    question: str = Field(min_length=3, max_length=2000)


class PlanStep(Strict):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,30}$")
    role: Literal["data_parser", "risk", "scenario", "research"]
    objective: str = Field(min_length=1, max_length=1000)
    depends_on: list[str] = Field(max_length=8)


class Plan(Strict):
    decision_type: Literal["supplier_switch", "promotional_event", "unsupported"]
    objective: str = Field(min_length=1, max_length=1000)
    steps: list[PlanStep] = Field(max_length=8)


class Question(Strict):
    field: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=1000)
    candidate_id: str | None = None


class AgentResult(Strict):
    status: Literal["completed", "needs_input", "blocked"]
    summary: str = Field(max_length=3000)
    artifact_ids: list[str] = Field(max_length=20)
    questions: list[Question] = Field(max_length=30)
    # Only planning uses this field; other phases must return null.
    plan: Plan | None = None


class FactCandidate(Strict):
    decision_type: Kind
    field: str
    value: str = Field(min_length=1, max_length=100)
    unit: str = Field(min_length=1, max_length=100)
    source_id: str
    location: str = Field(min_length=1, max_length=200)
    evidence: str = Field(min_length=1, max_length=1000)


class SourceEvidence(Strict):
    source_id: str
    location: str = Field(min_length=1, max_length=200)
    quote: str = Field(min_length=1, max_length=1000)


class WorkspaceEntry(Strict):
    subject: str = Field(min_length=1, max_length=200)
    attribute: str = Field(min_length=1, max_length=200)
    value: str = Field(min_length=1, max_length=2000)
    unit: str = Field(max_length=100)
    period: str = Field(max_length=200)
    status: Literal["observed", "assumed", "uncertain", "conflicting"]
    notes: str = Field(max_length=2000)
    evidence: list[SourceEvidence] = Field(min_length=1, max_length=10)


class InputRef(Strict):
    field: str
    fact_id: str


class WorkspaceInput(Strict):
    entry_id: str
    field: str
    value: str = Field(min_length=1, max_length=100)
    unit: str = Field(min_length=1, max_length=100)


class Answer(Strict):
    question_id: str
    value: Decimal | None = Field(default=None, ge=0, le=10000000)
    accept_candidate: bool = False
    reject_candidate: bool = False
    unit: str | None = Field(default=None, max_length=100)


class Answers(Strict):
    answers: list[Answer] = Field(min_length=1, max_length=30)


class DecisionCreate(Strict):
    business_id: str
    calculation_id: str
    title: str = Field(min_length=1, max_length=200)
    selected_scenario: Literal["Pessimistic", "Base case", "Optimistic"] = "Base case"


class StatusUpdate(Strict):
    status: Literal["planned", "implemented", "canceled"]


class OutcomeInput(Strict):
    period: int = Field(ge=1, le=60)
    actual_savings: Decimal | None = Field(default=None, ge=-10000000, le=10000000)
    attendance: Decimal | None = Field(default=None, ge=0, le=10000000)
    revenue: Decimal | None = Field(default=None, ge=0, le=100000000)
    costs: Decimal | None = Field(default=None, ge=0, le=100000000)
    repeat_contribution: Decimal | None = Field(default=None, ge=0, le=100000000)
    notes: str = Field(default="", max_length=2000)


class RiskFinding(Strict):
    description: str = Field(min_length=1, max_length=1000)
    severity: Literal["info", "review_required"]
    evidence_ids: list[str] = Field(max_length=10)
