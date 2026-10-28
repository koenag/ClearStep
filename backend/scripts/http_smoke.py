"""Exercise the running local API without invoking OpenAI. Creates fictional records."""

import argparse

import httpx


def main():
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--url", default="http://127.0.0.1:8000")
    options = args.parse_args()
    with httpx.Client(base_url=options.url, timeout=15, trust_env=False) as client:
        health = client.get("/api/health")
        health.raise_for_status()
        business = client.post("/api/demo/seed")
        business.raise_for_status()
        business = business.json()
        baseline = client.get(f"/api/businesses/{business['id']}/baseline")
        baseline.raise_for_status()
        assert baseline.json()["revenue"] == 72793
        calc = client.post(
            f"/api/businesses/{business['id']}/analyses",
            json={
                "decision_type": "supplier_switch",
                "inputs": {
                    "current_unit_cost": 12,
                    "new_unit_cost": 10,
                    "monthly_quantity": 100,
                    "current_shipping": 40,
                    "new_shipping": 50,
                    "switching_cost": 400,
                },
            },
        )
        calc.raise_for_status()
        calc = calc.json()
        base = calc["data"]["analysis"]["scenarios"][1]["result"]
        assert base["net_benefit"] == 1880 and base["break_even_month"] == 3
        decision = client.post(
            "/api/decisions",
            json={
                "business_id": business["id"],
                "calculation_id": calc["id"],
                "title": "Fictional HTTP smoke comparison",
            },
        )
        decision.raise_for_status()
        decision = decision.json()
        outcome = client.post(
            f"/api/decisions/{decision['id']}/outcomes", json={"period": 1, "actual_savings": 175}
        )
        outcome.raise_for_status()
        assert outcome.json()["data"]["variance"] == -15
        reopened = client.get("/api/decisions/" + decision["id"])
        reopened.raise_for_status()
        assert reopened.json()["data"]["snapshot"] == calc["data"]["analysis"]
        event = client.post(
            f"/api/businesses/{business['id']}/analyses",
            json={
                "decision_type": "promotional_event",
                "inputs": {
                    "event_cost": 500,
                    "incremental_visits": 120,
                    "average_spend": 9,
                    "contribution_margin": ".65",
                    "repeat_rate": ".2",
                    "repeat_visits": 2,
                    "staffing_cost": 150,
                },
            },
        )
        event.raise_for_status()
        assert event.json()["data"]["analysis"]["scenarios"][1]["result"]["net_benefit"] == 332.8
        schema = client.get("/openapi.json")
        schema.raise_for_status()
        assert "/api/runs" in schema.json()["paths"]
        print(
            "PASS: health, fictional seed/baseline, supplier/event arithmetic, save/reopen, actual variance and OpenAPI. No agent/model calls."
        )


if __name__ == "__main__":
    main()
