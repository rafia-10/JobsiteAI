"""PreCode backend entrypoint.

Get running:
    docker compose up --build
    (schema + demo data are created and seeded automatically on first start)

Hello world:   curl http://localhost:8081/api/health
Full API docs: http://localhost:8081/docs
"""
import logging
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import agent, queries
from .config import settings
from .db import get_db
from .models import Defect, Project, Supervisor, Task, Trade, TradeAssignment
from .schemas import (
    AgentDebug,
    AgentResponse,
    DefectFlatOut,
    PriorityResponse,
    ProjectOut,
    SeedResult,
    SupervisorOut,
    TaskFlatOut,
    TradeAssignmentOut,
    TradeOut,
)
from .seed import seed
from .voice import router as voice_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("precode")

# ------------------------------------------------------------------ app ----


@asynccontextmanager
async def lifespan(app: FastAPI):
    from .db import engine
    from .models import Base

    Base.metadata.create_all(engine)
    seed()  # no-op if already seeded
    if not settings.openai_api_key:
        logger.warning("OPENAI_API_KEY not set — agent will use deterministic fallback answers.")
    yield


app = FastAPI(
    title="PreCode Assistant API",
    description="Construction management platform with a hands-free voice assistant.",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # dev only
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(voice_router)


# ------------------------------------------------------------------ health ----

@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    """Hello-world endpoint: verifies API + DB round-trip."""
    db.execute(select(1))
    return {
        "status": "ok",
        "service": "precode-backend",
        "database": "connected",
        "llm": settings.llm_model if settings.openai_api_key else "fallback (no API key)",
    }


@app.post("/api/seed", response_model=SeedResult)
def reseed(drop: bool = False):
    seed(drop=drop)
    from .db import SessionLocal

    with SessionLocal() as db:
        return SeedResult(
            seeded=True,
            message="database seeded",
            projects=db.query(Project).count(),
            trades=db.query(Trade).count(),
            tasks=db.query(Task).count(),
            defects=db.query(Defect).count(),
        )


@app.get("/api/supervisors", response_model=list[SupervisorOut])
def list_supervisors(db: Session = Depends(get_db)):
    return db.execute(select(Supervisor)).scalars().all()


# -------------------------------------------------------------- core data ----

@app.get("/api/projects", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)):
    return db.execute(select(Project)).scalars().all()


@app.get("/api/trades", response_model=list[TradeOut])
def list_trades(db: Session = Depends(get_db)):
    return db.execute(select(Trade)).scalars().all()


@app.get("/api/trade-assignments", response_model=list[TradeAssignmentOut])
def list_assignments(db: Session = Depends(get_db)):
    return db.execute(select(TradeAssignment)).scalars().all()


@app.get("/api/tasks", response_model=list[TaskFlatOut])
def list_tasks(
    status: str | None = None,
    trade: str | None = None,
    on_date: date | None = None,
    db: Session = Depends(get_db),
):
    return queries.get_tasks(db, status=status, trade=trade, on_date=on_date)


@app.get("/api/defects", response_model=list[DefectFlatOut])
def list_defects(status: str | None = None, db: Session = Depends(get_db)):
    return queries.get_defects(db, status=status)


@app.get("/api/priority", response_model=PriorityResponse)
def priority(db: Session = Depends(get_db)):
    today = date.today()
    data = queries.get_priority_tasks(db, today)
    summary = agent.run_fallback(db, "what's my priority today and tomorrow", today)["answer"]
    return {**data, "generated_at": datetime.now(timezone.utc), "summary": summary}


# ------------------------------------------------------------------ agent ----


class AskBody(BaseModel):
    question: str


@app.post("/api/agent/ask", response_model=AgentResponse)
def agent_ask(payload: AskBody, db: Session = Depends(get_db)):
    question = payload.question.strip()
    if not question:
        raise HTTPException(422, "question must not be empty")
    result = agent.run_agent(db, question)
    return AgentResponse(
        answer=result["answer"],
        source=result["source"],
        model=result.get("model"),
        tools_used=[tc["name"] for tc in result.get("tool_calls", [])],
        citations=_citations(result.get("data_snapshot", {})),
    )


@app.post("/api/agent/debug", response_model=AgentDebug)
def agent_debug(payload: AskBody, db: Session = Depends(get_db)):
    """Same as /ask but returns raw tool calls + data — proves answers come from real data."""
    question = payload.question.strip()
    if not question:
        raise HTTPException(422, "question must not be empty")
    result = agent.run_agent(db, question)
    return AgentDebug(
        tool_calls=[
            {
                "name": tc["name"],
                "arguments": tc.get("arguments", {}),
                "result_preview": agent._preview(tc.get("result", {}), 1200),
            }
            for tc in result.get("tool_calls", [])
        ],
        data_snapshot=result.get("data_snapshot", {}),
    )


def _citations(snapshot: dict) -> list[dict]:
    """Flatten a data snapshot into citation entries for the UI."""
    out: dict[str, dict] = {}
    prio = snapshot.get("priority") or {}
    for key in ("today", "tomorrow", "overdue"):
        for t in prio.get(key, []):
            out[f"task-{t['task_id']}"] = {"type": "task", "id": t["task_id"], "title": t["title"]}
    for t in (snapshot.get("tasks") or {}).get("tasks", []):
        out[f"task-{t['task_id']}"] = {"type": "task", "id": t["task_id"], "title": t["title"]}
    for d in (snapshot.get("defects") or {}).get("defects", []):
        out[f"defect-{d['defect_id']}"] = {"type": "defect", "id": d["defect_id"], "title": d["title"]}
    for c in (snapshot.get("crews") or {}).get("crews", []):
        out[f"crew-{c['trade']}"] = {"type": "trade_assignment", "id": 0, "title": c["trade"]}
    return list(out.values())
