import csv
import importlib.util
import io
import json
from decimal import Decimal
from pathlib import Path

from app import demo
from app.financial.engine import analyze


def test_poc_records_define_pounds_and_full_year_pricing():
    manifest, files, _ = demo.load_bundle()
    settings = files["analysis_settings.txt"].decode()
    notes = files["owner_stock_and_switch_notes.txt"].decode()
    quote = files["alternative_supplier_quote_email.txt"].decode()
    current = files["current_supplier_invoices.txt"].decode()
    assert "Forecast horizon: 12 months." in settings
    assert "1 unit = 1 pound (lb)" in settings
    assert "units/month means lb/month" in settings
    assert "100 units/month = 100 lb/month" in settings
    assert "not the forecast horizon" in notes
    for record in [quote, current]:
        assert "2026-11-01 through" in record and "2027-10-31" in record
        assert "50-200 lb" in record
    assert "Prices beyond that date are not guaranteed" not in quote
    inputs = {
        f["field"]: f["value"] for f in manifest["facts"] if f["decision_type"] == "supplier_switch"
    }
    base = analyze("supplier_switch", inputs)["scenarios"][1]["result"]
    assert base["horizon"] == 12 and base["net_benefit"] == 1880


def test_demo_record_sources_and_provenance_reconcile(seeded):
    services, business = seeded
    manifest, files, fingerprint = demo.load_bundle()
    assert business["data"]["dataset_sha256"] == fingerprint
    assert len(files) == 6 and len(manifest["facts"]) == 25
    rows = list(csv.DictReader(io.StringIO(files["pos_sales_jul_sep.csv"].decode())))
    revenue = sum(Decimal(r["Net Sales"]) for r in rows)
    assert revenue == Decimal("57855.75")
    assert sum(Decimal(r["Gross Sales"]) - Decimal(r["Discount"]) for r in rows) == revenue
    baseline = services.baseline(business["id"])
    assert baseline["revenue"] == float(revenue)
    assert baseline["transactions"] == len({(r["Date"], r["Receipt"]) for r in rows}) == 8297
    assert baseline["line_items"] == len(rows) == 11478
    assert baseline["contribution_margin"] is None
    facts = services.store.list("fact", business["id"])
    for fact in facts:
        source = services.source(fact["data"]["source_id"], business["id"])
        assert any(fact["data"]["evidence"] in c["text"] for c in source["data"]["chunks"])
    current = next(f for f in facts if f["data"]["field"] == "current_unit_cost")
    forecast = next(f for f in facts if f["data"]["field"] == "monthly_quantity")
    margin = next(f for f in facts if f["data"]["field"] == "contribution_margin")
    assert current["data"]["provenance"] == "observed"
    assert forecast["data"]["provenance"] == margin["data"]["provenance"] == "assumed"


def test_new_bundle_does_not_replace_historical_business(backend):
    services = backend[0].state.services
    old = services.store.create("business", {"name": "Old demo", "seeded_demo": True})
    marker = services.store.create("run", {"status": "blocked", "original": "preserve"}, old["id"])
    current = demo.seed_demo(services)
    assert current["id"] != old["id"]
    assert services.store.get(marker["id"])["data"]["original"] == "preserve"
    assert demo.seed_demo(services)["id"] == current["id"]


def test_fixture_changes_use_a_new_business_and_validate_before_writes(
    seeded, tmp_path, monkeypatch
):
    services, original = seeded
    folder = tmp_path / "edited_fixture"
    folder.mkdir()
    manifest, files, _ = demo.load_bundle()
    (folder / "manifest.json").write_text(json.dumps(manifest))
    for name, content in files.items():
        (folder / name).write_bytes(content)
    notes = folder / "owner_stock_and_switch_notes.txt"
    notes.write_text(notes.read_text() + "\nAdditional fictional context.\n")
    monkeypatch.setattr(demo, "DEMO_FOLDER", folder)
    new = demo.seed_demo(services)
    assert new["id"] != original["id"]
    assert (
        services.business(original["id"])["data"]["dataset_sha256"]
        == original["data"]["dataset_sha256"]
    )
    count = len(services.store.list("business"))
    manifest["facts"][0]["evidence"] = "A quotation absent from every record."
    (folder / "manifest.json").write_text(json.dumps(manifest))
    # The old mapping is reference-only; it no longer drives financial extraction.
    fresh = demo.seed_demo(services)
    assert len(services.store.list("business")) == count + 1
    assert services.store.list("fact", fresh["id"]) == []


def test_preview_and_source_bundle_can_be_rebuilt_deterministically(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[1] / "scripts" / "build_demo_data.py"
    spec = importlib.util.spec_from_file_location("build_records", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "FOLDER", tmp_path / "records")
    module.build()
    for file in demo.DEMO_FOLDER.iterdir():
        if file.is_file() and file.suffix in [".json", ".txt", ".csv", ".html"]:
            assert (module.FOLDER / file.name).read_bytes() == file.read_bytes(), file.name
    page = (module.FOLDER / "index.html").read_text()
    assert "no unit costs or margin" in page.lower()
    assert "Currently supported questions" in page


def test_source_content_api_is_scoped_and_readable(backend, seeded):
    _, client, _ = backend
    services, business = seeded
    source = next(
        s
        for s in services.store.list("source", business["id"])
        if s["data"]["filename"] == "alternative_supplier_quote_email.txt"
    )
    result = client.get(f"/api/businesses/{business['id']}/sources/{source['id']}")
    assert result.status_code == 200
    assert "$50.00 per shipment" in result.json()["chunks"][0]["text"]
    assert "storage_name" not in result.json()["data"]
    other = client.post("/api/businesses", json={"name": "Other"}).json()
    assert client.get(f"/api/businesses/{other['id']}/sources/{source['id']}").status_code == 404
