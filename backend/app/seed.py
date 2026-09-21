"""Seed the database with realistic fake data.

Run: docker compose exec backend python -m app.seed
(or: docker compose exec backend python -m app.seed --drop  to rebuild tables first)

Dates are generated relative to *today* so the demo always looks live:
yesterday / today / tomorrow / this week / next week are all represented.
"""
import random
from datetime import date, timedelta

from sqlalchemy.orm import Session

from .db import SessionLocal, engine
from .models import (
    Base,
    Defect,
    DefectSeverity,
    DefectStatus,
    Project,
    ProjectStatus,
    Supervisor,
    Task,
    TaskPriority,
    TaskStatus,
    Trade,
    TradeAssignment,
)
from .models import TaskStatus as TS  # alias to avoid clash below

random.seed(42)

TODAY = date.today()


def d(offset: int) -> date:
    return TODAY + timedelta(days=offset)


def seed(drop: bool = False, db: Session | None = None) -> None:
    """Seed demo data. Pass `db` to seed into an existing session (used by tests)."""
    if drop:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    own_session = db is None
    if own_session:
        db = SessionLocal()
    try:
        if db.query(Task).count() > 0:
            print("Database already seeded — nothing to do (use --drop to rebuild).")
            return

        # --- Supervisor -----------------------------------------------------
        dave = Supervisor(name="Dave Marsh", email="dave.marsh@precode.example", phone="+64 21 555 0142")
        db.add(dave)
        db.flush()

        # --- Project ----------------------------------------------------------
        project = Project(
            supervisor_id=dave.id,
            name="14 Kowhai Crescent — New Build",
            address="14 Kowhai Crescent, Grey Lynn, Auckland",
            status=ProjectStatus.ACTIVE,
            start_date=d(-66),
            target_completion_date=d(+85),
        )
        db.add(project)
        db.flush()

        # --- Trades -----------------------------------------------------------
        trade_names = [
            ("Site Carpenter", "Framing, timber work, fix-outs", 68.0),
            ("Electrician", "Wiring, switchboards, lighting", 95.0),
            ("Plumber", "Drainage, pipework, fittings", 88.0),
            ("Roofer", "Roof cladding, flashing, spouting", 74.0),
            ("Gib Stopper", "Plasterboard stopping and finishing", 58.0),
        ]
        trades = {name: Trade(name=name, description=desc, typical_daily_rate=rate) for name, desc, rate in trade_names}
        db.add_all(trades.values())
        db.flush()

        # --- Trade assignments (crews on site this fortnight) -----------------
        assignments = [
            TradeAssignment(project_id=project.id, trade_id=trades["Site Carpenter"].id, crew_lead="Sione T.", crew_size=3, start_date=d(-14), end_date=d(+7), notes="Framing through to fix-out"),
            TradeAssignment(project_id=project.id, trade_id=trades["Electrician"].id, crew_lead="Priya N.", crew_size=2, start_date=d(-3), end_date=d(+6), notes="First fix wiring"),
            TradeAssignment(project_id=project.id, trade_id=trades["Plumber"].id, crew_lead="Marco V.", crew_size=2, start_date=d(-2), end_date=d(+8), notes="Drainage + first fix plumbing"),
            TradeAssignment(project_id=project.id, trade_id=trades["Roofer"].id, crew_lead="Hemi W.", crew_size=4, start_date=d(-6), end_date=d(+2), notes="Roof cladding, weather dependent"),
            TradeAssignment(project_id=project.id, trade_id=trades["Gib Stopper"].id, crew_lead="Lena K.", crew_size=2, start_date=d(+4), end_date=d(+14), notes="Booked for stopping after close-in"),
        ]
        db.add_all(assignments)
        db.flush()

        # --- Tasks --------------------------------------------------------------
        # (trade, title, status, priority, scheduled, due, description, blocked_reason)
        task_rows = [
            ("Roofer", "Close in roof — west elevation", "in_progress", "critical", -1, +2,
             "Last roof plane before cladding inspection; crane booked for sheets.", None),
            ("Roofer", "Install flashings and spouting", "pending", "high", +1, +3,
             "Depends on west elevation roof close-in.", None),
            ("Site Carpenter", "Framing — level 2 east wall", "in_progress", "high", -2, +1,
             "Steel lintel arrives today; frame inspection booked for tomorrow.", None),
            ("Site Carpenter", "Frame set-out — garage", "pending", "medium", -3, -1,
             "Standard 90x45 frame, tie down straps to spec. Slipped — crew pulled onto level 2 framing.", None),
            ("Site Carpenter", "Fix-out — skirtings and architraves", "pending", "low", +9, +12,
             "Do not start until gib stopping is complete.", None),
            ("Electrician", "First fix wiring — level 1", "in_progress", "high", -1, +1,
             "Runs for kitchen, lounge, 3 bedrooms. Switchboard energisation Friday.", None),
            ("Electrician", "Switchboard assembly and certification", "pending", "critical", +3, +3,
             "CoC needs signing before insulation closes walls.", None),
            ("Electrician", "Data cabling — home office", "pending", "low", +5, +6,
             "Cat6 to two drops.", None),
            ("Plumber", "Sewer drainage connection", "in_progress", "critical", -3, +0,
             "Trench is open; council inspection must be booked before backfill.", None),
            ("Plumber", "First fix plumbing — bathrooms", "pending", "high", +2, +5,
             "Both bathrooms; requires water main tap-in.", None),
            ("Plumber", "Water main tap-in", "pending", "medium", +4, +5,
             "Watercare approved for Thursday.", None),
            ("Gib Stopper", "Stop and tape — level 1 ceilings", "pending", "medium", +4, +7,
             "After electrical inspection and roof close-in.", None),
            ("Gib Stopper", "Stop and tape — walls level 1", "pending", "medium", +6, +9,
             "Follows ceilings.", None),
            ("Site Carpenter", "Install exterior joinery", "completed", "medium", -8, -6,
             "Windows and ranch slider installed.", None),
            ("Electrician", "Temporary site power and RCD", "completed", "low", -12, -10,
             "Certified and inspected.", None),
            ("Plumber", "Stormwater connections", "completed", "medium", -10, -8,
             "Connected to council main, inspection passed.", None),
        ]
        tasks: dict[str, Task] = {}
        for trade_name, title, status, priority, sched, due, desc, blocked in task_rows:
            t = Task(
                project_id=project.id,
                trade_id=trades[trade_name].id,
                title=title,
                description=desc,
                status=TS(status),
                priority=TaskPriority(priority),
                scheduled_date=d(sched),
                due_date=d(due),
                blocked_reason=blocked,
                completed_at=datetime_now_if_completed(status),
            )
            tasks[title] = t
            db.add(t)
        db.flush()

        # --- Defects (each links to a task) --------------------------------------
        defects = [
            Defect(task_id=tasks["Close in roof — west elevation"].id,
                   title="Roof sheets scratched — 3 panels",
                   description="Crane handling scratched three Colori panels on west plane. Supplier samples ordered for colour match.",
                   severity=DefectSeverity.MEDIUM, status=DefectStatus.OPEN, reported_by_id=dave.id),
            Defect(task_id=tasks["Sewer drainage connection"].id,
                   title="Drainage fall out of spec on run 3",
                   description="Laser shows 1:110 instead of 1:80 on run between MH2 and MH3. Needs re-bed before council inspection.",
                   severity=DefectSeverity.CRITICAL, status=DefectStatus.OPEN, reported_by_id=dave.id),
            Defect(task_id=tasks["First fix wiring — level 1"].id,
                   title="Missing nail plates at stud corners",
                   description="Two runs without nail plates where cables pass within 30mm of framing face.",
                   severity=DefectSeverity.LOW, status=DefectStatus.IN_PROGRESS, reported_by_id=dave.id),
            Defect(task_id=tasks["Install exterior joinery"].id,
                   title="Sealant bead uneven on ranch slider",
                   description="Cosmetic re-do of perimeter bead, scheduled with painter.",
                   severity=DefectSeverity.LOW, status=DefectStatus.RESOLVED, reported_by_id=dave.id,
                   resolved_at=None),
            Defect(task_id=tasks["Temporary site power and RCD"].id,
                   title="Temporary board labeling missing",
                   description="Board labels were replaced and photographed for records.",
                   severity=DefectSeverity.LOW, status=DefectStatus.CLOSED, reported_by_id=dave.id),
        ]
        db.add_all(defects)
        db.commit()

        print(f"Seeded: 1 project, {len(trades)} trades, {len(task_rows)} tasks, {len(defects)} defects.")
        print(f"Anchor date: {TODAY} (today) — dataset spans {d(-12)} … {d(+12)}")
    finally:
        if own_session:
            db.close()


def datetime_now_if_completed(status: str):
    from datetime import datetime, timezone
    return datetime.now(timezone.utc) if status == "completed" else None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--drop", action="store_true", help="drop and recreate all tables first")
    args = parser.parse_args()
    seed(drop=args.drop)
