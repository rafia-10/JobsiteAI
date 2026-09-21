"""Agent tests: deterministic fallback answers must cite real seed data, and the
LLM tool-calling loop must correctly record and use tool results (mocked LLM)."""
from datetime import date

from app import agent


def test_fallback_priority_answer(db_session):
    res = agent.run_fallback(db_session, "what's my priority today and tomorrow", date.today())
    assert "overdue" in res["answer"].lower()
    assert res["source"] == "fallback"
    assert res["tool_calls"][0]["name"] == "get_priority_tasks"
    # Groundedness: mentions a real task from the seed
    assert "Sewer drainage" in res["answer"] or "Framing" in res["answer"] or "roof" in res["answer"].lower()


def test_fallback_defects_answer(db_session):
    res = agent.run_fallback(db_session, "what defects are still open", date.today())
    assert res["source"] == "fallback"
    assert "drainage fall out of spec" in res["answer"].lower()


def test_fallback_crews_answer(db_session):
    res = agent.run_fallback(db_session, "who is on site this week", date.today())
    assert "Priya N." in res["answer"] and "Marco V." in res["answer"]


def test_fallback_unknown_question(db_session):
    res = agent.run_fallback(db_session, "what is the weather on mars", date.today())
    # Unknown questions still give the priority picture plus a scope hint.
    assert "I can also cover defects" in res["answer"]


# ------------------------------------------------------------------ LLM path ----

class _FakeMsg:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class _FakeTC:
    def __init__(self, tc_id, name, arguments):
        self.id = tc_id

        class _Fn:
            def __init__(self, name, arguments):
                self.name = name
                self.arguments = arguments

        self.function = _Fn(name, arguments)


class _FakeResp:
    def __init__(self, message):
        self.choices = [type("C", (), {"message": message})()]


class _FakeCompletions:
    def __init__(self, responses):
        self._responses = list(responses)

    def create(self, **kwargs):
        assert kwargs.get("tools"), "tools must be passed to the model"
        return self._responses.pop(0)


def _patch_client(monkeypatch, responses):
    created = {}

    class _FakeOpenAI:
        def __init__(self, **kwargs):
            created.update(kwargs)
            self.chat = type("Chat", (), {})()
            self.chat.completions = _FakeCompletions(responses)

    monkeypatch.setattr(agent, "OpenAI", _FakeOpenAI)
    monkeypatch.setattr(agent.settings, "openai_api_key", "test-key")
    return created


def test_llm_tool_loop_grounds_answer(monkeypatch, db_session):
    """Model asks for priority tasks, then answers — the tool result must be real DB data."""
    resp1 = _FakeResp(_FakeMsg(tool_calls=[
        _FakeTC("call_1", "get_priority_tasks", "{}"),
    ]))
    resp2 = _FakeResp(_FakeMsg(content="Two overdue jobs: garage frame set-out and the west roof."))
    _patch_client(monkeypatch, [resp1, resp2])

    res = agent.run_agent(db_session, "what's my priority today and tomorrow")
    assert res["source"] == "llm+tools"
    assert res["model"] == agent.settings.llm_model
    assert res["answer"].startswith("Two overdue jobs")
    assert res["tool_calls"][0]["name"] == "get_priority_tasks"
    # the recorded tool result is the real snapshot (not a JSON string — regression test)
    snap = res["tool_calls"][0]["result"]
    assert snap["project_name"] == "14 Kowhai Crescent — New Build"
    assert snap["overdue"]
    # data_snapshot normalized by snapshot key
    assert res["data_snapshot"]["priority"]["today"] is not None


def test_llm_bad_tool_error_returned_to_model(monkeypatch, db_session):
    resp1 = _FakeResp(_FakeMsg(tool_calls=[
        _FakeTC("call_1", "get_tasks", "{\"status\": \"bogus\"}"),
    ]))
    resp2 = _FakeResp(_FakeMsg(content="No tasks found for that status."))
    _patch_client(monkeypatch, [resp1, resp2])

    res = agent.run_agent(db_session, "show me bogus tasks")
    assert res["source"] == "llm+tools"
    assert res["tool_calls"][0]["result"] == {"tasks": []}


def test_llm_failure_falls_back(monkeypatch, db_session):
    class _Boom:
        def __init__(self, **kwargs):
            raise RuntimeError("api down")

    monkeypatch.setattr(agent, "OpenAI", _Boom)
    monkeypatch.setattr(agent.settings, "openai_api_key", "test-key")
    res = agent.run_agent(db_session, "what's my priority today and tomorrow")
    assert res["source"] == "fallback (llm error)"
    assert "overdue" in res["answer"].lower()
