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
from app.demo import DEMO_FOLDER, seed_demo
from app.main import create_app

DEFAULT_QUESTION = "Should I switch coffee bean suppliers? Use the fictional accepted demo inputs."


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    path.chmod(0o600)


async def run_demo(settings, question):
    settings.validate()
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        services = app.state.services
        business = seed_demo(services)
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
        print(f"Demo records preview: {(DEMO_FOLDER / 'index.html').resolve()}", flush=True)
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
        ]:
            snapshot[name] = services.store.list(kind, run_id=run["id"])
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
        help="Business question and any explicitly accepted fictional assumptions.",
    )
    args = parser.parse_args()
    return asyncio.run(run_demo(Settings.from_env(), args.question))


if __name__ == "__main__":
    raise SystemExit(main())
