"""PreCode schema — designed up front.

Tables
------
supervisors        : platform users who run builds
projects           : a residential build, owned by one supervisor
trades             : catalogue of trades (Electrician, Plumber, ...)
trade_assignments  : allocation of a trade crew to a project (crew lead, size, dates)
tasks              : unit of work; belongs to a project and a trade; has status,
                     priority, scheduled/due dates
defects            : issue raised against a task (and therefore a project)

Relationships
-------------
project 1-* task, task 1-* defect, task *-1 trade, trade 1-* trade_assignment,
project 1-* trade_assignment, supervisor 1-* project (and reports defects).
"""
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ProjectStatus(StrEnum):
    PLANNING = "planning"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"


class TaskStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"


class TaskPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DefectStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class DefectSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


def _enum(e: type[StrEnum]):
    """Non-native enum stored as a short string; keeps SQL portable and readable."""
    return Enum(e, values_callable=lambda x: [m.value for m in x], native_enum=False, length=20)


class Supervisor(Base):
    __tablename__ = "supervisors"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    phone: Mapped[str] = mapped_column(String(40), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    projects: Mapped[list["Project"]] = relationship(back_populates="supervisor")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    supervisor_id: Mapped[int] = mapped_column(ForeignKey("supervisors.id"))
    name: Mapped[str] = mapped_column(String(200))
    address: Mapped[str] = mapped_column(String(300), default="")
    status: Mapped[ProjectStatus] = mapped_column(_enum(ProjectStatus), default=ProjectStatus.ACTIVE)
    start_date: Mapped[date] = mapped_column(Date)
    target_completion_date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    supervisor: Mapped[Supervisor] = relationship(back_populates="projects")
    tasks: Mapped[list["Task"]] = relationship(back_populates="project")
    trade_assignments: Mapped[list["TradeAssignment"]] = relationship(back_populates="project")


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    description: Mapped[str] = mapped_column(String(300), default="")
    typical_daily_rate: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)

    tasks: Mapped[list["Task"]] = relationship(back_populates="trade")
    assignments: Mapped[list["TradeAssignment"]] = relationship(back_populates="trade")


class TradeAssignment(Base):
    """A trade crew allocated to a project for a period (the 'trade allocations' view)."""

    __tablename__ = "trade_assignments"
    __table_args__ = (UniqueConstraint("project_id", "trade_id", name="uq_project_trade"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    trade_id: Mapped[int] = mapped_column(ForeignKey("trades.id"))
    crew_lead: Mapped[str] = mapped_column(String(120))
    crew_size: Mapped[int] = mapped_column(default=1)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str] = mapped_column(String(300), default="")

    project: Mapped[Project] = relationship(back_populates="trade_assignments")
    trade: Mapped[Trade] = relationship(back_populates="assignments")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    trade_id: Mapped[int] = mapped_column(ForeignKey("trades.id"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[TaskStatus] = mapped_column(_enum(TaskStatus), default=TaskStatus.PENDING)
    priority: Mapped[TaskPriority] = mapped_column(_enum(TaskPriority), default=TaskPriority.MEDIUM)
    scheduled_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    blocked_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped[Project] = relationship(back_populates="tasks")
    trade: Mapped[Trade] = relationship(back_populates="tasks")
    defects: Mapped[list["Defect"]] = relationship(back_populates="task")


class Defect(Base):
    __tablename__ = "defects"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[DefectSeverity] = mapped_column(_enum(DefectSeverity), default=DefectSeverity.MEDIUM)
    status: Mapped[DefectStatus] = mapped_column(_enum(DefectStatus), default=DefectStatus.OPEN)
    reported_by_id: Mapped[int] = mapped_column(ForeignKey("supervisors.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    task: Mapped[Task] = relationship(back_populates="defects")
    reported_by: Mapped[Supervisor] = relationship()
