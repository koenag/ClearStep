from app.contracts import Answer, FactCandidate, Question
from test_tools import make_scope


def test_owner_interface_served_with_existing_api(backend):
    _, client, _ = backend
    page = client.get("/")
    assert page.status_code == 200
    assert "Choose a folder" in page.text
    assert client.get("/assets/app.js").status_code == 200
    assert client.get("/assets/logic.js").status_code == 200
    assert client.get("/assets/style.css").status_code == 200
    assert client.get("/api/health").json()["status"] == "ok"


def test_correcting_candidate_resolves_duplicate_questions_without_reproposing(seeded):
    services, business = seeded
    run, task, _ = make_scope(services, business, "data_parser")
    source = next(
        s
        for s in services.store.list("source", business["id"])
        if s["data"]["filename"] == "alternative_supplier_quote_email.txt"
    )
    candidate = services.submit_candidate(
        business["id"],
        FactCandidate(
            decision_type="supplier_switch",
            field="new_unit_cost",
            value="10",
            unit="USD/unit",
            source_id=source["id"],
            location=source["data"]["chunks"][0]["location"],
            evidence="(equivalent to $10.00 per lb).",
        ),
    )
    q = services.new_question(
        run,
        Question(field="new_unit_cost", reason="Check price", candidate_id=candidate["id"]),
        task["id"],
    )
    services.new_question(
        run,
        Question(field="new_unit_cost", reason="Duplicate", candidate_id=candidate["id"]),
        "other_task",
    )
    services.new_question(run, Question(field="new_unit_cost", reason="Missing price"), task["id"])
    run = services.store.patch(run, {"status": "waiting_for_input"})
    result = services.answer_questions(
        run, [Answer(question_id=q["id"], value=11, unit="USD/unit")]
    )
    assert result["data"]["status"] == "created"
    assert services.store.get(candidate["id"])["data"]["status"] == "rejected"
    assert all(
        q["data"]["status"] == "answered" for q in services.store.list("question", run_id=run["id"])
    )
    facts = services.eligible_facts(business["id"], "supplier_switch", run["id"])
    assert not any(f["data"]["status"] == "candidate" for f in facts)
    assert (
        next(
            f
            for f in facts
            if f["data"]["field"] == "new_unit_cost" and f["data"]["status"] == "accepted"
        )["data"]["value"]
        == "11"
    )
