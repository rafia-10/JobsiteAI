"""Seed the database with realistic fake data.

Run: docker compose exec backend python -m app.seed
(or: docker compose exec backend python -m app.seed --drop  to rebuild tables first)

Dates are generated relative to *today* so the demo always looks live:
yesterday / today / tomorrow / this week / next week are all represented.
"""
import random
from datetime import date, datetime, timedelta, timezone

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


def dt(days_ago: int, hour: int = 7, minute: int = 30) -> datetime:
    """A timestamp N days ago at a realistic morning reporting hour."""
    return datetime.combine(
        TODAY - timedelta(days=days_ago),
        datetime.min.time(),
    ).replace(hour=hour, minute=minute, tzinfo=timezone.utc)


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

        # --- Supervisors ------------------------------------------------------
        # The original PoC supervisor (Dave) plus a management team so defect
        # reporting, project ownership and QA sign-offs look like a real firm.
        dave = Supervisor(name="Dave Marsh", email="dave.marsh@precode.example", phone="+64 21 555 0142")
        aroha = Supervisor(name="Aroha Ngata", email="aroha.ngata@precode.example", phone="+64 22 431 8890")
        steve = Supervisor(name="Steve Okafor", email="steve.okafor@precode.example", phone="+64 27 712 3345")
        priya_s = Supervisor(name="Priya Sharma", email="priya.sharma@precode.example", phone="+64 21 038 7765")
        lena_s = Supervisor(name="Lena Sorensen", email="lena.sorensen@precode.example", phone="+64 27 550 2918")
        db.add_all([dave, aroha, steve, priya_s, lena_s])
        db.flush()

        # --- Trades (company-wide catalogue) -----------------------------------
        trade_defs = [
            ("Site Carpenter", "Framing, timber work, fix-outs", 68.0),
            ("Electrician", "Wiring, switchboards, lighting", 95.0),
            ("Plumber", "Drainage, pipework, fittings", 88.0),
            ("Roofer", "Roof cladding, flashing, spouting", 74.0),
            ("Gib Stopper", "Plasterboard stopping and finishing", 58.0),
            ("Painter", "Interior and exterior paint systems", 52.0),
            ("Tiler", "Bathroom and kitchen tiling, waterproofing", 62.0),
            ("Landscaper", "Hardscaping, retaining walls, planting", 55.0),
            ("Concrete Crew", "Slabs, foundations, driveways, footings", 71.0),
            ("Glazier", "Glass balustrades, shower glass, mirrors", 79.0),
        ]
        trades = {
            name: Trade(name=name, description=desc, typical_daily_rate=rate)
            for name, desc, rate in trade_defs
        }
        db.add_all(trades.values())
        db.flush()

        # --- Projects -----------------------------------------------------------
        # 1) Flagship ACTIVE build — test-coupled: name, crew leads, defect titles,
        #    and task titles ("Sewer drainage connection", "Framing — level 2 east
        #    wall", "Close in roof — west elevation") are asserted in the suite.
        project1 = Project(
            supervisor_id=dave.id,
            name="14 Kowhai Crescent — New Build",
            address="14 Kowhai Crescent, Grey Lynn, Auckland",
            status=ProjectStatus.ACTIVE,
            start_date=d(-66),
            target_completion_date=d(+85),
        )
        # 2) Second ACTIVE build — mid-programme, different trade mix.
        project2 = Project(
            supervisor_id=aroha.id,
            name="22 Rimu Street — Duplex Development",
            address="22 Rimu Street, Mount Eden, Auckland",
            status=ProjectStatus.ACTIVE,
            start_date=d(-40),
            target_completion_date=d(+120),
            created_at=dt(42),
        )
        # 3) Recently COMPLETED — full defect history incl. closed items.
        project3 = Project(
            supervisor_id=steve.id,
            name="8 Nikau Lane — Townhouse Retrofit",
            address="8 Nikau Lane, Devonport, Auckland",
            status=ProjectStatus.COMPLETED,
            start_date=d(-210),
            target_completion_date=d(-30),
            created_at=dt(214),
        )
        # 4) PLANNING — consents lodged, crews not yet on site.
        project4 = Project(
            supervisor_id=priya_s.id,
            name="31 Totara Way — New Build",
            address="31 Totara Way, Hobsonville, Auckland",
            status=ProjectStatus.PLANNING,
            start_date=d(+21),
            target_completion_date=d(+250),
            created_at=dt(9),
        )
        # 5) PAUSED — weather damage claim being assessed.
        project5 = Project(
            supervisor_id=lena_s.id,
            name="5 Miro Terrace — Renovation",
            address="5 Miro Terrace, Titirangi, Auckland",
            status=ProjectStatus.PAUSED,
            start_date=d(-95),
            target_completion_date=d(+40),
            created_at=dt(99),
        )
        db.add_all([project1, project2, project3, project4, project5])
        db.flush()

        # --- Trade assignments (crews on site this fortnight) -----------------
        assignments = [
            TradeAssignment(project_id=project1.id, trade_id=trades["Site Carpenter"].id, crew_lead="Sione T.", crew_size=3, start_date=d(-14), end_date=d(+7), notes="Framing through to fix-out"),
            TradeAssignment(project_id=project1.id, trade_id=trades["Electrician"].id, crew_lead="Priya N.", crew_size=2, start_date=d(-3), end_date=d(+6), notes="First fix wiring"),
            TradeAssignment(project_id=project1.id, trade_id=trades["Plumber"].id, crew_lead="Marco V.", crew_size=2, start_date=d(-2), end_date=d(+8), notes="Drainage + first fix plumbing"),
            TradeAssignment(project_id=project1.id, trade_id=trades["Roofer"].id, crew_lead="Hemi W.", crew_size=4, start_date=d(-6), end_date=d(+2), notes="Roof cladding, weather dependent"),
            TradeAssignment(project_id=project1.id, trade_id=trades["Gib Stopper"].id, crew_lead="Lena K.", crew_size=2, start_date=d(+4), end_date=d(+14), notes="Booked for stopping after close-in"),
            TradeAssignment(project_id=project1.id, trade_id=trades["Glazier"].id, crew_lead="Tom H.", crew_size=2, start_date=d(+9), end_date=d(+16), notes="Shower glass + balustrade, measure booked"),
            TradeAssignment(project_id=project2.id, trade_id=trades["Concrete Crew"].id, crew_lead="Big Joe R.", crew_size=5, start_date=d(-30), end_date=d(-5), notes="Slab pours both units, finished"),
            TradeAssignment(project_id=project2.id, trade_id=trades["Site Carpenter"].id, crew_lead="Wiremu P.", crew_size=4, start_date=d(-18), end_date=d(+20), notes="Full frame and truss programme"),
            TradeAssignment(project_id=project2.id, trade_id=trades["Roofer"].id, crew_lead="Sam T. (Sr.)", crew_size=3, start_date=d(+2), end_date=d(+12), notes="Unit A roof first, then B"),
            TradeAssignment(project_id=project2.id, trade_id=trades["Plumber"].id, crew_lead="Marco V.", crew_size=2, start_date=d(-8), end_date=d(+25), notes="Slab penetrations then first fix"),
            TradeAssignment(project_id=project2.id, trade_id=trades["Electrician"].id, crew_lead="Priya N.", crew_size=2, start_date=d(-8), end_date=d(+25), notes="Slab penetrations then first fix"),
            TradeAssignment(project_id=project2.id, trade_id=trades["Landscaper"].id, crew_lead="Ana G.", crew_size=3, start_date=d(+30), end_date=d(+55), notes="Fencing + driveways at end of programme"),
            TradeAssignment(project_id=project3.id, trade_id=trades["Site Carpenter"].id, crew_lead="Sione T.", crew_size=3, start_date=d(-200), end_date=d(-35), notes="Retrofit framing and joinery"),
            TradeAssignment(project_id=project3.id, trade_id=trades["Painter"].id, crew_lead="Rangi D.", crew_size=2, start_date=d(-60), end_date=d(-32), notes="Full repaint, signed off"),
            TradeAssignment(project_id=project3.id, trade_id=trades["Tiler"].id, crew_lead="Fatima Z.", crew_size=2, start_date=d(-70), end_date=d(-45), notes="Two wet areas per unit"),
            TradeAssignment(project_id=project5.id, trade_id=trades["Site Carpenter"].id, crew_lead="Wiremu P.", crew_size=2, start_date=d(-90), end_date=d(-20), notes="Stood down pending weather-tightness claim"),
            TradeAssignment(project_id=project5.id, trade_id=trades["Painter"].id, crew_lead="Rangi D.", crew_size=2, start_date=d(-88), end_date=d(-18), notes="Stopped at exterior prep coat"),
        ]
        db.add_all(assignments)
        db.flush()

        # --- Tasks --------------------------------------------------------------
        # (project, trade, title, status, priority, scheduled, due, description, blocked_reason)
        task_rows = [
            # ---------------- project1: flagship (test-coupled rows kept verbatim)
            (project1, "Roofer", "Close in roof — west elevation", "in_progress", "critical", -1, +2,
             "Last roof plane before cladding inspection; crane booked for sheets.", None),
            (project1, "Roofer", "Install flashings and spouting", "pending", "high", +1, +3,
             "Depends on west elevation roof close-in.", None),
            (project1, "Site Carpenter", "Framing — level 2 east wall", "in_progress", "high", -2, +1,
             "Steel lintel arrives today; frame inspection booked for tomorrow.", None),
            (project1, "Site Carpenter", "Frame set-out — garage", "pending", "medium", -3, -1,
             "Standard 90x45 frame, tie down straps to spec. Slipped — crew pulled onto level 2 framing.", None),
            (project1, "Site Carpenter", "Fix-out — skirtings and architraves", "pending", "low", +9, +12,
             "Do not start until gib stopping is complete.", None),
            (project1, "Electrician", "First fix wiring — level 1", "in_progress", "high", -1, +1,
             "Runs for kitchen, lounge, 3 bedrooms. Switchboard energisation Friday.", None),
            (project1, "Electrician", "Switchboard assembly and certification", "pending", "critical", +3, +3,
             "CoC needs signing before insulation closes walls.", None),
            (project1, "Electrician", "Data cabling — home office", "pending", "low", +5, +6,
             "Cat6 to two drops.", None),
            (project1, "Plumber", "Sewer drainage connection", "in_progress", "critical", -3, +0,
             "Trench is open; council inspection must be booked before backfill.", None),
            (project1, "Plumber", "First fix plumbing — bathrooms", "pending", "high", +2, +5,
             "Both bathrooms; requires water main tap-in.", None),
            (project1, "Plumber", "Water main tap-in", "pending", "medium", +4, +5,
             "Watercare approved for Thursday.", None),
            (project1, "Gib Stopper", "Stop and tape — level 1 ceilings", "pending", "medium", +4, +7,
             "After electrical inspection and roof close-in.", None),
            (project1, "Gib Stopper", "Stop and tape — walls level 1", "pending", "medium", +6, +9,
             "Follows ceilings.", None),
            (project1, "Site Carpenter", "Install exterior joinery", "completed", "medium", -8, -6,
             "Windows and ranch slider installed.", None),
            (project1, "Electrician", "Temporary site power and RCD", "completed", "low", -12, -10,
             "Certified and inspected.", None),
            (project1, "Plumber", "Stormwater connections", "completed", "medium", -10, -8,
             "Connected to council main, inspection passed.", None),
            # ---------------- project1: extra history/realism (added, not replacing)
            (project1, "Roofer", "Scaffold inspect and handover — roof zone", "completed", "medium", -7, -7,
             "Scafftag green, full perimeter, ladder access both gables.", None),
            (project1, "Electrician", "First fix wiring — level 2", "pending", "high", +6, +9,
             "Four bedrooms plus bathroom; runs after roof close-in.", None),
            (project1, "Gib Stopper", "Install plasterboard — level 1", "pending", "high", +8, +12,
             "10mm sheets walls, 13mm ceilings; order confirmed with supplier.", None),
            (project1, "Glazier", "Measure and order shower glass", "pending", "medium", +10, +14,
             "Measure after gib levels set; 10-week lead time confirmed.", None),
            (project1, "Site Carpenter", "Punch list walk — level 1", "pending", "low", +14, +16,
             "Walk with Dave before stopping starts on level 2.", None),

            # ---------------- project2: duplex development (active)
            (project2, "Concrete Crew", "Slab pour — Unit A", "completed", "critical", -28, -26,
             "32MPa slab, poly under; passed pre-pour inspection.", None),
            (project2, "Concrete Crew", "Slab pour — Unit B", "completed", "critical", -22, -20,
             "Pumped pour, cured 7 days before frame delivery.", None),
            (project2, "Site Carpenter", "Frame and truss — Unit A", "in_progress", "critical", -14, +3,
             "Frame erecting; trusses land Thursday (crane 7am-10am).", None),
            (project2, "Site Carpenter", "Frame and truss — Unit B", "in_progress", "high", -10, +8,
             "Walls standing; roof trusses next week.", None),
            (project2, "Site Carpenter", "Wrap and paper — Unit A", "pending", "high", +4, +6,
             "Rigid air barrier before roofing starts.", None),
            (project2, "Plumber", "Slab penetrations — Unit A", "completed", "high", -24, -23,
             "All penetrations sleeved and pressure tested.", None),
            (project2, "Plumber", "Slab penetrations — Unit B", "completed", "high", -19, -18,
             "Photos in job file for council.", None),
            (project2, "Plumber", "First fix plumbing — Unit A", "in_progress", "medium", -5, +10,
             "Running pipework behind frames as they close.", None),
            (project2, "Plumber", "Gully and stormwater — both units", "pending", "medium", +9, +14,
             "After frames are up; council inspection to follow.", None),
            (project2, "Electrician", "Slab penetrations — Unit A", "completed", "high", -24, -23,
             "Conduit stubs for kitchen island bench.", None),
            (project2, "Electrician", "First fix wiring — Unit A", "in_progress", "high", -6, +12,
             "Wiring behind frame; coordinate with plumber in common walls.", None),
            (project2, "Electrician", "First fix wiring — Unit B", "pending", "medium", +9, +18,
             "Start once trusses are on.", None),
            (project2, "Roofer", "Roof — Unit A", "pending", "high", +2, +12,
             "Colorsteel; depends on wrap and paper.", None),
            (project2, "Roofer", "Roof — Unit B", "pending", "medium", +14, +24,
             "Same crew moves across after Unit A.", None),
            (project2, "Landscaper", "Site fencing and hoarding", "completed", "low", -32, -30,
             "Temporary fencing with privacy mesh.", None),
            (project2, "Site Carpenter", "Pergola framing — Unit A", "blocked", "low", +18, +25,
             "Engineer revised the beam detail; waiting on updated PS1.",
             "Engineering sign-off outstanding — architect resubmitting calcs."),
            (project2, "Electrician", "EV charger rough-in — Unit B garage", "pending", "low", +20, +26,
             "Client upgraded spec after sales negotiation.", None),

            # ---------------- project3: completed townhouse retrofit
            (project3, "Site Carpenter", "Load-bearing wall removal — Unit 1", "completed", "critical", -180, -172,
             "Steel beam install per engineer's detail; inspection passed.", None),
            (project3, "Site Carpenter", "Kitchen fit-out — all units", "completed", "high", -120, -95,
             "Stone tops templated then installed; punch list closed.", None),
            (project3, "Tiler", "Wet area tiling — Units 1-4", "completed", "high", -95, -70,
             "Waterproofing tested 48h before tiling each wet area.", None),
            (project3, "Painter", "Interior repaint — full programme", "completed", "medium", -80, -50,
             "Two coats, Resene Space Cote throughout.", None),
            (project3, "Painter", "Exterior weatherboard repaint", "completed", "medium", -60, -40,
             "Prep coat, undercoat and two topcoats; wet weather delay of 4 days absorbed.", None),
            (project3, "Plumber", "Bathroom renovations — all units", "completed", "high", -110, -80,
             "New vanities, mixers and tiled showers.", None),
            (project3, "Electrician", "Lighting upgrade — LED throughout", "completed", "medium", -130, -105,
             "Downlights, dimmers and new switch plates.", None),
            (project3, "Site Carpenter", "Final clean and handover", "completed", "medium", -38, -31,
             "Handover packs issued to owners' committee.", None),

            # ---------------- project4: planning (work queued, not started)
            (project4, "Concrete Crew", "Site shed and toilet hire install", "pending", "low", +18, +20,
             "Deliver before diggers arrive.", None),
            (project4, "Concrete Crew", "Excavate and pour footings", "pending", "high", +22, +30,
             "Geotech report reviewed; engineer's footing schedule attached.", None),
            (project4, "Site Carpenter", "Slab preparation and poly", "pending", "high", +32, +38,
             "Compact hardfill to spec, poly laps taped.", None),
            (project4, "Plumber", "Stormwater and wastewater design", "pending", "medium", +15, +22,
             "Hydraulic consultant engaged; plans with council for approval.", None),

            # ---------------- project5: paused (blocked by claim)
            (project5, "Site Carpenter", "Weather-tightness remediation plan", "blocked", "critical", -18, +5,
             "Weathertightness assessor engaged; scope under insurance review.",
             "Awaiting insurance assessor's scope of works."),
            (project5, "Painter", "Exterior repaint — hold", "blocked", "low", -10, +15,
             "Paused at prep coat until envelope remediation is signed off.",
             "Remediation scope not finalised."),
            (project5, "Site Carpenter", "Deck framing repair", "blocked", "high", -30, +8,
             "Joist ends rotted; repair detail from engineer pending.",
             "Insurance claim assessment in progress."),
        ]
        tasks: dict[str, Task] = {}
        for project, trade_name, title, status, priority, sched, due, desc, blocked in task_rows:
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
                completed_at=dt(max(0, -due), hour=16) if status == "completed" else None,
            )
            tasks[title] = t
            db.add(t)
        db.flush()

        # --- Defects (each links to a task) --------------------------------------
        defects = [
            Defect(task_id=tasks["Close in roof — west elevation"].id,
                   title="Roof sheets scratched — 3 panels",
                   description="Crane handling scratched three Colori panels on west plane. Supplier samples ordered for colour match.",
                   severity=DefectSeverity.MEDIUM, status=DefectStatus.OPEN, reported_by_id=dave.id, created_at=dt(1, 8, 15)),
            Defect(task_id=tasks["Sewer drainage connection"].id,
                   title="Drainage fall out of spec on run 3",
                   description="Laser shows 1:110 instead of 1:80 on run between MH2 and MH3. Needs re-bed before council inspection.",
                   severity=DefectSeverity.CRITICAL, status=DefectStatus.OPEN, reported_by_id=dave.id, created_at=dt(2, 7, 45)),
            Defect(task_id=tasks["First fix wiring — level 1"].id,
                   title="Missing nail plates at stud corners",
                   description="Two runs without nail plates where cables pass within 30mm of framing face.",
                   severity=DefectSeverity.LOW, status=DefectStatus.IN_PROGRESS, reported_by_id=dave.id, created_at=dt(3, 9, 5)),
            Defect(task_id=tasks["Install exterior joinery"].id,
                   title="Sealant bead uneven on ranch slider",
                   description="Cosmetic re-do of perimeter bead, scheduled with painter.",
                   severity=DefectSeverity.LOW, status=DefectStatus.RESOLVED, reported_by_id=dave.id,
                   created_at=dt(9, 10, 20), resolved_at=dt(6, 15, 0)),
            Defect(task_id=tasks["Temporary site power and RCD"].id,
                   title="Temporary board labeling missing",
                   description="Board labels were replaced and photographed for records.",
                   severity=DefectSeverity.LOW, status=DefectStatus.CLOSED, reported_by_id=dave.id,
                   created_at=dt(12, 11, 0), resolved_at=dt(11, 14, 30)),
            # project1 extras
            Defect(task_id=tasks["Framing — level 2 east wall"].id,
                   title="Lintel bearing pad missing on opening 3",
                   description="Steel lintel landed without 5mm bearing pads; carpenter crew fabricating shims today.",
                   severity=DefectSeverity.HIGH, status=DefectStatus.OPEN, reported_by_id=aroha.id, created_at=dt(1, 13, 40)),
            Defect(task_id=tasks["Frame set-out — garage"].id,
                   title="Garage slab anchor spacing off",
                   description="Two anchors outside 300mm tolerance on north wall. Plans re-marked; fix scheduled before frame erection.",
                   severity=DefectSeverity.MEDIUM, status=DefectStatus.IN_PROGRESS, reported_by_id=dave.id, created_at=dt(4, 8, 55)),
            Defect(task_id=tasks["Stop and tape — level 1 ceilings"].id,
                   title="Ceiling batch colour mismatch (pre-check)",
                   description="Supplier confirmed next batch matches existing; flagged early to avoid rework.",
                   severity=DefectSeverity.LOW, status=DefectStatus.OPEN, reported_by_id=lena_s.id, created_at=dt(0, 12, 10)),

            # project2 defects
            Defect(task_id=tasks["Frame and truss — Unit A"].id,
                   title="Truss delivery short-shipped",
                   description="Three trusses missing from delivery 2; supplier resending for Friday crane slot.",
                   severity=DefectSeverity.HIGH, status=DefectStatus.OPEN, reported_by_id=aroha.id, created_at=dt(1, 7, 20)),
            Defect(task_id=tasks["Frame and truss — Unit B"].id,
                   title="Wall misaligned at utility void",
                   description="Frame 4 out of plumb 8mm at bottom plate; packers ordered, bracing to be re-fixed after correction.",
                   severity=DefectSeverity.MEDIUM, status=DefectStatus.IN_PROGRESS, reported_by_id=aroha.id, created_at=dt(3, 9, 15)),
            Defect(task_id=tasks["First fix wiring — Unit A"].id,
                   title="Cable run crosses plumbing chase",
                   description="Bedroom 2 run crosses the plumber's chase — relocate 150mm clear per spec.",
                   severity=DefectSeverity.MEDIUM, status=DefectStatus.OPEN, reported_by_id=priya_s.id, created_at=dt(2, 14, 25)),
            Defect(task_id=tasks["Slab pour — Unit B"].id,
                   title="Slab surface crazing near pour joint",
                   description="Cosmetic crazing within tolerance; documented and accepted by engineer via email.",
                   severity=DefectSeverity.LOW, status=DefectStatus.CLOSED, reported_by_id=aroha.id,
                   created_at=dt(19, 10, 5), resolved_at=dt(17, 16, 0)),

            # project3 (completed build) — historic defect trail
            Defect(task_id=tasks["Wet area tiling — Units 1-4"].id,
                   title="Lippage on Unit 2 shower floor",
                   description="Re-tiled shower floor; slope corrected to fall and re-grouted.",
                   severity=DefectSeverity.MEDIUM, status=DefectStatus.CLOSED, reported_by_id=steve.id,
                   created_at=dt(85, 8, 30), resolved_at=dt(78, 15, 0)),
            Defect(task_id=tasks["Bathroom renovations — all units"].id,
                   title="Mixer cartridge faulty — Unit 3",
                   description="Warranty replacement fitted; tested at 1.5 bar for 30 minutes.",
                   severity=DefectSeverity.LOW, status=DefectStatus.CLOSED, reported_by_id=steve.id,
                   created_at=dt(72, 11, 45), resolved_at=dt(70, 9, 30)),
            Defect(task_id=tasks["Interior repaint — full programme"].id,
                   title="Paint overspray on joinery",
                   description="Window frames masked and re-cut; final inspection passed.",
                   severity=DefectSeverity.LOW, status=DefectStatus.CLOSED, reported_by_id=steve.id,
                   created_at=dt(55, 13, 10), resolved_at=dt(52, 12, 0)),
            Defect(task_id=tasks["Lighting upgrade — LED throughout"].id,
                   title="Dimmer flicker at low setting — lounge",
                   description="Driver swapped for compatible unit; flicker gone at minimum dim.",
                   severity=DefectSeverity.MEDIUM, status=DefectStatus.CLOSED, reported_by_id=steve.id,
                   created_at=dt(100, 15, 20), resolved_at=dt(96, 10, 15)),
            Defect(task_id=tasks["Final clean and handover"].id,
                   title="Garage remote not programmed",
                   description="Remotes paired to motor and handed over with manual.",
                   severity=DefectSeverity.LOW, status=DefectStatus.CLOSED, reported_by_id=steve.id,
                   created_at=dt(33, 9, 0), resolved_at=dt(32, 14, 45)),

            # project5 (paused) — the blockers themselves
            Defect(task_id=tasks["Weather-tightness remediation plan"].id,
                   title="Water ingress at parapet — Unit 4 boundary",
                   description="Moisture readings elevated along parapet; assessor opening for intrusive survey next week.",
                   severity=DefectSeverity.CRITICAL, status=DefectStatus.IN_PROGRESS, reported_by_id=lena_s.id, created_at=dt(20, 7, 55)),
            Defect(task_id=tasks["Deck framing repair"].id,
                   title="Deck joist rot — 6 joists",
                   description="Joists 3-8 show advanced rot at wall junction; engineer's repair detail awaited.",
                   severity=DefectSeverity.HIGH, status=DefectStatus.OPEN, reported_by_id=lena_s.id, created_at=dt(28, 8, 40)),
        ]
        db.add_all(defects)
        db.commit()

        print(f"Seeded: {db.query(Project).count()} projects, {db.query(Trade).count()} trades, "
              f"{db.query(Task).count()} tasks, {db.query(Defect).count()} defects, "
              f"{db.query(Supervisor).count()} supervisors.")
        print(f"Anchor date: {TODAY} (today) — dataset spans {d(-214)} … {d(+38)}")
    finally:
        if own_session:
            db.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--drop", action="store_true", help="drop and recreate all tables first")
    args = parser.parse_args()
    seed(drop=args.drop)
