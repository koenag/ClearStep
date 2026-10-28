"""Explicit LIVE, PAID integration check using only the server-seeded fictional café.

Requires OPENAI_API_KEY and LIVE_API_CALLS_ENABLED=true. Not part of automated tests.
"""

import asyncio
import json
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import Settings
from app.contracts import RunRequest
from app.demo import seed_demo
from app.main import create_app


async def main():
    settings = Settings.from_env()
    settings.validate()
    if not settings.live_api_calls_enabled:
        raise SystemExit("Live calls are disabled. This script makes paid API calls when enabled.")
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        s = app.state.services
        business = seed_demo(s)
        run = app.state.executor.create_run(
            RunRequest(
                business_id=business["id"],
                question="Should I switch coffee bean suppliers? Use the fictional accepted demo inputs.",
            )
        )
        await app.state.executor.execute(run["id"])
        result = s.store.get(run["id"])
        usage = s.store.list("usage", run_id=run["id"])
        print(
            json.dumps(
                {
                    "run_id": run["id"],
                    "status": result["data"]["status"],
                    "estimated_cost_usd": str(
                        sum((Decimal(u["data"]["estimated_cost_usd"]) for u in usage), Decimal(0))
                    ),
                    "error": result["data"]["error"],
                    "summary": (result["data"].get("report") or {}).get("summary"),
                },
                indent=2,
            )
        )
        if result["data"]["status"] != "completed":
            raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
