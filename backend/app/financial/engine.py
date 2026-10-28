"""Pure deterministic models. Decimal arithmetic; HALF_UP rounding at output only."""

from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

from app.contracts import AnalysisOutput, EventInput, SupplierInput

VERSION = "2.0.0"
D = Decimal


def money(value):
    return float(D(value).quantize(D(".01"), rounding=ROUND_HALF_UP))


def consume(lots, quantity):
    cost = D(0)
    while quantity > 0:
        amount = min(quantity, lots[0][0])
        cost += amount * lots[0][1]
        quantity -= amount
        lots[0][0] -= amount
        if lots[0][0] == 0:
            lots.pop(0)
    return cost


def supplier(x: SupplierInput):
    current_stock = proposed_stock = D(0)
    current_lots = []
    proposed_lots = []
    raw_cumulative = []
    cumulative = -x.switching_cost
    rows = []
    current_total = proposed_total = D(0)
    current_consumed = proposed_consumed = D(0)
    for month in range(1, x.horizon + 1):
        cp = x.current_unit_cost * (1 + x.current_escalation) ** (D(month - 1) / 12)
        np = x.new_unit_cost * (1 + x.new_escalation) ** (D(month - 1) / 12)
        # Buy only when inventory cannot cover demand; MOQ is a minimum batch.
        cq = max(x.monthly_quantity - current_stock, D(0))
        nq = max(x.monthly_quantity - proposed_stock, D(0))
        if cq > 0:
            cq = max(cq, D(x.current_moq))
        if nq > 0:
            nq = max(nq, D(x.new_moq))
        current_stock += cq - x.monthly_quantity
        proposed_stock += nq - x.monthly_quantity
        cc = cq * cp + (x.current_shipping if cq else 0)
        nc = nq * np + (x.new_shipping if nq else 0)
        if month == 1:
            first_purchase = nc
        current_total += cc
        proposed_total += nc
        if cq:
            current_lots.append([cq, cp])
        if nq:
            proposed_lots.append([nq, np])
        current_consumed += consume(current_lots, x.monthly_quantity)
        proposed_consumed += consume(proposed_lots, x.monthly_quantity)
        cumulative += cc - nc
        raw_cumulative.append(cumulative)
        rows.append(
            dict(
                month=month,
                current_cost=money(cc),
                proposed_cost=money(nc),
                savings=money(cc - nc),
                cumulative=money(cumulative),
                current_inventory=float(current_stock),
                proposed_inventory=float(proposed_stock),
            )
        )
    # Sustained cash payback: later bulk orders must not reverse it within the horizon.
    payback = next(
        (r["month"] for i, r in enumerate(rows) if all(t >= 0 for t in raw_cumulative[i:])),
        None,
    )
    net = current_total - proposed_total - x.switching_cost
    return dict(
        net_benefit=money(net),
        monthly_savings=money((current_total - proposed_total) / x.horizon),
        current_monthly_cost=money(current_total / x.horizon),
        proposed_monthly_cost=money(proposed_total / x.horizon),
        switching_cost=money(x.switching_cost),
        upfront_cash=money(x.switching_cost + first_purchase),
        roi=money(net / x.switching_cost * 100) if x.switching_cost else None,
        roi_basis="One-time switching cost; procurement spend is compared in cash flows.",
        break_even_month=payback,
        horizon=x.horizon,
        current_total=money(current_total),
        proposed_total=money(proposed_total),
        consumed_cost_savings=money(current_consumed - proposed_consumed),
        ending_current_inventory=float(current_stock),
        ending_proposed_inventory=float(proposed_stock),
        timeline=rows,
    )


def event(x: EventInput):
    revenue = x.incremental_visits * x.average_spend
    contribution = revenue * x.contribution_margin
    repeat = contribution * x.repeat_rate * x.repeat_visits
    costs = x.event_cost + x.staffing_cost
    per_visit = x.average_spend * x.contribution_margin * (1 + x.repeat_rate * x.repeat_visits)
    net = contribution + repeat - costs
    return dict(
        net_benefit=money(net),
        event_revenue=money(revenue),
        event_contribution=money(contribution),
        repeat_contribution=money(repeat),
        total_cost=money(costs),
        upfront_cash=money(costs),
        roi=money(net / costs * 100) if costs else None,
        roi_basis="Event plus additional staffing costs.",
        break_even_visits=int((costs / per_visit).to_integral_value(rounding=ROUND_CEILING))
        if per_visit
        else (0 if not costs else None),
        horizon=x.horizon,
        timeline=[],
    )


def analyze(kind, raw, provenance=None):
    if kind not in ("supplier_switch", "promotional_event"):
        raise ValueError("Unsupported financial model.")
    cls, calculate = (SupplierInput, supplier) if kind == "supplier_switch" else (EventInput, event)
    x = cls.model_validate(raw)
    scenarios = []
    for name, sign in [("Pessimistic", -1), ("Base case", 0), ("Optimistic", 1)]:
        data = x.model_dump()
        if kind == "supplier_switch":
            data["monthly_quantity"] *= 1 + sign * x.demand_variation
            data["new_unit_cost"] *= 1 - sign * x.cost_variation
        else:
            data["incremental_visits"] *= 1 + sign * x.attendance_variation
            data["average_spend"] *= 1 + sign * x.spend_variation
            data["repeat_rate"] = min(D(1), x.repeat_rate * (1 + sign * x.repeat_variation))
            data["event_cost"] *= 1 - sign * x.expense_variation
            data["staffing_cost"] *= 1 - sign * x.expense_variation
        validated = cls.model_validate(data)
        scenarios.append(
            dict(
                name=name,
                inputs=validated.model_dump(mode="json"),
                result=calculate(validated),
            )
        )
    base = scenarios[1]["result"]
    assumptions = [
        dict(
            name=k,
            value=float(v),
            unit="months"
            if k == "horizon"
            else (
                "ratio"
                if any(t in k for t in ["rate", "margin", "variation", "escalation"])
                else "USD per unit"
                if k in ["current_unit_cost", "new_unit_cost"]
                else "USD per visit"
                if k == "average_spend"
                else "USD"
                if any(t in k for t in ["cost", "shipping"])
                else "units per month"
                if k == "monthly_quantity"
                else "visits per retained customer"
                if k == "repeat_visits"
                else "visits"
                if k == "incremental_visits"
                else "units"
            ),
            provenance=(provenance or {}).get(k, "user" if k in raw else "assumed"),
            editable=True,
        )
        for k, v in x.model_dump().items()
    ]
    if kind == "supplier_switch":
        risks = [
            "Demand is constant within each scenario; supplier reliability and product quality are not priced.",
            "Inventory starts at zero, carries forward without spoilage, and has no terminal resale credit. Shipping is charged per purchase month.",
            "Escalation is an effective annual rate applied monthly. Break-even is sustained through the modeled horizon.",
        ]
        if x.current_moq or x.new_moq:
            risks.append(
                "Minimum order batches can tie up cash; cash savings differ from inventory consumed."
            )
        summary = f"{'Switching is projected to save' if base['net_benefit'] > 0 else 'Staying avoids a projected loss of'} ${abs(base['net_benefit']):,.2f} over {x.horizon} months."
        if base["net_benefit"] == 0:
            summary = f"Switching has no net cash benefit over {x.horizon} months under the base assumptions."
    else:
        risks = [
            "Visits must be incremental to normal trade; attribution is supplied by the user.",
            "Repeat visits are cumulative over the horizon; their timing and causal attribution are unknown.",
            "Contribution margin includes variable product costs. Event and additional staffing costs must not overlap.",
        ]
        summary = f"The event has a projected {'net benefit' if base['net_benefit'] >= 0 else 'net loss'} of ${abs(base['net_benefit']):,.2f} over {x.horizon} months."
    return AnalysisOutput.model_validate(
        dict(
            decision_type=kind,
            inputs=x.model_dump(mode="json"),
            scenarios=scenarios,
            summary=summary,
            assumptions=assumptions,
            risks=risks,
            calculation_version=VERSION,
            scenario_note="Illustrative sensitivities, not calibrated probabilities. Scenario labels may not rank cash outcomes when minimum orders apply.",
        )
    ).model_dump(mode="json")
