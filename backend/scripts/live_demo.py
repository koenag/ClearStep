"""Run a live, paid OpenAI demo and export its available inputs and saved outputs.

There is no offline switch or simulated-model option. Test doubles exist only in tests.
"""

import argparse
import asyncio
import json
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import Settings
from app.contracts import RunRequest
from app.data import SUPPORTED, parse_file
from app.demo import DEMO_FOLDER, seed_demo
from app.main import create_app

DEFAULT_QUESTION = "Should I switch coffee bean suppliers? Extract inputs from the supplied documents and ask me to review them."


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    path.chmod(0o600)


def load_folder(services, folder):
    """Load a flat batch of supported files, reusing an unchanged batch on later runs."""
    import hashlib

    files = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED)
    if not files:
        raise ValueError("The input folder contains no supported files.")
    payloads = [(p.name, p.read_bytes()) for p in files]
    digest = hashlib.sha256()
    for name, content in payloads:
        digest.update(json.dumps([name, len(content)]).encode())
        digest.update(content)
    fingerprint = digest.hexdigest()
    for business in services.store.list("business"):
        if business["data"].get("folder_sha256") == fingerprint:
            return business
    parsed = {name: parse_file(name, content, services.settings) for name, content in payloads}
    business = services.store.create(
        "business",
        {"name": folder.name, "currency": "USD", "folder_sha256": fingerprint},
        key="input_folder:" + fingerprint,
    )
    for name, content in payloads:
        services.upload(business["id"], name, content, _parsed=parsed[name])
    return business


async def run_demo(settings, question, input_folder=None):
    settings.validate()
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        services = app.state.services
        business = load_folder(services, input_folder) if input_folder else seed_demo(services)
        run = app.state.executor.create_run(
            RunRequest(business_id=business["id"], question=question)
        )
        folder = settings.data_dir / "runs" / run["id"]
        sources = [
            services.source_view(source)
            for source in services.store.list("source", business["id"])
            if source["data"]["ai_eligible"]
        ]
        facts = [
            fact
            for fact in services.store.list("fact", business["id"])
            if fact["data"]["ai_eligible"]
        ]
        write_json(
            folder / "inputs.json",
            {
                "run_id": run["id"],
                "business_id": business["id"],
                "dataset_version": business["data"].get("dataset_version"),
                "dataset_sha256": business["data"].get("dataset_sha256"),
                "model": settings.openai_model,
                "question": question,
                "available_sources": sources,
                "available_facts": facts,
                "note": "Available business inputs at launch, not a full model request transcript.",
            },
        )
        print(f"Input records: {input_folder or DEMO_FOLDER}", flush=True)
        print(f"Run: {run['id']}", flush=True)
        print(f"Question: {question}", flush=True)
        print(f"Inputs: {(folder / 'inputs.json').resolve()}", flush=True)
        await app.state.executor.execute(run["id"])
        result = services.store.get(run["id"])
        snapshot = {"run": result}
        for kind, name in [
            ("task", "tasks"),
            ("question", "questions"),
            ("usage", "usage"),
            ("event", "events"),
            ("artifact", "artifacts"),
            ("calculation", "calculations"),
            ("fact", "facts"),
        ]:
            snapshot[name] = services.store.list(kind, run_id=run["id"])
        snapshot["workspace"] = [
            a for a in snapshot["artifacts"] if a["data"].get("type") == "workspace_entry"
        ]
        write_json(folder / "outputs.json", snapshot)
        print(
            json.dumps(
                {
                    "run_id": run["id"],
                    "status": result["data"]["status"],
                    "estimated_cost_usd": str(
                        sum(
                            (Decimal(u["data"]["estimated_cost_usd"]) for u in snapshot["usage"]),
                            Decimal(0),
                        )
                    ),
                    "error": result["data"]["error"],
                    "summary": (result["data"].get("report") or {}).get("summary"),
                    "stopped_tasks": [
                        {"role": task["data"]["role"], "result": task["data"].get("result")}
                        for task in snapshot["tasks"]
                        if task["data"]["status"] in ["blocked", "needs_input"]
                    ],
                    "outputs_file": str((folder / "outputs.json").resolve()),
                },
                indent=2,
            ),
            flush=True,
        )
        return 0 if result["data"]["status"] == "completed" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--question",
        default=DEFAULT_QUESTION,
        help="Business question to answer using the supplied records.",
    )
    parser.add_argument(
        "--input-folder",
        type=Path,
        help="Folder of CSV/XLSX/TXT/text-PDF files. Excerpts may be sent to OpenAI. Nonrecursive.",
    )
    args = parser.parse_args()
    return asyncio.run(run_demo(Settings.from_env(), args.question, args.input_folder))


if __name__ == "__main__":
    raise SystemExit(main())
