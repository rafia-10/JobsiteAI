"""API endpoint tests: routes work end-to-end against seeded SQLite."""
from app.main import _citations


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["database"] == "connected"


def test_priority_endpoint(client):
    r = client.get("/api/priority")
    assert r.status_code == 200
    body = r.json()
    assert body["project_name"] == "14 Kowhai Crescent — New Build"
    assert body["summary"]
    assert isinstance(body["generated_at"], str)


def test_list_tasks_filters(client):
    r = client.get("/api/tasks", params={"trade": "roofer"})
    assert r.status_code == 200
    tasks = r.json()
    assert tasks and all(t["trade"] == "Roofer" for t in tasks)

    r = client.get("/api/tasks", params={"status": "completed"})
    assert r.status_code == 200
    assert all(t["status"] == "completed" for t in r.json())


def test_list_defects(client):
    r = client.get("/api/defects", params={"status": "open"})
    assert r.status_code == 200
    defects = r.json()
    assert defects and all(d["status"] == "open" for d in defects)


def test_agent_ask_fallback_with_citations(client):
    r = client.post("/api/agent/ask", json={"question": "what's my priority today and tomorrow"})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"]
    assert body["source"] == "fallback"
    assert body["tools_used"] == ["get_priority_tasks"]
    # citations must reference real seed tasks
    titles = {c["title"] for c in body["citations"]}
    assert "Framing — level 2 east wall" in titles or "Sewer drainage connection" in titles


def test_agent_debug_shows_tool_calls(client):
    r = client.post("/api/agent/debug", json={"question": "what defects are still open"})
    assert r.status_code == 200
    body = r.json()
    assert body["tool_calls"][0]["name"] == "get_defects"
    assert "defects" in body["data_snapshot"]


def test_agent_ask_validates_body(client):
    r = client.post("/api/agent/ask", json={"question": "   "})
    assert r.status_code == 422


def test_citations_from_generic_task_list():
    snap = {"tasks": {"tasks": [{"task_id": 9, "title": "T9"}]}}
    out = _citations(snap)
    assert {"type": "task", "id": 9, "title": "T9"} in out


def test_agent_stream_sse_events(client):
    with client.stream("POST", "/api/agent/stream", json={"question": "what defects are still open"}) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        body = "".join(r.iter_text())

    assert "event: sentence" in body or "event: delta" in body
    assert "event: done" in body
    assert "get_defects" in body  # tool activity event present


def test_agent_stream_accepts_history(client):
    with client.stream("POST", "/api/agent/stream", json={
        "question": "and which tasks are they on?",
        "history": [{"role": "user", "content": "what defects are still open"},
                     {"role": "assistant", "content": "Two active defects."}],
    }) as r:
        assert r.status_code == 200
        body = "".join(r.iter_text())
    assert "event: done" in body


def test_agent_ask_suggestions(client):
    r = client.post("/api/agent/ask", json={"question": "what's my priority today and tomorrow"})
    assert r.status_code == 200
    suggestions = r.json()["suggestions"]
    assert suggestions and all(isinstance(s, str) for s in suggestions)
