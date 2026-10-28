import pytest
from app.contracts import EventInput, SupplierInput
from app.financial.engine import analyze, event, supplier
from pydantic import ValidationError


def s(**kwargs):
    return SupplierInput(current_unit_cost=12, new_unit_cost=10, monthly_quantity=100, **kwargs)


def test_supplier_cash_and_payback():
    r = supplier(s(switching_cost=400))
    assert r["current_monthly_cost"] == 1200
    assert r["proposed_monthly_cost"] == 1000
    assert r["monthly_savings"] == 200
    assert r["net_benefit"] == 2000
    assert r["roi"] == 500
    assert r["break_even_month"] == 2
    assert r["upfront_cash"] == 1400
    assert r["timeline"][0]["cumulative"] == -200


def test_negative_and_high_switching_costs():
    r = supplier(SupplierInput(current_unit_cost=10, new_unit_cost=12, monthly_quantity=100))
    assert r["net_benefit"] == -2400 and r["break_even_month"] is None
    assert supplier(s(switching_cost=3000))["break_even_month"] is None


def test_zero_demand():
    r = supplier(
        SupplierInput(
            current_unit_cost=12,
            new_unit_cost=10,
            monthly_quantity=0,
            new_moq=500,
            current_shipping=50,
            new_shipping=50,
            switching_cost=400,
        )
    )
    assert r["current_total"] == r["proposed_total"] == 0
    assert r["net_benefit"] == -400 and r["break_even_month"] is None


def test_inventory_cash_and_fifo():
    r = supplier(s(new_moq=500, horizon=2))
    assert r["proposed_total"] == 5000
    assert r["consumed_cost_savings"] == 400
    assert r["ending_proposed_inventory"] == 300
    escalated = supplier(s(new_moq=200, horizon=2, new_escalation=".12"))
    assert escalated["consumed_cost_savings"] == 400


def test_sustained_not_first_crossing():
    r = supplier(s(new_moq=300, horizon=6))
    assert [m["cumulative"] for m in r["timeline"]] == [-1800, -600, 600, -1200, 0, 1200]
    assert r["break_even_month"] == 5


def test_event_contribution_and_whole_visit_break_even():
    r = event(
        EventInput(
            event_cost=500,
            incremental_visits=100,
            average_spend=10,
            contribution_margin=".6",
            repeat_rate=".2",
            repeat_visits=2,
            staffing_cost=100,
        )
    )
    assert r["event_revenue"] == 1000
    assert r["event_contribution"] == 600
    assert r["repeat_contribution"] == 240
    assert r["total_cost"] == 600
    assert r["net_benefit"] == 240 and r["roi"] == 40
    assert r["break_even_visits"] == 72 and r["timeline"] == []


def test_zero_investment_and_zero_margin():
    assert supplier(s())["roi"] is None
    r = event(
        EventInput(event_cost=100, incremental_visits=1, average_spend=5, contribution_margin=0)
    )
    assert r["net_benefit"] == -100 and r["break_even_visits"] is None


@pytest.mark.parametrize(
    "kind,inputs",
    [
        (
            "supplier_switch",
            {"current_unit_cost": 12, "new_unit_cost": 10, "monthly_quantity": 100},
        ),
        (
            "promotional_event",
            {
                "event_cost": 500,
                "incremental_visits": 100,
                "average_spend": 10,
                "contribution_margin": ".6",
                "repeat_rate": ".2",
                "repeat_visits": 2,
            },
        ),
    ],
)
def test_scenario_order(kind, inputs):
    r = analyze(kind, inputs)
    n = [s["result"]["net_benefit"] for s in r["scenarios"]]
    assert n[0] < n[1] < n[2]


@pytest.mark.parametrize("value", [-1, "NaN", "Infinity", "-Infinity"])
def test_invalid_amounts(value):
    with pytest.raises(ValidationError):
        SupplierInput(current_unit_cost=value, new_unit_cost=10, monthly_quantity=1)


def test_invalid_model_and_horizon():
    with pytest.raises(ValueError, match="Unsupported"):
        analyze("hire", {})
    with pytest.raises(ValidationError):
        s(horizon=0)


def test_upfront_cash_rounds_only_at_boundary():
    r = supplier(
        SupplierInput(
            current_unit_cost="2", new_unit_cost="1.004", monthly_quantity=1, switching_cost=".004"
        )
    )
    assert r["upfront_cash"] == 1.01
