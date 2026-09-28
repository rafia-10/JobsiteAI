"""API response schemas."""
from datetime import date, datetime

from pydantic import BaseModel


class SupervisorOut(BaseModel):
    id: int
    name: str
    email: str

    model_config = {"from_attributes": True}


class ProjectOut(BaseModel):
    id: int
    name: str
    address: str
    status: str
    start_date: date
    target_completion_date: date

    model_config = {"from_attributes": True}


class TradeOut(BaseModel):
    id: int
    name: str
    description: str

    model_config = {"from_attributes": True}


class TradeAssignmentOut(BaseModel):
    id: int
    trade: TradeOut
    crew_lead: str
    crew_size: int
    start_date: date
    end_date: date | None

    model_config = {"from_attributes": True}


class TaskFlatOut(BaseModel):
    """Flat task shape returned by the query layer (also what agent tools see)."""

    task_id: int
    title: str
    trade: str
    status: str
    priority: str
    scheduled_date: date
    due_date: date
    days_overdue: int
    open_defects: int
    blocked_reason: str | None = None
    project_name: str
    project_id: int
    description: str
    reason: str | None = None


class DefectFlatOut(BaseModel):
    """Flat defect shape returned by the query layer."""

    defect_id: int
    title: str
    description: str
    severity: str
    status: str
    task_id: int
    task_title: str
    project_name: str
    trade: str
    created_at: str | None = None


class SeedResult(BaseModel):
    seeded: bool
    message: str
    projects: int
    trades: int
    tasks: int
    defects: int


class PriorityTask(BaseModel):
    task_id: int
    title: str
    trade: str
    status: str
    priority: str
    scheduled_date: date
    due_date: date
    days_overdue: int
    open_defects: int
    reason: str | None = None


class PriorityResponse(BaseModel):
    project_name: str | None = None
    generated_at: datetime
    today: list[PriorityTask]
    tomorrow: list[PriorityTask]
    overdue: list[PriorityTask]
    open_defects: int
    summary: str


class AgentCitation(BaseModel):
    type: str      # e.g. "task", "defect", "trade_assignment"
    id: int
    title: str


class AgentResponse(BaseModel):
    answer: str
    source: str                  # "llm+tools" | "fallback"
    model: str | None = None
    tools_used: list[str]
    citations: list[AgentCitation]
    suggestions: list[str] = []  # contextual follow-up questions for the UI


class ToolCall(BaseModel):
    name: str
    arguments: dict
    result_preview: str


class AgentDebug(BaseModel):
    tool_calls: list[ToolCall]
    data_snapshot: dict
