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


# -------------------------------------------------------------- streaming ----

class _Delta:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class _StreamChunk:
    def __init__(self, delta):
        self.choices = [type("C", (), {"delta": delta})()]


class _StreamTC:
    """One incremental tool_call delta (OpenAI chunk shape)."""

    def __init__(self, index, tc_id=None, name=None, arguments=None):
        self.index = index
        self.id = tc_id
        if name is not None or arguments is not None:
            self.function = type("F", (), {"name": name, "arguments": arguments})()
        else:
            self.function = None


class _FakeStreamCompletions:
    def __init__(self, streams, seen):
        self._streams = list(streams)
        self._seen = seen

    def create(self, **kwargs):
        assert kwargs.get("stream") is True, "streaming must request stream=True"
        assert kwargs.get("tools"), "tools must be passed to the model"
        self._seen.append(kwargs)
        return iter(self._streams.pop(0))


def _patch_stream_client(monkeypatch, streams):
    seen: list[dict] = []

    class _FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = type("Chat", (), {})()
            self.chat.completions = _FakeStreamCompletions(streams, seen)

    monkeypatch.setattr(agent, "OpenAI", _FakeOpenAI)
    monkeypatch.setattr(agent.settings, "openai_api_key", "test-key")
    return seen


def test_stream_loop_streams_tool_then_answer(monkeypatch, db_session):
    stream1 = [
        _StreamChunk(_Delta(tool_calls=[_StreamTC(0, tc_id="call_1", name="get_priority_tasks", arguments="{}")])),
    ]
    stream2 = [
        _StreamChunk(_Delta(content="Two overdue jobs today.")),
        _StreamChunk(_Delta(content=" Call the roofer first.")),
    ]
    _patch_stream_client(monkeypatch, [stream1, stream2])

    events = list(agent.stream_agent_events(db_session, "what's my priority today and tomorrow"))
    types = [e["type"] for e in events]

    assert "tool" in types and "tool_result" in types
    assert types.count("delta") == 2
    assert {"type": "sentence", "text": "Two overdue jobs today."} in events
    done = events[-1]
    assert done["type"] == "done"
    assert done["source"] == "llm+tools"
    assert done["answer"] == "Two overdue jobs today. Call the roofer first."
    # the recorded tool result is real DB data, not model invention
    assert done["tool_calls"][0]["name"] == "get_priority_tasks"
    assert done["tool_calls"][0]["result"]["project_name"] == "14 Kowhai Crescent — New Build"
    # conversation history was sent to the model
    # (seen[0]["messages"] includes system + user; history tested separately)


def test_stream_history_is_trimmed_and_forwarded(monkeypatch, db_session):
    stream = [_StreamChunk(_Delta(content="Sure thing."))]
    seen = _patch_stream_client(monkeypatch, [stream])

    history = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"turn {i}"}
               for i in range(20)]
    list(agent.stream_agent_events(db_session, "and tomorrow?", history=history))

    messages = seen[0]["messages"]
    # system + trimmed history (12) + current question
    assert len(messages) == 14
    assert messages[0]["role"] == "system"
    assert messages[1]["content"] == "turn 8"  # oldest surviving turn
    assert messages[-1] == {"role": "user", "content": "and tomorrow?"}


def test_stream_failure_falls_back_gracefully(monkeypatch, db_session):
    class _Boom:
        def __init__(self, **kwargs):
            raise RuntimeError("api down")

    monkeypatch.setattr(agent, "OpenAI", _Boom)
    monkeypatch.setattr(agent.settings, "openai_api_key", "test-key")

    events = list(agent.stream_agent_events(db_session, "what's my priority today"))
    done = events[-1]
    assert done["type"] == "done"
    assert done["source"] == "fallback (llm error)"
    assert "overdue" in done["answer"].lower()
    assert any(e["type"] == "sentence" for e in events)


# ----------------------------------------------------------------- memory ----

def test_fallback_resolves_followup_from_history(db_session):
    today = date.today()
    # Topic established in a prior turn; follow-up alone carries no keyword.
    history = [{"role": "user", "content": "what defects are still open"}]
    res = agent.run_fallback(db_session, "and which task are they on?", today, history=history)
    assert res["source"] == "fallback"
    assert "drainage fall out of spec" in res["answer"].lower()


def test_run_agent_forwards_history_to_model(monkeypatch, db_session):
    resp1 = _FakeResp(_FakeMsg(tool_calls=[_FakeTC("call_1", "get_trades_workload", "{}")]))
    resp2 = _FakeResp(_FakeMsg(content="Hemi's roofing crew."))
    seen_kwargs: list[dict] = []

    class _FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = type("Chat", (), {})()
            self.chat.completions = _FakeCompletions([resp1, resp2])
            self.chat.completions.seen = seen_kwargs

        # capture messages via wrapper below
    original_create = _FakeCompletions.create

    def _spy_create(self, **kwargs):
        # snapshot: run_agent mutates its messages list in place between rounds
        seen_kwargs.append({**kwargs, "messages": list(kwargs["messages"])})
        return original_create(self, **kwargs)

    monkeypatch.setattr(_FakeCompletions, "create", _spy_create)
    monkeypatch.setattr(agent, "OpenAI", _FakeOpenAI)
    monkeypatch.setattr(agent.settings, "openai_api_key", "test-key")

    res = agent.run_agent(db_session, "who is on that crew?",
                          history=[{"role": "user", "content": "who's roofing?"}])
    assert res["source"] == "llm+tools"
    messages = seen_kwargs[0]["messages"]
    assert {"role": "user", "content": "who's roofing?"} in messages
    assert messages[-1] == {"role": "user", "content": "who is on that crew?"}


def test_stream_single_sentence_emits_one_tts_event(monkeypatch, db_session):
    """Regression: a one-sentence answer (no trailing whitespace) must flush its
    tail exactly once — never zero sentence events (no TTS) and never twice."""
    stream = [_StreamChunk(_Delta(content="Both are still open."))]
    _patch_stream_client(monkeypatch, [stream])

    events = list(agent.stream_agent_events(db_session, "any defects left?"))
    sentences = [e["text"] for e in events if e["type"] == "sentence"]
    assert sentences == ["Both are still open."]
    done = events[-1]
    assert done["type"] == "done" and done["answer"] == "Both are still open."


def test_stream_multi_sentence_no_duplicate_tts(monkeypatch, db_session):
    """Sentences completed during streaming must not be re-emitted by the flush."""
    stream = [
        _StreamChunk(_Delta(content="First sentence.")),
        _StreamChunk(_Delta(content=" Second one. ")),
    ]
    _patch_stream_client(monkeypatch, [stream])

    events = list(agent.stream_agent_events(db_session, "tell me things"))
    sentences = [e["text"] for e in events if e["type"] == "sentence"]
    assert sentences == ["First sentence.", "Second one."]
