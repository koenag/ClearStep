"""Local-only configuration. No provider calls occur just by importing the app."""

import os
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    data_dir: Path = ROOT / "backend" / "var"
    database_url: str | None = None
    openai_model: str = "gpt-6-luna"
    openai_api_key: str = field(default="", repr=False)
    max_upload_bytes: int = 5 * 1024 * 1024
    max_rows: int = 20000
    max_pdf_pages: int = 50
    max_document_chars: int = 150000
    max_agent_turns: int = 6
    max_run_calls: int = 24
    max_tool_calls: int = 60
    max_output_tokens: int = 4000
    max_context_chars: int = 60000
    max_run_seconds: int = 300
    run_budget_usd: Decimal = Decimal("0.10")
    input_price_per_million: Decimal = Decimal("0.10")
    cached_price_per_million: Decimal = Decimal("0.01")
    output_price_per_million: Decimal = Decimal("0.50")
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")

    @classmethod
    def from_env(cls):
        env = {**dotenv_values(ROOT / ".env"), **os.environ}
        return cls(
            data_dir=Path(env.get("DATA_DIR") or ROOT / "backend" / "var").resolve(),
            database_url=env.get("DATABASE_URL") or None,
            openai_model=env.get("OPENAI_MODEL") or "gpt-6-luna",
            openai_api_key=env.get("OPENAI_API_KEY") or "",
            run_budget_usd=Decimal(env.get("RUN_BUDGET_USD") or "0.10"),
            cors_origins=tuple((env.get("CORS_ORIGINS") or ",".join(cls.cors_origins)).split(",")),
        )

    def validate(self, *, require_api_key=True):
        if not self.run_budget_usd.is_finite() or self.run_budget_usd <= 0:
            raise ValueError("RUN_BUDGET_USD must be finite and positive.")
        if self.openai_model != "gpt-6-luna":
            raise ValueError(
                "Only gpt-6-luna pricing is configured. Add verified pricing before switching models."
            )
        if require_api_key and not self.openai_api_key.strip():
            raise ValueError(
                "Set OPENAI_API_KEY in the root .env before starting the live backend."
            )


class DomainError(Exception):
    def __init__(self, code: str, message: str, status: int = 422):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)


class LimitReached(DomainError):
    def __init__(self, message="Run execution limit reached."):
        super().__init__("limit_reached", message, 409)
