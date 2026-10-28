"""Small JSON document repository with optimistic writes and scoped lookups.

Typed contracts live in contracts.py. Immutable facts/calculations carry their own
versions; mutable workflow records use revision checks to prevent lost updates.
"""

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4

from sqlalchemy import JSON, Integer, String, UniqueConstraint, create_engine, event, select, update
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.config import DomainError

KINDS = {
    "business",
    "source",
    "fact",
    "run",
    "task",
    "artifact",
    "question",
    "calculation",
    "decision",
    "outcome",
    "event",
    "usage",
    "tool_receipt",
}


class Base(DeclarativeBase):
    pass


class Record(Base):
    __tablename__ = "records"
    __table_args__ = (UniqueConstraint("idempotency_key"),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    kind: Mapped[str] = mapped_column(String, index=True)
    business_id: Mapped[str | None] = mapped_column(String, index=True)
    run_id: Mapped[str | None] = mapped_column(String, index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(String)
    idempotency_key: Mapped[str | None] = mapped_column(String)


class Store:
    def __init__(self, settings):
        self._lock = RLock()
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        url = settings.database_url or f"sqlite:///{settings.data_dir / 'business.db'}"
        if not url.startswith("sqlite:"):
            raise ValueError("This local MVP supports SQLite only.")
        self.engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 10})
        if url in ("sqlite://", "sqlite:///:memory:"):
            from sqlalchemy.pool import StaticPool

            self.engine.dispose()
            self.engine = create_engine(
                url, connect_args={"check_same_thread": False}, poolclass=StaticPool
            )

        @event.listens_for(self.engine, "connect")
        def setup(connection, record):
            connection.execute("PRAGMA busy_timeout=10000")
            connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    @staticmethod
    def view(row):
        return dict(
            id=row.id,
            kind=row.kind,
            business_id=row.business_id,
            run_id=row.run_id,
            created_at=row.created_at,
            revision=row.revision,
            data=row.payload,
        )

    @contextmanager
    def transaction(self):
        # SQLite's check_same_thread=False is not a synchronization primitive.
        # In-memory tests share one physical connection; protect it, and keep
        # all local repository transactions short and serialized in production.
        with self._lock, self.sessions.begin() as session:
            yield session

    def create(self, kind, data, business_id=None, run_id=None, key=None, session=None):
        if kind not in KINDS:
            raise ValueError("Unknown record kind.")
        # Disallow NaN and serialize Decimal only when callers have explicitly converted it.
        json.dumps(data, allow_nan=False)
        if session is None:
            with self.transaction() as db:
                return self.create(kind, data, business_id, run_id, key, db)
        if key:
            existing = session.scalar(select(Record).where(Record.idempotency_key == key))
            if existing:
                return self.view(existing)
        row = Record(
            id=f"{kind}_{uuid4().hex}",
            kind=kind,
            payload=data,
            business_id=business_id,
            run_id=run_id,
            revision=1,
            created_at=datetime.now(timezone.utc).isoformat(),
            idempotency_key=key,
        )
        session.add(row)
        session.flush()
        return self.view(row)

    def get(self, id, kind=None, business_id=None, run_id=None, session=None):
        if session is None:
            with self._lock, self.sessions() as db:
                return self.get(id, kind, business_id, run_id, db)
        row = session.get(Record, id)
        if (
            row is None
            or (kind and row.kind != kind)
            or (business_id and row.business_id != business_id)
            or (run_id and row.run_id != run_id)
        ):
            raise DomainError("not_found", "Record not found in this scope.", 404)
        return self.view(row)

    def list(self, kind, business_id=None, run_id=None, session=None):
        if session is None:
            with self._lock, self.sessions() as db:
                return self.list(kind, business_id, run_id, db)
        query = select(Record).where(Record.kind == kind)
        if business_id:
            query = query.where(Record.business_id == business_id)
        if run_id:
            query = query.where(Record.run_id == run_id)
        return [
            self.view(r)
            for r in session.scalars(query.order_by(Record.created_at, Record.id)).all()
        ]

    def patch(self, record, changes, session=None):
        if session is None:
            with self.transaction() as db:
                return self.patch(record, changes, db)
        data = {**record["data"], **changes}
        json.dumps(data, allow_nan=False)
        result = session.execute(
            update(Record)
            .where(Record.id == record["id"], Record.revision == record["revision"])
            .values(payload=data, revision=record["revision"] + 1)
        )
        if result.rowcount != 1:
            raise DomainError("revision_conflict", "Record changed; reload and retry.", 409)
        return {**record, "data": data, "revision": record["revision"] + 1}

    def close(self):
        with self._lock:
            self.engine.dispose()
