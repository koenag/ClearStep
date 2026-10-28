"""Seed versioned synthetic records from an inspectable fixture bundle.

The manifest explicitly maps this known dataset to model inputs. It is demo
wiring, not a general document extractor or an owner-supplied business record.
"""

import hashlib
import json
from pathlib import Path

from app.data import parse_file
from app.service import INPUT_MODELS, input_unit

DEMO_FOLDER = Path(__file__).resolve().parents[1] / "demo_data" / "coffee_shop"


def load_bundle():
    manifest_bytes = (DEMO_FOLDER / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    sources = {}
    digest = hashlib.sha256(manifest_bytes)
    for filename in manifest["sources"]:
        if Path(filename).name != filename:
            raise ValueError("Demo source filenames must be simple local filenames.")
        content = (DEMO_FOLDER / filename).read_bytes()
        sources[filename] = content
        digest.update(filename.encode())
        digest.update(content)
    return manifest, sources, digest.hexdigest()


def seed_demo(services):
    manifest, files, fingerprint = load_bundle()
    existing = [
        b
        for b in services.store.list("business")
        if b["data"].get("seeded_demo") and b["data"].get("dataset_sha256") == fingerprint
    ]
    if existing:
        return existing[0]
    # Validate the complete fixture before writing anything, so editing an input
    # without its fact mapping cannot leave a half-seeded business behind.
    parsed = {name: parse_file(name, content, services.settings) for name, content in files.items()}
    for kind, model in INPUT_MODELS.items():
        inputs = {f["field"]: f["value"] for f in manifest["facts"] if f["decision_type"] == kind}
        if set(inputs) != set(model.model_fields):
            raise ValueError("Demo input index must explicitly cover all model fields.")
        model.model_validate(inputs)
    for fact in manifest["facts"]:
        chunks = parsed[fact["source"]]["chunks"]
        if not any(fact["evidence"] in c["text"] for c in chunks):
            raise ValueError("Demo evidence quotation is absent: " + fact["field"])
        services.validate_field(fact["decision_type"], fact["field"], fact["value"])
    # New datasets get a separate business. Historical inputs/runs stay intact.
    business = services.store.create(
        "business",
        {
            "name": "Juniper Coffee (fictional business records)",
            "industry": "Coffee shop",
            "seeded_demo": True,
            "currency": "USD",
            "dataset_version": manifest["dataset_version"],
            "dataset_sha256": fingerprint,
        },
        key="demo_records:" + fingerprint,
    )
    sources = {
        name: services.upload(business["id"], name, content, seeded=True, _parsed=parsed[name])
        for name, content in files.items()
    }
    for fact in manifest["facts"]:
        source = sources[fact["source"]]
        matches = [c for c in source["data"]["chunks"] if fact["evidence"] in c["text"]]
        if not matches:
            raise ValueError("Demo evidence quotation is absent: " + fact["field"])
        services.validate_field(fact["decision_type"], fact["field"], fact["value"])
        services.store.create(
            "fact",
            {
                "decision_type": fact["decision_type"],
                "field": fact["field"],
                "value": fact["value"],
                "unit": input_unit(fact["field"]),
                "source_id": source["id"],
                "location": matches[0]["location"],
                "evidence": fact["evidence"],
                "provenance": fact["provenance"],
                "status": "accepted",
                "ai_eligible": True,
                "note": fact["note"],
                "normalization": "Prepared demo index with source quotations; not general-purpose extraction.",
            },
            business["id"],
        )
    return business
