"""Groundedness: the tool functions return data that matches the seed dataset."""
from datetime import date, timedelta

from app import queries


def test_priority_buckets(db_session):
    data = queries.get_priority_tasks(db_session, date.today())
    assert data["project_name"] == "14 Kowhai Crescent — New Build"
    assert data["overdue"], "seed must contain overdue tasks"
    assert data["today"], "seed must contain tasks due today"
    assert data["tomorrow"], "seed must contain tasks due tomorrow"
    assert data["open_defects"] == 6  # 4 open + 2 in_progress on the flagship build

    for bucket in ("overdue", "today", "tomorrow"):
        for t in data[bucket]:
            assert t["status"] in ("pending", "in_progress", "blocked")
            assert t["trade"]
            assert t["due_date"] <= (date.today() + timedelta(days=3)).isoformat() or bucket != "today"


def test_overdue_tasks_have_positive_days(db_session):
    data = queries.get_priority_tasks(db_session, date.today())
    for t in data["overdue"]:
        assert t["days_overdue"] >= 1


def test_get_tasks_filter_by_trade(db_session):
    tasks = queries.get_tasks(db_session, trade="roofer")
    assert tasks
    assert all("Roofer" == t["trade"] for t in tasks)


def test_get_tasks_filter_by_status(db_session):
    tasks = queries.get_tasks(db_session, status="completed")
    assert tasks
    assert all(t["status"] == "completed" for t in tasks)


def test_get_tasks_on_date_window(db_session):
    today = date.today()
    tasks = queries.get_tasks(db_session, on_date=today)
    assert tasks
    for t in tasks:
        assert t["scheduled_date"] <= today.isoformat() <= t["due_date"]


def test_get_defects_status_filter(db_session):
    open_defects = queries.get_defects(db_session, status="open")
    assert open_defects
    assert all(d["status"] == "open" for d in open_defects)
    assert any(d["severity"] == "critical" for d in open_defects)


def test_trades_workload_includes_crew_leads(db_session):
    crews = queries.get_trades_workload(db_session, date.today())
    leads = {c["crew_lead"] for c in crews}
    assert {"Sione T.", "Priya N.", "Marco V."} <= leads
    roofer = next(c for c in crews if c["trade"] == "Roofer")
    assert roofer["active_tasks"]


def test_project_status_counts(db_session):
    status = queries.get_project_status(db_session, date.today())
    assert status["project_name"] == "14 Kowhai Crescent — New Build"
    assert status["total_tasks"] == 21
    assert status["task_counts"].get("completed", 0) == 4
