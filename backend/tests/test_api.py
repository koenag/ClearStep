import pytest
from app.config import Settings
from app.main import create_app
from conftest import final
from fastapi.testclient import TestClient


def test_local_workflow_persistence_and_outcomes(backend, seeded):
    app, c, _ = backend
    s, b = seeded
    assert c.get("/api/health").json()["research_enabled"] is False
    baseline = c.get(f"/api/businesses/{b['id']}/baseline").json()
    assert baseline["revenue"] == 72793 and baseline["variable_costs"] == 23566
    assert baseline["contribution_profit"] == 49227 and baseline["transactions"] is None
    assert c.post("/api/demo/seed").json()["id"] == b["id"]
    req = {
        "decision_type": "supplier_switch",
        "inputs": {
            "current_unit_cost": 12,
            "new_unit_cost": 10,
            "monthly_quantity": 100,
            "switching_cost": 400,
        },
    }
    calc = c.post(f"/api/businesses/{b['id']}/analyses", json=req)
    assert calc.status_code == 201, calc.text
    id = calc.json()["id"]
    d = c.post(
        "/api/decisions",
        json={"business_id": b["id"], "calculation_id": id, "title": "Supplier comparison"},
    ).json()
    original = d["data"]["snapshot"]
    assert c.patch(f"/api/decisions/{d['id']}", json={"status": "implemented"}).status_code == 200
    result = c.post(f"/api/decisions/{d['id']}/outcomes", json={"period": 1, "actual_savings": 175})
    assert result.status_code == 201, result.text
    assert result.json()["data"]["expected"]["net_benefit"] == 200
    assert result.json()["data"]["variance"] == -25
    assert c.get(f"/api/decisions/{d['id']}").json()["data"]["snapshot"] == original
    assert (
        c.post(
            f"/api/decisions/{d['id']}/outcomes", json={"period": 1, "actual_savings": 175}
        ).status_code
        == 409
    )
    assert (
        c.post(
            f"/api/decisions/{d['id']}/outcomes", json={"period": 13, "actual_savings": 175}
        ).status_code
        == 422
    )


@pytest.mark.parametrize(
    "repeat,actual,expected,pending", [(None, -60, 0, True), (200, 140, 240, False)]
)
def test_event_actuals(backend, seeded, repeat, actual, expected, pending):
    _, c, _ = backend
    _, b = seeded
    calc = c.post(
        f"/api/businesses/{b['id']}/analyses",
        json={
            "decision_type": "promotional_event",
            "inputs": {
                "event_cost": 500,
                "incremental_visits": 100,
                "average_spend": 10,
                "contribution_margin": ".6",
                "repeat_rate": ".2",
                "repeat_visits": 2,
                "staffing_cost": 100,
            },
        },
    ).json()
    d = c.post(
        "/api/decisions",
        json={"business_id": b["id"], "calculation_id": calc["id"], "title": "Event"},
    ).json()
    r = c.post(
        f"/api/decisions/{d['id']}/outcomes",
        json={
            "period": 1 if repeat is None else 12,
            "attendance": 90,
            "revenue": 900,
            "costs": 600,
            "repeat_contribution": repeat,
        },
    ).json()["data"]
    assert r["actual"]["net_benefit"] == actual
    assert r["expected"]["net_benefit"] == expected and r["expected"]["repeat_pending"] == pending
    assert r["variance"] == actual - expected


def test_real_workspace_and_upload_policy(backend, seeded):
    app, c, _ = backend
    s, b = seeded
    real = c.post("/api/businesses", json={"name": "Private café"}).json()
    assert (
        c.post("/api/businesses", json={"name": "Impersonation", "seeded_demo": True}).status_code
        == 422
    )
    r = c.post(
        "/api/runs", json={"business_id": real["id"], "question": "Should I switch suppliers?"}
    )
    assert r.status_code == 403
    local = c.post(
        f"/api/businesses/{b['id']}/sources",
        files={"file": ("quote.txt", b"Private supplier terms", "text/plain")},
    )
    assert local.status_code == 201
    assert local.json()["data"]["ai_eligible"] is False
    assert "chunks" not in local.json()["data"]
    assert (
        c.post(
            f"/api/businesses/{b['id']}/sources", files={"file": ("bad.exe", b"code")}
        ).status_code
        == 415
    )
    assert c.get("/api/businesses/missing").status_code == 404


def test_live_api_disabled_by_default(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, database_url="sqlite://"))
    with TestClient(app) as c:
        b = c.post("/api/demo/seed").json()
        r = c.post(
            "/api/runs", json={"business_id": b["id"], "question": "Should I switch suppliers?"}
        )
        assert r.status_code == 503 and r.json()["error"]["code"] == "live_api_disabled"
        assert app.state.executor.jobs == {}


def test_sqlite_persists_without_global_import_side_effects(tmp_path):
    settings = Settings(data_dir=tmp_path)
    with TestClient(create_app(settings)) as c:
        b = c.post("/api/businesses", json={"name": "Persistent local business"}).json()
    with TestClient(create_app(settings)) as c:
        assert (
            c.get("/api/businesses/" + b["id"]).json()["data"]["name"]
            == "Persistent local business"
        )


def test_unknown_and_nonfinite_financial_inputs(backend, seeded):
    _, c, _ = backend
    _, b = seeded
    for value in ["NaN", "Infinity", -1]:
        r = c.post(
            f"/api/businesses/{b['id']}/analyses",
            json={
                "decision_type": "supplier_switch",
                "inputs": {
                    "current_unit_cost": value,
                    "new_unit_cost": 10,
                    "monthly_quantity": 100,
                },
            },
        )
        assert r.status_code == 422
    r = c.post(f"/api/businesses/{b['id']}/analyses", json={"decision_type": "hire", "inputs": {}})
    assert r.status_code == 422


def test_http_background_run_and_report(backend, seeded):
    import time

    app, c, _ = backend
    _, b = seeded
    created = c.post(
        "/api/runs", json={"business_id": b["id"], "question": "Should I switch suppliers?"}
    )
    assert created.status_code == 202
    id = created.json()["id"]
    for _ in range(100):
        response = c.get("/api/runs/" + id).json()
        if response["data"]["status"] in ["completed", "failed", "limit_reached"]:
            break
        time.sleep(0.01)
    assert response["data"]["status"] == "completed", response
    assert response["data"]["report"]["analysis"]["scenarios"][1]["result"]["net_benefit"] == 1880
    assert c.get("/api/runs/" + id + "/events").json()
    assert response["usage"] and all(u["data"]["status"] == "reported" for u in response["usage"])


def test_http_cancel_active_run(backend, seeded):
    import asyncio
    import time

    app, c, model = backend
    _, b = seeded

    async def slow(**kwargs):
        await asyncio.sleep(10)
        return final()

    model.respond = slow
    created = c.post(
        "/api/runs", json={"business_id": b["id"], "question": "Should I switch suppliers?"}
    ).json()
    canceled = c.post("/api/runs/" + created["id"] + "/cancel")
    assert canceled.status_code == 200
    time.sleep(0.02)
    assert c.get("/api/runs/" + created["id"]).json()["data"]["status"] == "canceled"


def test_shared_sqlite_connection_is_serialized_across_threads(seeded):
    from concurrent.futures import ThreadPoolExecutor

    services, b = seeded

    def write_read(n):
        record = services.store.create("artifact", {"thread_value": n}, b["id"])
        assert services.store.get(record["id"])["data"]["thread_value"] == n
        assert services.store.list("artifact", business_id=b["id"])
        return record["id"]

    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(write_read, range(100)))
    assert len(set(ids)) == 100
    assert len(services.store.list("artifact", business_id=b["id"])) == 100


def test_partial_event_repeats_do_not_claim_time_matched_variance(backend, seeded):
    _, c, _ = backend
    _, b = seeded
    calc = c.post(
        f"/api/businesses/{b['id']}/analyses",
        json={
            "decision_type": "promotional_event",
            "inputs": {
                "event_cost": 500,
                "incremental_visits": 100,
                "average_spend": 10,
                "contribution_margin": ".6",
                "repeat_rate": ".2",
                "repeat_visits": 2,
                "staffing_cost": 100,
            },
        },
    ).json()
    decision = c.post(
        "/api/decisions",
        json={
            "business_id": b["id"],
            "calculation_id": calc["id"],
            "title": "Partial repeat observations",
        },
    ).json()
    result = c.post(
        f"/api/decisions/{decision['id']}/outcomes",
        json={
            "period": 2,
            "attendance": 100,
            "revenue": 1000,
            "costs": 600,
            "repeat_contribution": 100,
        },
    ).json()["data"]
    assert result["actual"]["net_benefit"] == 100
    assert result["expected"]["full_horizon_net_benefit"] == 240
    assert result["expected"]["time_comparable"] is False and result["variance"] is None
