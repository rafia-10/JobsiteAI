"""Deterministic, SQL-backed data functions.

Every function here is the *only* way the agent (or the REST API) touches data.
The LLM never writes SQL and never invents numbers — it calls these tools and
reasons over their JSON output. This keeps answers grounded in live data and
makes every tool result auditable (see /api/agent/debug).

All functions take an explicit `today` so the agent's notion of "today" is
always the server's date, never the model's guess.
"""
from datetime import date, timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from .models import (
    Defect,
    DefectStatus,
    Project,
    ProjectStatus,
    Task,
    TaskStatus,
    Trade,
    TradeAssignment,
)

_PRIORITY_RANK = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
}

# Completions past their due date don't belong on a priority list.
_ACTIVE_STATUSES = [TaskStatus.PENDING, TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED]


def _task_defect_counts(db: Session, task_ids: list[int]) -> dict[int, int]:
    if not task_ids:
        return {}
    rows = (
        db.execute(
            select(Defect.task_id, func.count())
            .where(Defect.task_id.in_(task_ids))
            .where(Defect.status.in_([DefectStatus.OPEN, DefectStatus.IN_PROGRESS]))
            .group_by(Defect.task_id)
        )
        .all()
    )
    return {task_id: count for task_id, count in rows}


def _serialize_task(db: Session, t: Task, *, reason: str | None = None) -> dict:
    defect_count = _task_defect_counts(db, [t.id]).get(t.id, 0)
    days_overdue = max(0, (date.today() - t.due_date).days)
    return {
        "task_id": t.id,
        "title": t.title,
        "trade": t.trade.name,
        "status": t.status.value,
        "priority": t.priority.value,
        "scheduled_date": t.scheduled_date.isoformat(),
        "due_date": t.due_date.isoformat(),
        "days_overdue": days_overdue,
        "open_defects": defect_count,
        "blocked_reason": t.blocked_reason,
        "project_name": t.project.name,
        "project_id": t.project_id,
        "description": t.description,
        "reason": reason,
    }


def _sort_key(t: Task):
    return (_PRIORITY_RANK.get(t.priority.value, 9), t.due_date, t.id)


def get_active_project(db: Session) -> Project | None:
    """The single live project used by the PoC (first ACTIVE project)."""
    return db.execute(
        select(Project).where(Project.status == ProjectStatus.ACTIVE).order_by(Project.id).limit(1)
    ).scalar_one_or_none()


def get_priority_tasks(db: Session, today: date) -> dict:
    """Tasks due today, tomorrow, plus everything overdue — the core demo query."""
    project = get_active_project(db)
    if project is None:
        return {"project_name": None, "today": [], "tomorrow": [], "overdue": [], "open_defects": 0}

    tasks = db.execute(
        select(Task)
        .where(Task.project_id == project.id)
        .where(Task.status.in_(_ACTIVE_STATUSES))
    ).scalars().all()

    today_tasks = [t for t in tasks if t.scheduled_date <= today <= t.due_date or t.due_date == today]
    tomorrow_tasks = [t for t in tasks if t.scheduled_date <= today + timedelta(days=1) <= t.due_date]
    overdue = [t for t in tasks if t.due_date < today]

    today_tasks.sort(key=_sort_key)
    tomorrow_tasks.sort(key=_sort_key)
    overdue.sort(key=_sort_key)

    open_defects = db.execute(
        select(func.count())
        .select_from(Defect)
        .join(Task, Defect.task_id == Task.id)
        .where(Task.project_id == project.id)
        .where(Defect.status.in_([DefectStatus.OPEN, DefectStatus.IN_PROGRESS]))
    ).scalar_one()

    return {
        "project_name": project.name,
        "today": [_serialize_task(db, t) for t in today_tasks],
        "tomorrow": [_serialize_task(db, t) for t in tomorrow_tasks],
        "overdue": [_serialize_task(db, t) for t in overdue],
        "open_defects": open_defects,
    }


def get_tasks(db: Session, status: str | None = None, trade: str | None = None,
              on_date: date | None = None, limit: int = 50) -> list[dict]:
    """Filtered task list; values are matched case-insensitively by name."""
    q = select(Task).order_by(Task.due_date, Task.id).limit(limit)
    if status:
        try:
            q = q.where(Task.status == TaskStatus(status.lower().replace(" ", "_")))
        except ValueError:
            return []
    if trade:
        q = q.join(Trade, Task.trade_id == Trade.id).where(func.lower(Trade.name).like(f"%{trade.lower()}%"))
    if on_date:
        # a task is "on that date" when its window overlaps it
        q = q.where(and_(Task.scheduled_date <= on_date, Task.due_date >= on_date))
    return [_serialize_task(db, t) for t in db.execute(q).scalars().all()]


def get_defects(db: Session, status: str | None = None, limit: int = 50) -> list[dict]:
    q = select(Defect).order_by(Defect.created_at.desc()).limit(limit)
    if status:
        try:
            q = q.where(Defect.status == DefectStatus(status.lower().replace(" ", "_")))
        except ValueError:
            return []
    out = []
    for d in db.execute(q).scalars().all():
        out.append({
            "defect_id": d.id,
            "title": d.title,
            "description": d.description,
            "severity": d.severity.value,
            "status": d.status.value,
            "task_id": d.task_id,
            "task_title": d.task.title,
            "project_name": d.task.project.name,
            "trade": d.task.trade.name,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        })
    return out


def get_trades_workload(db: Session, today: date) -> list[dict]:
    """Crews currently allocated to the active project + their open task load."""
    project = get_active_project(db)
    if project is None:
        return []
    rows = db.execute(
        select(TradeAssignment, Trade)
        .join(Trade, TradeAssignment.trade_id == Trade.id)
        .where(TradeAssignment.project_id == project.id)
        .where(TradeAssignment.start_date <= today + timedelta(days=7))
        .order_by(TradeAssignment.start_date)
    ).all()
    out = []
    for ta, trade in rows:
        active_tasks = db.execute(
            select(Task)
            .where(Task.trade_id == trade.id, Task.project_id == project.id)
            .where(Task.status.in_(_ACTIVE_STATUSES))
        ).scalars().all()
        out.append({
            "trade": trade.name,
            "crew_lead": ta.crew_lead,
            "crew_size": ta.crew_size,
            "on_site_from": ta.start_date.isoformat(),
            "on_site_until": ta.end_date.isoformat() if ta.end_date else None,
            "notes": ta.notes,
            "active_tasks": [
                {"title": t.title, "status": t.status.value, "priority": t.priority.value,
                 "due_date": t.due_date.isoformat()}
                for t in sorted(active_tasks, key=_sort_key)
            ],
        })
    return out


def get_project_status(db: Session, today: date) -> dict:
    project = get_active_project(db)
    if project is None:
        return {}
    tasks = db.execute(select(Task).where(Task.project_id == project.id)).scalars().all()
    counts: dict[str, int] = {}
    for t in tasks:
        counts[t.status.value] = counts.get(t.status.value, 0) + 1
    open_defects = db.execute(
        select(func.count())
        .select_from(Defect)
        .join(Task, Defect.task_id == Task.id)
        .where(Task.project_id == project.id)
        .where(Defect.status.in_([DefectStatus.OPEN, DefectStatus.IN_PROGRESS]))
    ).scalar_one()
    return {
        "project_name": project.name,
        "address": project.address,
        "status": project.status.value,
        "days_elapsed": (today - project.start_date).days,
        "days_to_target": (project.target_completion_date - today).days,
        "target_completion_date": project.target_completion_date.isoformat(),
        "task_counts": counts,
        "total_tasks": len(tasks),
        "open_defects": open_defects,
    }
