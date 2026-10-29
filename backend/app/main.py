"""Local API and buildless owner-facing interface."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from app.agents import AgentRunner
from app.config import DomainError, Settings
from app.contracts import (
    Answers,
    BusinessCreate,
    DecisionCreate,
    OutcomeInput,
    RunRequest,
    StatusUpdate,
)
from app.db import Store
from app.demo import seed_demo
from app.llm import OpenAIModel
from app.service import Services
from app.workflow import Executor
from app.workspace import query_entries


def create_app(settings=None, model=None):
    settings = settings or Settings.from_env()
    # Model injection is test-only; normal startup always requires the live provider key.
    settings.validate(require_api_key=model is None or isinstance(model, OpenAIModel))
    store = Store(settings)
    services = Services(store, settings)
    model = model or OpenAIModel(settings)
    executor = Executor(services, AgentRunner(services, model))

    @asynccontextmanager
    async def lifespan(app):
        executor.recover()
        yield
        await executor.close()
        await model.close()
        store.close()

    app = FastAPI(title="Business Decision Agents", version="2.0.0", lifespan=lifespan)
    app.state.services = services
    app.state.executor = executor
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Content-Type"],
    )

    @app.exception_handler(DomainError)
    async def domain_error(request, exc):
        return JSONResponse(
            status_code=exc.status, content={"error": {"code": exc.code, "message": exc.message}}
        )

    @app.exception_handler(RequestValidationError)
    @app.exception_handler(ValidationError)
    async def invalid(request, exc):
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "; ".join(str(e["loc"]) + ": " + e["msg"] for e in exc.errors()),
                }
            },
        )

    @app.exception_handler(ValueError)
    async def invalid_value(request, exc):
        return JSONResponse(
            status_code=422, content={"error": {"code": "invalid_value", "message": str(exc)[:500]}}
        )

    @app.get("/api/health")
    def health():
        return {
            "status": "ok",
            "model": settings.openai_model,
            "run_mode": "live",
            "research_enabled": False,
            "ai_data_policy": "uploaded_sources",
            "formats": ["csv", "xlsx", "txt", "text_pdf"],
            "estimated_budget_usd": str(settings.run_budget_usd),
        }

    @app.post("/api/businesses", status_code=201)
    def create_business(req: BusinessCreate):
        return store.create(
            "business", {**req.model_dump(), "currency": "USD", "seeded_demo": False}
        )

    @app.get("/api/businesses")
    def businesses():
        return store.list("business")

    @app.get("/api/businesses/{id}")
    def business(id: str):
        return services.business(id)

    @app.post("/api/demo/seed")
    def demo():
        return seed_demo(services)

    @app.post("/api/businesses/{id}/sources", status_code=201)
    async def upload(id: str, file: UploadFile = File(...), sheet: str | None = Form(default=None)):
        content = await file.read(settings.max_upload_bytes + 1)
        return services.source_view(services.upload(id, file.filename or "", content, sheet))

    @app.get("/api/businesses/{id}/sources")
    def sources(id: str):
        services.business(id)
        return [services.source_view(s) for s in store.list("source", id)]

    @app.get("/api/businesses/{id}/sources/{source_id}")
    def source_content(id: str, source_id: str):
        source = services.source(source_id, id)
        return {**services.source_view(source), "chunks": source["data"]["chunks"]}

    @app.get("/api/businesses/{id}/baseline")
    def baseline(id: str):
        services.business(id)
        return services.baseline(id)

    @app.get("/api/businesses/{id}/facts")
    def facts(id: str):
        services.business(id)
        return store.list("fact", id)

    @app.post("/api/runs", status_code=202)
    async def run(req: RunRequest):
        record = executor.create_run(req)
        executor.schedule(record["id"])
        return record

    @app.get("/api/runs/{id}")
    def get_run(id: str):
        record = store.get(id, "run")
        return {
            **record,
            "tasks": store.list("task", run_id=id),
            "questions": store.list("question", run_id=id),
            "usage": store.list("usage", run_id=id),
        }

    @app.get("/api/runs/{id}/events")
    def events(id: str):
        store.get(id, "run")
        return store.list("event", run_id=id)

    @app.get("/api/runs/{id}/workspace")
    def workspace(id: str, query: str = "", offset: int = 0, limit: int = 10):
        run = store.get(id, "run")
        return query_entries(services, run["business_id"], id, query, offset, limit)

    @app.post("/api/runs/{id}/answers", status_code=202)
    async def answer(id: str, req: Answers):
        record = services.answer_questions(store.get(id, "run"), req.answers)
        if record["data"]["status"] == "created":
            executor.schedule(id)
        return record

    @app.post("/api/runs/{id}/cancel")
    async def cancel(id: str):
        record = store.get(id, "run")
        if record["data"]["status"] not in [
            "created",
            "planning",
            "running",
            "synthesizing",
            "waiting_for_input",
        ]:
            raise DomainError("invalid_state", "This run cannot be canceled.", 409)
        record = store.patch(record, {"status": "canceled"})
        task = executor.jobs.get(id)
        if task and not task.done():
            task.cancel()
        return record

    @app.post("/api/runs/{id}/retry", status_code=202)
    async def retry(id: str):
        return executor.schedule(id)

    @app.get("/api/calculations/{id}")
    def calculation(id: str):
        return store.get(id, "calculation")

    @app.post("/api/decisions", status_code=201)
    def save(req: DecisionCreate):
        return services.save_decision(req)

    @app.get("/api/decisions")
    def decisions(business_id: str):
        services.business(business_id)
        return store.list("decision", business_id)

    @app.get("/api/decisions/{id}")
    def decision(id: str):
        return store.get(id, "decision")

    @app.patch("/api/decisions/{id}")
    def status(id: str, req: StatusUpdate):
        return store.patch(store.get(id, "decision"), req.model_dump())

    @app.post("/api/decisions/{id}/outcomes", status_code=201)
    def actual(id: str, req: OutcomeInput):
        return services.record_outcome(id, req)

    @app.get("/api/decisions/{id}/outcomes")
    def outcomes(id: str):
        record = store.get(id, "decision")
        return [
            o
            for o in store.list("outcome", record["business_id"])
            if o["data"]["decision_id"] == id
        ]

    frontend = Path(__file__).resolve().parents[2] / "frontend"
    if (frontend / "index.html").is_file():
        app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="assets")

        @app.get("/", include_in_schema=False)
        def owner_interface():
            return FileResponse(frontend / "index.html", headers={"Cache-Control": "no-store"})

    return app
