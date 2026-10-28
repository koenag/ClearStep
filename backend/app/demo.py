"""Only this server-controlled seed can mark source content AI-eligible."""

import csv
import io
import random
from datetime import date, timedelta

from app.contracts import EventInput, SupplierInput
from app.service import input_unit


def seed_demo(services):
    existing = [b for b in services.store.list("business") if b["data"].get("seeded_demo")]
    if existing:
        return existing[0]
    business = services.store.create(
        "business",
        {
            "name": "Juniper Coffee (fictional)",
            "industry": "Coffee shop",
            "seeded_demo": True,
            "currency": "USD",
        },
        key="demo_business_v2",
    )
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["date", "product", "quantity", "unit_price", "unit_cost"])
    rng = random.Random(42)
    for n in range(92):
        day = date(2026, 7, 1) + timedelta(days=n)
        for name, price, cost, mean in [
            ("Latte", "5.50", "1.80", 42),
            ("Cappuccino", "5.00", "1.65", 29),
            ("Americano", "3.75", ".95", 33),
            ("Cold brew", "5.25", "1.45", 23),
            ("Croissant", "4.25", "1.85", 27),
        ]:
            q = max(1, round(mean * (1.25 if day.weekday() > 4 else 1) * rng.uniform(0.75, 1.25)))
            writer.writerow([day.isoformat(), name, q, price, cost])
    services.upload(business["id"], "fictional_sales.csv", out.getvalue().encode(), seeded=True)
    examples = {
        "supplier_switch": SupplierInput(
            current_unit_cost=12,
            new_unit_cost=10,
            monthly_quantity=100,
            current_shipping=40,
            new_shipping=50,
            switching_cost=400,
        ),
        "promotional_event": EventInput(
            event_cost=500,
            incremental_visits=120,
            average_spend=9,
            contribution_margin=".65",
            repeat_rate=".2",
            repeat_visits=2,
            staffing_cost=150,
        ),
    }
    text = "SERVER-GENERATED FICTIONAL ASSUMPTIONS. Not historical facts.\n"
    for kind, model in examples.items():
        text += (
            kind
            + "\n"
            + "\n".join(f"{k} = {v} {input_unit(k)}" for k, v in model.model_dump().items())
            + "\n"
        )
    source = services.upload(
        business["id"], "fictional_assumptions.txt", text.encode(), seeded=True
    )
    for kind, model in examples.items():
        for field, value in model.model_dump().items():
            services.store.create(
                "fact",
                {
                    "decision_type": kind,
                    "field": field,
                    "value": str(value),
                    "unit": input_unit(field),
                    "source_id": source["id"],
                    "location": "server seed",
                    "provenance": "assumed",
                    "status": "accepted",
                    "ai_eligible": True,
                    "note": "Explicit fictional demo assumption; not inferred from sales.",
                },
                business["id"],
            )
    return business
