"""Run-local, evidence-backed working records in the existing SQLite document store."""

import hashlib
import json

from app.config import DomainError


def save_entry(services, scope, entry):
    services.store.get(scope.run_id, "run", scope.business_id)
    for evidence in entry.evidence:
        source = services.source(evidence.source_id, scope.business_id, for_ai=True)
        if not any(
            c["location"] == evidence.location and evidence.quote in c["text"]
            for c in source["data"]["chunks"]
        ):
            raise DomainError(
                "invalid_evidence", "Workspace evidence must quote its exact source location."
            )
    data = {"type": "workspace_entry", **entry.model_dump()}
    if len(json.dumps(data)) > 14000:
        raise DomainError("entry_too_large", "Split this workspace entry into smaller records.")
    digest = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    return services.store.create(
        "artifact", data, scope.business_id, scope.run_id, f"{scope.run_id}:workspace:{digest}"
    )


def query_entries(services, business_id, run_id, query="", offset=0, limit=10):
    services.store.get(run_id, "run", business_id)
    if offset < 0 or not 1 <= limit <= 10 or len(query) > 200:
        raise DomainError(
            "invalid_query", "Use offset >= 0, limit 1-10, and query <= 200 characters."
        )
    terms = query.casefold().split()
    records = [
        r
        for r in services.store.list("artifact", business_id, run_id)
        if r["data"].get("type") == "workspace_entry"
        and all(term in json.dumps(r["data"], ensure_ascii=False).casefold() for term in terms)
    ]
    # Stay below the runner's tool-output limit even for long quotations/notes.
    page = []
    for record in records[offset : offset + limit]:
        if len(json.dumps(page + [record])) > 16000:
            break
        page.append(record)
    next_offset = offset + len(page)
    return {
        "entries": page,
        "total": len(records),
        "next_offset": next_offset if next_offset < len(records) else None,
    }
