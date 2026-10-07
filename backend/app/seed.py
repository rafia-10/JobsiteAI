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
        tui = Supervisor(name="Tui Waititi", email="tui.waititi@precode.example", phone="+64 21 555 9071")
        james = Supervisor(name="James Fletcher", email="james.fletcher@precode.example", phone="+64 27 884 2210")
        hana = Supervisor(name="Hana Kim", email="hana.kim@precode.example", phone="+64 22 630 4457")
        db.add_all([dave, aroha, steve, priya_s, lena_s, tui, james, hana])
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
            ("Scaffolder", "Erect, tag and strike scaffold systems", 72.0),
            ("Cabinetmaker", "Kitchen and vanity joinery, hardware fit-off", 84.0),
            ("HVAC Technician", "Heat pumps, HRV/ERV ventilation installs", 93.0),
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
        # 6) ACTIVE — architectural build, mid-programme (different crew mix).
        project6 = Project(
            supervisor_id=tui.id,
            name="7 Kauri Lane — Architectural Build",
            address="7 Kauri Lane, Titirangi, Auckland",
            status=ProjectStatus.ACTIVE,
            start_date=d(-52),
            target_completion_date=d(+95),
            created_at=dt(55),
        )
        # 7) COMPLETED — commercial-style fit-out, full historic trail.
        project7 = Project(
            supervisor_id=james.id,
            name="19a Rata Street — Unit Fit-out",
            address="19a Rata Street, Grey Lynn, Auckland",
            status=ProjectStatus.COMPLETED,
            start_date=d(-300),
            target_completion_date=d(-60),
            created_at=dt(306),
        )
        # 8) ACTIVE — early stage, just off the slab.
        project8 = Project(
            supervisor_id=hana.id,
            name="12 Wharf Road — Townhouse Pair",
            address="12 Wharf Road, Herne Bay, Auckland",
            status=ProjectStatus.ACTIVE,
            start_date=d(-18),
            target_completion_date=d(+150),
            created_at=dt(21),
        )
        db.add_all([project1, project2, project3, project4, project5, project6, project7, project8])
        db.flush()

        # --- Trade assignments (crews: on site now, finished, and booked ahead) -
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
            TradeAssignment(project_id=project5.id, trade_id=trades["Plumber"].id, crew_lead="Kahu R.", crew_size=2, start_date=d(-60), end_date=d(-15), notes="Interior rough-in paused mid-run"),
            TradeAssignment(project_id=project5.id, trade_id=trades["Scaffolder"].id, crew_lead="Sonny K.", crew_size=2, start_date=d(-40), end_date=d(-10), notes="Struck to half scaffold, awaiting assessor"),
            TradeAssignment(project_id=project1.id, trade_id=trades["Scaffolder"].id, crew_lead="Sonny K.", crew_size=2, start_date=d(-7), end_date=d(+10), notes="Roof zone + perimeter, weekly scaffold inspection"),
            TradeAssignment(project_id=project2.id, trade_id=trades["Gib Stopper"].id, crew_lead="Bex T.", crew_size=3, start_date=d(+12), end_date=d(+40), notes="Stopping Unit A after close-in"),
            TradeAssignment(project_id=project2.id, trade_id=trades["HVAC Technician"].id, crew_lead="Dan P.", crew_size=2, start_date=d(+28), end_date=d(+42), notes="Heat pumps and HRV, both units"),
            TradeAssignment(project_id=project2.id, trade_id=trades["Cabinetmaker"].id, crew_lead="Anika M.", crew_size=2, start_date=d(+35), end_date=d(+50), notes="Kitchens and vanities at fit-out"),
            TradeAssignment(project_id=project3.id, trade_id=trades["Electrician"].id, crew_lead="Anika M.", crew_size=2, start_date=d(-160), end_date=d(-105), notes="LED upgrade and switchboard rework"),
            TradeAssignment(project_id=project3.id, trade_id=trades["Roofer"].id, crew_lead="Sam T. (Sr.)", crew_size=3, start_date=d(-195), end_date=d(-155), notes="Reroof both units before repaint"),
            TradeAssignment(project_id=project3.id, trade_id=trades["Plumber"].id, crew_lead="Marco V.", crew_size=2, start_date=d(-125), end_date=d(-85), notes="Bathroom renovations, all units"),
            TradeAssignment(project_id=project3.id, trade_id=trades["Glazier"].id, crew_lead="Tom H.", crew_size=2, start_date=d(-105), end_date=d(-78), notes="Shower screens and mirrors"),
            TradeAssignment(project_id=project4.id, trade_id=trades["Concrete Crew"].id, crew_lead="Big Joe R.", crew_size=5, start_date=d(+20), end_date=d(+34), notes="Footings and slab programme, weather permitting"),
            TradeAssignment(project_id=project4.id, trade_id=trades["Plumber"].id, crew_lead="Kahu R.", crew_size=2, start_date=d(+16), end_date=d(+30), notes="Under-slab drainage once excavation is certified"),
            TradeAssignment(project_id=project4.id, trade_id=trades["Site Carpenter"].id, crew_lead="Wiremu P.", crew_size=4, start_date=d(+31), end_date=d(+60), notes="Frame and truss, provisional start"),
            TradeAssignment(project_id=project4.id, trade_id=trades["Scaffolder"].id, crew_lead="Sonny K.", crew_size=2, start_date=d(+35), end_date=d(+45), notes="Perimeter scaffold at frame start"),
            TradeAssignment(project_id=project6.id, trade_id=trades["Concrete Crew"].id, crew_lead="Big Joe R.", crew_size=5, start_date=d(-52), end_date=d(-25), notes="Foundations and slab, cured and stripped"),
            TradeAssignment(project_id=project6.id, trade_id=trades["Site Carpenter"].id, crew_lead="Sione T.", crew_size=4, start_date=d(-45), end_date=d(+20), notes="Frame, truss and roof substrate"),
            TradeAssignment(project_id=project6.id, trade_id=trades["Electrician"].id, crew_lead="Priya N.", crew_size=2, start_date=d(-20), end_date=d(+15), notes="First fix behind frame"),
            TradeAssignment(project_id=project6.id, trade_id=trades["Plumber"].id, crew_lead="Marco V.", crew_size=2, start_date=d(-18), end_date=d(+10), notes="First fix and underfloor drainage"),
            TradeAssignment(project_id=project6.id, trade_id=trades["Roofer"].id, crew_lead="Hemi W.", crew_size=3, start_date=d(+5), end_date=d(+25), notes="Long-run roofing after close-in"),
            TradeAssignment(project_id=project6.id, trade_id=trades["Gib Stopper"].id, crew_lead="Lena K.", crew_size=3, start_date=d(+18), end_date=d(+35), notes="Stopping and painting prep"),
            TradeAssignment(project_id=project7.id, trade_id=trades["Site Carpenter"].id, crew_lead="Wiremu P.", crew_size=3, start_date=d(-290), end_date=d(-150), notes="Fit-out framing and bulkheads"),
            TradeAssignment(project_id=project7.id, trade_id=trades["Electrician"].id, crew_lead="Anika M.", crew_size=2, start_date=d(-200), end_date=d(-120), notes="Power and data fit-out"),
            TradeAssignment(project_id=project7.id, trade_id=trades["Tiler"].id, crew_lead="Fatima Z.", crew_size=2, start_date=d(-170), end_date=d(-110), notes="Lobby floors and wet areas"),
            TradeAssignment(project_id=project7.id, trade_id=trades["Painter"].id, crew_lead="Rangi D.", crew_size=2, start_date=d(-150), end_date=d(-90), notes="Final coat, handed over"),
            TradeAssignment(project_id=project7.id, trade_id=trades["Cabinetmaker"].id, crew_lead="Anika M.", crew_size=2, start_date=d(-120), end_date=d(-75), notes="Kitchens and vanities installed"),
            TradeAssignment(project_id=project8.id, trade_id=trades["Concrete Crew"].id, crew_lead="Big Joe R.", crew_size=4, start_date=d(-18), end_date=d(-4), notes="Slab poured week 2"),
            TradeAssignment(project_id=project8.id, trade_id=trades["Scaffolder"].id, crew_lead="Sonny K.", crew_size=2, start_date=d(-5), end_date=d(+30), notes="Full perimeter, roof edge protection"),
            TradeAssignment(project_id=project8.id, trade_id=trades["Site Carpenter"].id, crew_lead="Sione T.", crew_size=4, start_date=d(-10), end_date=d(+40), notes="Frame programme both units"),
            TradeAssignment(project_id=project8.id, trade_id=trades["Plumber"].id, crew_lead="Kahu R.", crew_size=2, start_date=d(+2), end_date=d(+35), notes="Under-slab then first fix"),
            TradeAssignment(project_id=project8.id, trade_id=trades["Electrician"].id, crew_lead="Priya N.", crew_size=2, start_date=d(+5), end_date=d(+45), notes="First fix once frame closes"),
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
            (project2, "Plumber", "Slab penetrations — plumbing, Unit A", "completed", "high", -24, -23,
             "All penetrations sleeved and pressure tested.", None),
            (project2, "Plumber", "Slab penetrations — Unit B", "completed", "high", -19, -18,
             "Photos in job file for council.", None),
            (project2, "Plumber", "First fix plumbing — Unit A", "in_progress", "medium", -5, +10,
             "Running pipework behind frames as they close.", None),
            (project2, "Plumber", "Gully and stormwater — both units", "pending", "medium", +9, +14,
             "After frames are up; council inspection to follow.", None),
            (project2, "Electrician", "Slab penetrations — electrical, Unit A", "completed", "high", -24, -23,
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
            (project5, "Plumber", "Interior rough-in — pause", "blocked", "high", -60, -20,
             "Stopped mid-run in kitchen wall; caps fitted.",
             "Paused with the claim — no trades on site."),
            (project5, "Scaffolder", "Half-scaffold maintain and inspect", "blocked", "medium", -35, -15,
             "Structure left at half height for the assessor's access.",
             "Site access restricted pending assessment."),
            (project5, "Site Carpenter", "Rot repair — bathroom subfloor Unit 4", "blocked", "critical", -25, +10,
             "Lift boards once assessor signs off scope.",
             "Insurance scope of works outstanding."),
            (project5, "Site Carpenter", "Reinstate parapet capping", "pending", "high", +18, +30,
             "Follows water-ingress remediation design.", None),

            # ---------------- project2: fit-out and services queued behind framing
            (project2, "Gib Stopper", "Install plasterboard — Unit A ceilings", "pending", "medium", +13, +17,
             "Booked after roof and first-fix sign-off.", None),
            (project2, "Gib Stopper", "Stop and tape — Unit A walls", "pending", "medium", +16, +22,
             "Level 5 finish to living areas per plans.", None),
            (project2, "HVAC Technician", "Heat pumps — supply and install both units", "pending", "medium", +30, +40,
             "Client spec: two indoor heads per unit.", None),
            (project2, "HVAC Technician", "HRV ducting — ceiling spaces", "pending", "low", +33, +42,
             "Coordinate with gib — before ceilings close.", None),
            (project2, "Cabinetmaker", "Kitchen joinery — Unit A measure", "pending", "medium", +36, +38,
             "Site measure after gib levels are set.", None),
            (project2, "Cabinetmaker", "Vanities and wardrobes — both units", "pending", "low", +44, +52,
             "Install at fit-out, after tiling.", None),
            (project2, "Site Carpenter", "Barge boards and fascia — Unit A", "pending", "medium", +8, +11,
             "Alongside roofing; primed joinery supplied.", None),
            (project2, "Site Carpenter", "Interior door hanging — Unit A", "pending", "low", +24, +30,
             "After stopping first coat; 20 doors + 3 sliders.", None),
            (project2, "Electrician", "Switchboard and RCD — Unit A", "pending", "high", +14, +18,
             "Board install before plasterboard close-up.", None),

            # ---------------- project3: extra completed history
            (project3, "Roofer", "Full reroof — Units 1-4", "completed", "high", -195, -158,
             "Long-run steel over new underlay; warranty issued.", None),
            (project3, "Electrician", "Switchboard upgrade — all units", "completed", "high", -150, -132,
             "Main boards replaced; verification signed.", None),
            (project3, "Electrician", "Power and data fit-out — Units 2-4", "completed", "medium", -145, -112,
             "Extra outlets and data points per client schedule.", None),
            (project3, "Plumber", "New laundry plumbing — Unit 4", "completed", "medium", -108, -92,
             "Relocated wasteflow and taps; pressure tested.", None),
            (project3, "Glazier", "Mirrors and shower screens — all units", "completed", "medium", -102, -80,
             "Installed after tiling; silicone cured before use.", None),
            (project3, "Tiler", "Splashbacks — kitchens, all units", "completed", "low", -90, -74,
             "Glass splashbacks fitted after stone tops.", None),

            # ---------------- project4: planning — more of the programme queued
            (project4, "Concrete Crew", "Set out and punch footings", "pending", "high", +24, +27,
             "Surveyor set-out; engineer on site for pour.", None),
            (project4, "Concrete Crew", "Slab pour — house pad", "pending", "critical", +40, +41,
             "32MPa with poly under; pump booked for the morning.", None),
            (project4, "Plumber", "Under-slab drainage rough-in", "pending", "high", +26, +31,
             "Before rebar; council inspection mid-window.", None),
            (project4, "Site Carpenter", "Delivery and store — frame pack", "pending", "medium", +32, +34,
             "Keep off ground, cover against weather.", None),
            (project4, "Site Carpenter", "Frame lift — ground floor", "pending", "high", +35, +45,
             "Two crews, crane for portal beam day 2.", None),
            (project4, "Scaffolder", "Perimeter scaffold — house pad provision", "pending", "medium", +35, +38,
             "Erect at frame start; scaffold tag scheme.", None),

            # ---------------- project6: Kauri Lane (active, mid-programme)
            (project6, "Concrete Crew", "Foundations and pile caps", "completed", "critical", -52, -45,
             "Engineer sat pours; concrete tests passed.", None),
            (project6, "Concrete Crew", "Slab pour — main house", "completed", "critical", -40, -38,
             "32MPa, power-floated, poly over slab.", None),
            (project6, "Site Carpenter", "Frame and truss — ground floor", "completed", "high", -30, -18,
             "Portal beam landed with crane; braced and pegged.", None),
            (project6, "Site Carpenter", "Frame and truss — first floor", "in_progress", "critical", -14, +4,
             "Walls standing; roof trusses land next week.", None),
            (project6, "Site Carpenter", "Roof substrate and barge", "pending", "high", +3, +9,
             "Ply substrate ready for long-run steel.", None),
            (project6, "Site Carpenter", "Window and door joinery install", "pending", "high", +6, +12,
             "Frames in; glazing crew follows.", None),
            (project6, "Plumber", "First fix plumbing — ground floor", "in_progress", "high", -12, +6,
             "Hot and cold to kitchen and two baths.", None),
            (project6, "Plumber", "Wasteflow and stormwater connections", "pending", "medium", +8, +14,
             "Council inspection booked mid-window.", None),
            (project6, "Electrician", "First fix wiring — ground floor", "in_progress", "high", -15, +8,
             "Cabling before plasterboard; smoke alarms looped.", None),
            (project6, "Electrician", "Switchboard install and CoC", "pending", "critical", +14, +16,
             "Energisation before walls close.", None),
            (project6, "Gib Stopper", "Install plasterboard — ground floor", "pending", "medium", +20, +27,
             "After inspections; 13mm ceilings throughout.", None),
            (project6, "Roofer", "Long-run roof install", "pending", "high", +7, +18,
             "Colour match to architect's spec, flashings first.", None),
            (project6, "Scaffolder", "Scaffold raise — gable end", "blocked", "medium", +2, +5,
             "Waiting on engineered tie detail for the gable.",
             "Engineer revising tie calculations."),
            (project6, "Site Carpenter", "Deck framing — rear elevation", "pending", "low", +30, +40,
             "Ground screws set out; hardwood deck to follow.", None),
            (project6, "Plumber", "Fit-off — bathrooms and kitchen", "pending", "medium", +34, +45,
             "After tiling; fixtures held in store.", None),
            (project6, "Electrician", "Fit-off — lighting and power", "pending", "medium", +36, +46,
             "Finals test and CoC sign-off at completion.", None),

            # ---------------- project7: Rata Street fit-out (completed)
            (project7, "Site Carpenter", "Bulkhead and stud partitions — ground floor", "completed", "high", -290, -260,
             "Tenancy layout per architect's plans.", None),
            (project7, "Electrician", "Power and data rough-in — all levels", "completed", "high", -230, -190,
             "Data cabling tested and labelled.", None),
            (project7, "Site Carpenter", "Reception joinery install", "completed", "medium", -160, -140,
             "Custom oak front delivered and fitted.", None),
            (project7, "Tiler", "Floor tiling — lobby and wet areas", "completed", "medium", -170, -145,
             "Large format tiles, lippage checked.", None),
            (project7, "Painter", "Full interior paint — all levels", "completed", "medium", -150, -120,
             "Low-VOC system, two coats.", None),
            (project7, "Cabinetmaker", "Kitchen and kitchenette fit-out", "completed", "high", -125, -95,
             "Stone tops templated post-install.", None),
            (project7, "Electrician", "Emergency and exit lighting test", "completed", "medium", -80, -74,
             "Commissioning test done at handover.", None),
            (project7, "Plumber", "Fixtures and fit-off — all levels", "completed", "medium", -110, -88,
             "Taps, WC and basins commissioned.", None),
            (project7, "Painter", "Touch-ups after joinery", "completed", "low", -75, -70,
             "Snag list closed pre-handover.", None),
            (project7, "Site Carpenter", "Defect rectification walk — punch list", "completed", "medium", -70, -62,
             "All items signed off by facilities manager.", None),

            # ---------------- project8: Wharf Road (active, early stage)
            (project8, "Concrete Crew", "Slab pour — both units", "completed", "critical", -14, -12,
             "Pumped pour, cured before frame delivery.", None),
            (project8, "Scaffolder", "Perimeter scaffold and edge protection", "completed", "medium", -5, -3,
             "Tagged, inspection register current.", None),
            (project8, "Site Carpenter", "Frame — Unit 1 ground floor", "in_progress", "critical", -8, +3,
             "Walls standing; bracing inspection booked.", None),
            (project8, "Site Carpenter", "Frame — Unit 2 ground floor", "in_progress", "high", -4, +8,
             "Set out behind Unit 1 crew.", None),
            (project8, "Site Carpenter", "First floor joists — Unit 1", "pending", "high", +4, +10,
             "After ground-floor frame sign-off.", None),
            (project8, "Plumber", "Under-slab drainage pressure test", "pending", "high", +3, +5,
             "Council witness required before backfill.", None),
            (project8, "Plumber", "First fix plumbing — Unit 1", "pending", "medium", +9, +20,
             "Rough-in behind frame as walls close.", None),
            (project8, "Electrician", "Site power upgrade — permanent feed", "pending", "medium", +6, +12,
             "Meter install coordinated with provider.", None),
            (project8, "Electrician", "First fix wiring — Unit 1", "pending", "high", +12, +25,
             "Cable through frame; coordinate with plumber.", None),
            (project8, "Concrete Crew", "Driveway and path pour", "pending", "low", +45, +55,
             "At end of programme after trades demob.", None),
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

            # project1 — extra *closed* history (the 6 active flagship defects stay as-is)
            Defect(task_id=tasks["Stormwater connections"].id,
                   title="Gully trap grate proud of finish level",
                   description="Grate sat 8mm high after paving; reset on mortar bed and re-tested.",
                   severity=DefectSeverity.LOW, status=DefectStatus.CLOSED, reported_by_id=dave.id,
                   created_at=dt(7, 9, 40), resolved_at=dt(5, 14, 15)),
            Defect(task_id=tasks["Scaffold inspect and handover — roof zone"].id,
                   title="Scaffold tag expired on east ladder bay",
                   description="Weekly inspection lapsed over the long weekend; inspected and tag replaced.",
                   severity=DefectSeverity.MEDIUM, status=DefectStatus.RESOLVED, reported_by_id=dave.id,
                   created_at=dt(6, 7, 25), resolved_at=dt(6, 11, 5)),

            # project2 — more of the live defect mix
            Defect(task_id=tasks["Frame and truss — Unit A"].id,
                   title="Brace spacing short at stair opening",
                   description="Two bays at the stair void braced at 3.5m instead of 3.0m; extra strap to be fixed.",
                   severity=DefectSeverity.HIGH, status=DefectStatus.OPEN, reported_by_id=aroha.id, created_at=dt(4, 8, 10)),
            Defect(task_id=tasks["First fix plumbing — Unit A"].id,
                   title="Hot water loop crosses joist without grommet",
                   description="Pipe passes through a joist web with no sleeve; core drill and grommet required.",
                   severity=DefectSeverity.MEDIUM, status=DefectStatus.OPEN, reported_by_id=aroha.id, created_at=dt(5, 10, 35)),
            Defect(task_id=tasks["First fix wiring — Unit A"].id,
                   title="Switch drops out of position at kitchen bench",
                   description="Three drops 40mm low against the cabinetry set-out; re-pull before gib closes.",
                   severity=DefectSeverity.MEDIUM, status=DefectStatus.IN_PROGRESS, reported_by_id=priya_s.id, created_at=dt(6, 13, 15)),
            Defect(task_id=tasks["Slab pour — Unit A"].id,
                   title="Sawn joint at garage threshold sealed",
                   description="Joint re-cut and sealed to spec; photos filed for the job pack.",
                   severity=DefectSeverity.LOW, status=DefectStatus.CLOSED, reported_by_id=aroha.id,
                   created_at=dt(26, 9, 20), resolved_at=dt(24, 15, 30)),

            # project3 — completed build: more closed trail
            Defect(task_id=tasks["Full reroof — Units 1-4"].id,
                   title="Spouting bracket spacing flagged at inspection",
                   description="Three brackets at 1.1m instead of 900mm; reset and signed off by the inspector.",
                   severity=DefectSeverity.MEDIUM, status=DefectStatus.CLOSED, reported_by_id=steve.id,
                   created_at=dt(45, 8, 5), resolved_at=dt(40, 16, 20)),
            Defect(task_id=tasks["Kitchen and kitchenette fit-out"].id,
                   title="Door reveal proud on pantry unit",
                   description="Reveals packed and re-hung to align with the benchtop shadow line.",
                   severity=DefectSeverity.LOW, status=DefectStatus.CLOSED, reported_by_id=steve.id,
                   created_at=dt(120, 11, 30), resolved_at=dt(115, 14, 10)),

            # project5 — paused build: the claim keeps growing
            Defect(task_id=tasks["Reinstate parapet capping"].id,
                   title="Parapet flashing corroded at valley",
                   description="Capping and step flashing surface-corroded; replace with like-for-like on remediation.",
                   severity=DefectSeverity.MEDIUM, status=DefectStatus.OPEN, reported_by_id=lena_s.id, created_at=dt(9, 7, 50)),
            Defect(task_id=tasks["Half-scaffold maintain and inspect"].id,
                   title="Scaffold fuse board missing at west bay",
                   description="Board and toe board stripped during partial strike; refit before site reopens.",
                   severity=DefectSeverity.MEDIUM, status=DefectStatus.IN_PROGRESS, reported_by_id=lena_s.id, created_at=dt(12, 8, 25)),

            # project6 — Kauri Lane: live defect mix on the active build
            Defect(task_id=tasks["Frame and truss — first floor"].id,
                   title="Truss nail plate lift on bottom chord",
                   description="Two plates not fully seated on truss T-7; hydraulic press tool requested by supplier.",
                   severity=DefectSeverity.CRITICAL, status=DefectStatus.OPEN, reported_by_id=tui.id, created_at=dt(4, 7, 40)),
            Defect(task_id=tasks["Frame and truss — first floor"].id,
                   title="Wall frame out of plumb at stair void",
                   description="12mm over 3m at the stair void; re-plumb and re-brace before joists land.",
                   severity=DefectSeverity.HIGH, status=DefectStatus.IN_PROGRESS, reported_by_id=tui.id, created_at=dt(5, 9, 55)),
            Defect(task_id=tasks["First fix plumbing — ground floor"].id,
                   title="Pipe penetrating fire wall without sleeve",
                   description="Kitchen cold line through the party wall needs a fire-rated sleeve and intumescent seal.",
                   severity=DefectSeverity.MEDIUM, status=DefectStatus.OPEN, reported_by_id=tui.id, created_at=dt(7, 11, 15)),
            Defect(task_id=tasks["Foundations and pile caps"].id,
                   title="Pile cap datum 10mm low — packed to spec",
                   description="Cap at grid C4 poured low; engineer accepted shimming detail, poured and re-tested.",
                   severity=DefectSeverity.LOW, status=DefectStatus.RESOLVED, reported_by_id=tui.id,
                   created_at=dt(15, 10, 45), resolved_at=dt(12, 13, 0)),

            # project7 — completed fit-out: closed snag history
            Defect(task_id=tasks["Floor tiling — lobby and wet areas"].id,
                   title="Grout colour variation in lobby",
                   description="Two batches mixed in the same bay; regrouted the affected area, matched on cure.",
                   severity=DefectSeverity.LOW, status=DefectStatus.CLOSED, reported_by_id=james.id,
                   created_at=dt(95, 9, 25), resolved_at=dt(88, 15, 45)),
            Defect(task_id=tasks["Emergency and exit lighting test"].id,
                   title="Two exit signs failed lux test",
                   description="Drivers replaced with matching units; full re-test passed at 0.5 lux at floor level.",
                   severity=DefectSeverity.MEDIUM, status=DefectStatus.CLOSED, reported_by_id=james.id,
                   created_at=dt(70, 14, 5), resolved_at=dt(65, 10, 40)),

            # project8 — Wharf Road: fresh defects on the new active build
            Defect(task_id=tasks["Frame — Unit 1 ground floor"].id,
                   title="Bottom plate anchor spacing off at wet wall",
                   description="Anchors at 1.6m instead of 1.2m along the wet wall; added fixings today.",
                   severity=DefectSeverity.CRITICAL, status=DefectStatus.OPEN, reported_by_id=hana.id, created_at=dt(3, 8, 30)),
            Defect(task_id=tasks["Slab pour — both units"].id,
                   title="Surface laitance at garage bay",
                   description="Weak surface over ~2m² at the garage bay; bush-hammer and cure before covering.",
                   severity=DefectSeverity.MEDIUM, status=DefectStatus.OPEN, reported_by_id=hana.id, created_at=dt(6, 9, 10)),
            Defect(task_id=tasks["Perimeter scaffold and edge protection"].id,
                   title="Missing toe board on north run",
                   description="Toe board lifted for the material hoist and not replaced; refit before tomorrow's briefing.",
                   severity=DefectSeverity.LOW, status=DefectStatus.IN_PROGRESS, reported_by_id=hana.id, created_at=dt(5, 7, 55)),
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
