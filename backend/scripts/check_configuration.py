"""Check configuration without creating an OpenAI client or sending a request."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import Settings

settings = Settings.from_env()
settings.validate()
print("Model:", settings.openai_model)
print("API key configured:", bool(settings.openai_api_key))
print("Run mode: live (OpenAI API)")
print("Research: disabled")
print("AI data policy: seeded demo only")
print("Estimated run budget USD:", settings.run_budget_usd)
