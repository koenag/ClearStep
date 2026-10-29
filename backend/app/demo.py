"""Seed only raw synthetic documents; financial facts must be extracted and reviewed.

The old manifest's fact mapping is reference material, never loaded as accepted facts.
"""

import hashlib
import json
from pathlib import Path

from app.data import parse_file

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
        and b["data"].get("extraction_mode") == "documents"
    ]
    if existing:
        return existing[0]
    # Parse all files before writing a new business.
    parsed = {name: parse_file(name, content, services.settings) for name, content in files.items()}
    # New datasets get a separate business. Historical inputs/runs stay intact.
    business = services.store.create(
        "business",
        {
            "name": "Juniper Coffee (fictional business records)",
            "industry": "Coffee shop",
            "seeded_demo": True,
            "extraction_mode": "documents",
            "currency": "USD",
            "dataset_version": manifest["dataset_version"],
            "dataset_sha256": fingerprint,
        },
        key="demo_documents:" + fingerprint,
    )
    for name, content in files.items():
        services.upload(business["id"], name, content, _parsed=parsed[name])
    return business
