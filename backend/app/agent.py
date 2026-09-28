"""The PreCode assistant.

Design: an LLM (any OpenAI-compatible API) with *tool calling*. The model can
only see project data through the deterministic functions in `queries.py`, so
answers are grounded in live data — the model plans and phrases, the database
answers. Every tool call is recorded for audit/debug.

If no API key is configured, a deterministic fallback answers the core
questions (priority today/tomorrow, defects, trade workload, project status)
directly from the same query layer, so the demo works offline.
"""
import json
import logging
import re
from collections.abc import Iterator
from datetime import date

from openai import OpenAI
from sqlalchemy.orm import Session

from . import queries
from .config import settings

logger = logging.getLogger("precode.agent")

MAX_HISTORY_MESSAGES = 12  # keep memory bounded; recent turns matter most


def _trim_history(history: list[dict]) -> list[dict]:
    """Keep the most recent turns, always keeping an assistant before each user
    turn so tool-result messages are never dangling."""
    h = [m for m in history if m.get("role") in ("user", "assistant") and (m.get("content") or "").strip()]
    return h[-MAX_HISTORY_MESSAGES:]

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_priority_tasks",
            "description": (
                "Get the supervisor's priority schedule: tasks due today, tasks due tomorrow, "
                "and all overdue tasks for the active project, each with trade, status, priority, "
                "due date and open defect count. Use this for questions like "
                "'what's my priority today and tomorrow'."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_project_status",
            "description": "Get overall status of the active project: timeline, task counts by status, open defects.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_defects",
            "description": "List defects. Optionally filter by status: open, in_progress, resolved, closed.",
            "parameters": {
                "type": "object",
                "properties": {"status": {"type": "string", "enum": ["open", "in_progress", "resolved", "closed"]}},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_trades_workload",
            "description": "Get trades/crews currently allocated to the active project, who leads each crew, and their active tasks.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_tasks",
            "description": "List tasks with optional filters: status (pending/in_progress/blocked/completed), trade name (e.g. 'roofer'), or a specific date (YYYY-MM-DD).",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string"},
                    "trade": {"type": "string"},
                    "on_date": {"type": "string", "description": "ISO date, e.g. 2026-09-15"},
                },
                "required": [],
            },
        },
    },
]

SYSTEM_PROMPT = (
    "You are PreCode Assistant, a concise voice assistant for a construction site supervisor "
    "who may be driving. Answer ONLY from the tool results provided — never invent tasks, dates, "
    "names or numbers. If the tools don't contain the answer, say what's missing. "
    "Keep answers under 120 words, spoken-style, no markdown, no bullet symbols "
    "(use plain sentences). Lead with the most important items: overdue first, then critical, "
    "then the rest. Mention trade names and crew leads when relevant."
)


def _client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key, base_url=settings.llm_base_url)


def _llm_kwargs(extra: dict | None = None) -> dict:
    """Per-request options tuned for the configured provider.

    Groq's gpt-oss models are reasoning models: without `reasoning_effort: low`
    they can spend seconds thinking before the first spoken word — wrong trade
    for a voice assistant. The kwarg is ignored (removed) for other providers.
    """
    if "groq.com" in (settings.llm_base_url or ""):
        return {**extra, "reasoning_effort": "low"} if extra else {"reasoning_effort": "low"}
    return dict(extra) if extra else {}


def _execute_tool(db: Session, today: date, name: str, args: dict) -> dict:
    if name == "get_priority_tasks":
        return queries.get_priority_tasks(db, today)
    if name == "get_project_status":
        return queries.get_project_status(db, today)
    if name == "get_defects":
        return {"defects": queries.get_defects(db, status=args.get("status"))}
    if name == "get_trades_workload":
        return {"crews": queries.get_trades_workload(db, today)}
    if name == "get_tasks":
        on_date = date.fromisoformat(args["on_date"]) if args.get("on_date") else None
        return {"tasks": queries.get_tasks(db, status=args.get("status"), trade=args.get("trade"), on_date=on_date)}
    raise ValueError(f"Unknown tool: {name}")


def _preview(payload: dict, limit: int = 600) -> str:
    text = json.dumps(payload, default=str)
    return text if len(text) <= limit else text[:limit] + "…"


def _base_messages(history: list[dict] | None, question: str, today: date) -> list[dict]:
    msgs: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT + f" Today's date is {today.isoformat()}."}
    ]
    msgs.extend(_trim_history(history or []))
    msgs.append({"role": "user", "content": question})
    return msgs


def run_agent(db: Session, question: str, today: date | None = None,
              history: list[dict] | None = None) -> dict:
    """Answer a supervisor question.

    `history` is prior conversation turns ([{role, content}, ...]) so the
    assistant resolves follow-ups like "and who is on that crew?".
    Returns {answer, source, model, tool_calls, data_snapshot}.
    """
    today = today or date.today()

    if not settings.openai_api_key:
        return run_fallback(db, question, today)

    tool_calls_made: list[dict] = []
    try:
        client = _client()
        messages = _base_messages(history, question, today)

        for _ in range(4):  # bounded tool-call loop
            resp = client.chat.completions.create(
                model=settings.llm_model,
                messages=messages,
                tools=TOOLS,
                temperature=0.2,
                **_llm_kwargs(),
            )
            msg = resp.choices[0].message
            if not msg.tool_calls:
                return {
                    "answer": msg.content or "I couldn't produce an answer.",
                    "source": "llm+tools",
                    "model": settings.llm_model,
                    "tool_calls": tool_calls_made,
                    "data_snapshot": {_snapshot_key(tc["name"]): tc["result"] for tc in tool_calls_made},
                }
            messages.append(msg)
            for tc in msg.tool_calls:
                args = json.loads(tc.function.arguments or "{}")
                try:
                    result = _execute_tool(db, today, tc.function.name, args)
                except Exception as exc:  # tool errors go back to the model, not the user
                    logger.exception("tool %s failed", tc.function.name)
                    result = {"error": str(exc)}
                tool_calls_made.append({"name": tc.function.name, "arguments": args, "result": result})
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, default=str),
                })
        return {
            "answer": "I couldn't finish that in the allowed number of steps. Try a more specific question.",
            "source": "llm+tools",
            "model": settings.llm_model,
            "tool_calls": tool_calls_made,
            "data_snapshot": {},
        }
    except Exception as exc:
        logger.exception("LLM agent failed; falling back to deterministic answers")
        fb = run_fallback(db, question, today)
        fb["source"] = "fallback (llm error)"
        fb["error"] = str(exc)
        return fb


# --------------------------------------------------------------- streaming ----

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def split_sentences(buffer: str) -> tuple[list[str], str]:
    """Pop complete sentences (ending .!? + whitespace) off a growing buffer."""
    parts = _SENTENCE_END.split(buffer)
    if len(parts) <= 1:
        return [], buffer
    complete = parts[:-1]
    consumed = len(buffer) - len(parts[-1])
    return complete, buffer[consumed:]


def stream_agent_events(db: Session, question: str, today: date | None = None,
                        history: list[dict] | None = None) -> Iterator[dict]:
    """Yield agent progress as typed events for Server-Sent Events.

    Event shapes:
      {"type": "tool", "name": str}          — model is calling a tool
      {"type": "tool_result", "name": str}   — tool finished (name is out; no data leaks)
      {"type": "delta", "text": str}         — next chunk of spoken answer text
      {"type": "sentence", "text": str}      — a complete spoken sentence (drives TTS)
      {"type": "done", ...run_agent fields}  — final answer + tool_calls + citations data
    On any LLM failure this degrades to the deterministic fallback, still streamed.
    """
    today = today or date.today()

    if not settings.openai_api_key:
        fb = run_fallback(db, question, today)
        tail, _rest = split_sentences(fb["answer"] + " ")
        for s in tail:
            yield {"type": "sentence", "text": s}
        yield {"type": "done", **fb}
        return

    tool_calls_made: list[dict] = []
    buffer = ""   # unconsumed tail, split into sentences as it grows
    full = ""     # every content token across all rounds -> the final answer
    try:
        client = _client()
        messages = _base_messages(history, question, today)

        for _ in range(4):
            stream = client.chat.completions.create(
                model=settings.llm_model,
                messages=messages,
                tools=TOOLS,
                temperature=0.2,
                stream=True,
                **_llm_kwargs(),
            )
            tool_calls: dict[int, dict] = {}
            for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta is None:
                    continue
                if getattr(delta, "tool_calls", None):
                    for tcd in delta.tool_calls:
                        slot = tool_calls.setdefault(tcd.index, {"id": "", "name": "", "arguments": ""})
                        if tcd.id:
                            slot["id"] = tcd.id
                        if tcd.function and tcd.function.name:
                            slot["name"] = tcd.function.name
                        if tcd.function and tcd.function.arguments:
                            slot["arguments"] += tcd.function.arguments
                if delta.content:
                    buffer += delta.content
                    full += delta.content
                    yield {"type": "delta", "text": delta.content}
                    sentences, buffer = split_sentences(buffer)
                    for s in sentences:
                        yield {"type": "sentence", "text": s}

            if not tool_calls:
                break  # content answer finished

            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": s["id"], "type": "function",
                     "function": {"name": s["name"], "arguments": s["arguments"] or "{}"}}
                    for s in tool_calls.values()
                ],
            })
            for slot in tool_calls.values():
                yield {"type": "tool", "name": slot["name"]}
                args = json.loads(slot["arguments"] or "{}")
                try:
                    result = _execute_tool(db, today, slot["name"], args)
                except Exception as exc:
                    logger.exception("tool %s failed", slot["name"])
                    result = {"error": str(exc)}
                tool_calls_made.append({"name": slot["name"], "arguments": args, "result": result})
                messages.append({
                    "role": "tool",
                    "tool_call_id": slot["id"] or f"call_{len(tool_calls_made)}",
                    "content": json.dumps(result, default=str),
                })
                yield {"type": "tool_result", "name": slot["name"]}

        answer = full.strip() or "I couldn't produce an answer."
        # Flush whatever streaming hasn't already emitted: split_sentences
        # removes emitted text from the buffer, so the remaining tail (e.g. a
        # single-sentence answer that never hit ". ", or a closing fragment)
        # is exactly what still needs a sentence event. Never re-emit `answer`.
        leftover = buffer.strip()
        if leftover:
            yield {"type": "sentence", "text": leftover}
        yield {
            "type": "done",
            "answer": answer,
            "source": "llm+tools",
            "model": settings.llm_model,
            "tool_calls": tool_calls_made,
            "data_snapshot": {_snapshot_key(tc["name"]): tc["result"] for tc in tool_calls_made},
        }
    except Exception as exc:
        logger.exception("LLM streaming failed; falling back to deterministic answers")
        fb = run_fallback(db, question, today)
        fb["source"] = "fallback (llm error)"
        fb["error"] = str(exc)
        tail, _rest = split_sentences(fb["answer"] + " ")
        for s in tail:
            yield {"type": "sentence", "text": s}
        yield {"type": "done", **fb}


# ---------------------------------------------------------------- fallback ----

def run_fallback(db: Session, question: str, today: date, history: list[dict] | None = None) -> dict:
    """Deterministic answers with no LLM. Detects intent with simple keyword rules.

    A follow-up question (e.g. "and tomorrow?" with no topic keyword) is resolved
    against the previous user turn so short voice follow-ups still work offline.
    """
    for m in reversed(history or []):
        if m.get("role") == "user" and (m.get("content") or "").strip():
            question = f"{m['content']} {question}"
            break
    q = question.lower()
    snapshot: dict = {}

    def wants(*words: str) -> bool:
        return any(w in q for w in words)

    parts: list[str] = []
    tools_used: list[str] = []

    if wants("defect", "snag", "issue") and not wants("priority"):
        defects = queries.get_defects(db, status="open")
        snapshot["defects"] = {"defects": defects}
        tools_used.append("get_defects")
        active = [d for d in defects if d["status"] in ("open", "in_progress")]
        if active:
            bits = [f"{d['severity']} severity {d['title']} on {d['task_title']} ({d['trade']})" for d in active]
            parts.append(f"You have {len(active)} active defects: " + "; ".join(bits) + ".")
        else:
            parts.append("You have no active defects right now.")

    if wants("trade", "crew", "who is on", "on site"):
        crews = queries.get_trades_workload(db, today)
        snapshot["crews"] = {"crews": crews}
        tools_used.append("get_trades_workload")
        if crews:
            bits = [f"{c['trade']} led by {c['crew_lead']}, crew of {c['crew_size']}, until {c['on_site_until']}" for c in crews]
            parts.append("Crews on site: " + "; ".join(bits) + ".")

    # default / explicit priority question
    matched = bool(parts)
    if not parts or wants("priority", "today", "tomorrow", "schedule", "overdue"):
        data = queries.get_priority_tasks(db, today)
        snapshot["priority"] = data
        tools_used.insert(0, "get_priority_tasks")

        def describe(items):
            return [f"{t['title']} for {t['trade']}"
                    + (f", {t['priority']} priority" if t["priority"] != "medium" else "")
                    + (f", {t['days_overdue']} days overdue" if t["days_overdue"] else "")
                    for t in items]

        if data["overdue"]:
            parts.insert(0, f"First, {len(data['overdue'])} overdue task(s): " + "; ".join(describe(data["overdue"])) + ".")
        if data["today"]:
            parts.append(f"Today: " + "; ".join(describe(data["today"])) + ".")
        else:
            parts.append("Nothing scheduled for today.")
        if data["tomorrow"]:
            parts.append(f"Tomorrow: " + "; ".join(describe(data["tomorrow"])) + ".")
        if data["open_defects"]:
            parts.append(f"You have {data['open_defects']} open defects on {data['project_name']}.")

    answer = " ".join(parts)
    if not matched and not wants("priority", "today", "tomorrow", "schedule", "overdue"):
        answer += " I can also cover defects, trade crews and project status — just ask."
    return {"answer": answer, "source": "fallback", "model": None, "tool_calls": [
        {"name": t, "arguments": {}, "result": snapshot.get(_snapshot_key(t), {})}
        for t in tools_used
    ], "data_snapshot": snapshot}


def _snapshot_key(tool: str) -> str:
    return {"get_priority_tasks": "priority", "get_defects": "defects",
            "get_trades_workload": "crews", "get_project_status": "status", "get_tasks": "tasks"}.get(tool, tool)
