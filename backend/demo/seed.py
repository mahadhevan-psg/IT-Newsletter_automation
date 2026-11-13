"""Demo mode: fills the application with a realistic, entirely invented department and keeps it tidy.

    start()   called at server start-up when DEMO_MODE=true: seeds once, then resets itself on a timer
    reset()   wipe and rebuild (also available as POST /api/demo/reset, rate limited)

The data goes through the same importer the real uploads use, so profiles, the by-work view, the diary and the newsletter
studio all have something meaningful to show. Nothing here describes real people.
"""
import json
import os
import random
import shutil
import threading
import time
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from backend.demo import data as D
from backend.demo.mode import PASSWORD, enabled, reset_hours
from backend.master import ingest
from backend.master.auth import hash_password, set_staff_password
from backend.master.profiles import _categories
from database.master_db import audit, ay_for, db, ensure_ay, init_master_db

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFAULTS = os.path.join(ROOT, "config.default")          # copy of the shipped settings, made when the image is built
MUTABLE_CONFIG = ("form_mappings.json", "section_categories.json", "section_layouts.json", "front_matter.json")
_lock = threading.Lock()
_state: Dict[str, Any] = {"last_reset": None, "last_manual": 0.0, "thread": None}
ISSUE_ID = "ISSUE_2026_V1I1"


class DemoRefused(RuntimeError):
    pass


# ---------------------------------------------------------------- safety
def ensure_safe(conn):
    """DEMO_MODE wipes and rebuilds the database. Never let it near real data: only a database that is empty, or that this
    module created earlier (it carries a marker), may be reset."""
    conn.execute("CREATE TABLE IF NOT EXISTS demo_state (id INTEGER PRIMARY KEY CHECK (id = 1), seeded_at TEXT NOT NULL)")
    marked = conn.execute("SELECT 1 FROM demo_state").fetchone()
    if marked:
        return
    people = conn.execute("SELECT (SELECT COUNT(*) FROM faculty WHERE emp_id != 'ADMIN') + (SELECT COUNT(*) FROM students) "
                          "+ (SELECT COUNT(*) FROM form_submissions)").fetchone()[0]
    if people:
        raise DemoRefused("DEMO_MODE is switched on but this database already holds real data (students, faculty or submissions). "
                          "Refusing to wipe it. Use a separate service and an empty disk for the demo.")


# ---------------------------------------------------------------- helpers to build form rows
_titles: Dict[str, Dict[str, str]] = {}


def _heads(form_id: str) -> Dict[str, str]:
    if form_id not in _titles:
        _titles[form_id] = {q["key"]: q["q"] for q in ingest.specs()["forms"][form_id]["questions"] if q.get("key")}
    return _titles[form_id]


def _choice(form_id: str, key: str, starts: str) -> str:
    for q in ingest.specs()["forms"][form_id]["questions"]:
        if q.get("key") == key:
            return next((c for c in q.get("choices", []) if c.lower().startswith(starts.lower())), starts)
    return starts


def _row(form_id: str, when: date, email: str, **keys) -> Dict[str, str]:
    ts = min(when + timedelta(days=_R.randint(1, 12)), date.today())
    raw = {"Timestamp": f"{ts.isoformat()} {_R.randint(9, 17):02d}:{_R.randint(0, 59):02d}:00", "Email Address": email}
    heads = _heads(form_id)
    for k, v in keys.items():
        if v not in (None, ""):
            raw[heads[k]] = str(v)
    return raw


_R = random.Random(2026)


def _rdate(a: date, b: date) -> date:
    return a + timedelta(days=_R.randint(0, max(0, (b - a).days)))


def _fac_email(emp: str) -> str:
    return f"{emp.lower()}@demo.example.edu"


class Cohort:
    """One class of students and the dates in which things can have happened to them."""
    def __init__(self, class_id, rolls, start, end, final_year, programme, grp):
        self.class_id, self.rolls, self.start, self.end, self.final, self.programme, self.grp = class_id, rolls, start, end, final_year, programme, grp


# ---------------------------------------------------------------- wipe
def _wipe_master(conn):
    conn.execute("PRAGMA foreign_keys = OFF")
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' AND name != 'demo_state'")]
    for t in tables:
        conn.execute(f"DELETE FROM {t}")
    conn.execute("DELETE FROM sqlite_sequence")
    conn.execute("PRAGMA foreign_keys = ON")


def _wipe_newsletter():
    from database.db_manager import get_connection
    c = get_connection()
    try:
        for t in ("canonical_entries", "raw_responses", "generations", "audit_logs", "visual_templates"):
            c.execute(f"DELETE FROM {t}")
        c.commit()
    finally:
        c.close()


def _restore_settings():
    """Visitors can edit forms, layouts and front pages in the studio: put the shipped settings back (only inside the image)."""
    if not os.path.isdir(DEFAULTS):
        return
    for name in MUTABLE_CONFIG:
        src, dst = os.path.join(DEFAULTS, name), os.path.join(ROOT, "config", name)
        if os.path.exists(src):
            shutil.copyfile(src, dst)
        elif os.path.exists(dst):
            os.remove(dst)
    out = os.path.join(ROOT, "output")
    if os.path.isdir(out):
        for entry in os.listdir(out):
            p = os.path.join(out, entry)
            shutil.rmtree(p, ignore_errors=True) if os.path.isdir(p) else os.remove(p)


# ---------------------------------------------------------------- people, classes, students
def _seed_people(conn) -> List[Cohort]:
    today = date.today()
    a0 = int(ay_for(today)[:4])
    cur_ay = ay_for(today)
    for emp, name, desig, qual in D.FACULTY:
        conn.execute("INSERT INTO faculty (emp_id, full_name, email, designation, qualification, date_of_joining) VALUES (?,?,?,?,?,?)",
                     (emp, name, _fac_email(emp), desig, qual, f"{_R.randint(2004, 2023)}-{_R.randint(6, 8):02d}-01"))
        set_staff_password(conn, emp, PASSWORD)
    conn.execute("INSERT INTO role_assignments (emp_id, role) VALUES (?, 'HOD')", (D.HOD,))
    for emp, prog, grp in D.COORDINATORS:
        conn.execute("INSERT INTO role_assignments (emp_id, role, programme, grp) VALUES (?, 'PC', ?, ?)", (emp, prog, grp))
    conn.execute("UPDATE users SET must_change = 0")                   # shared demo logins: nobody is asked to change a password

    used, cohorts = set(), []
    classes = conn.execute("SELECT class_id, class_code, programme, grp, year_no FROM classes ORDER BY class_id").fetchall()

    def student_name():
        while True:
            n = f"{_R.choice(D.FEMALE + D.MALE)} {_R.choice(D.SURNAMES)}"
            if n not in used:
                used.add(n)
                return n

    def add_students(class_id, programme, grp, admission, count, status, graduation=None):
        yy = admission % 100
        rolls = []
        for i in range(1, count + 1):
            roll = f"{yy}IT{'A' if grp == 'G1' else 'B'}{i:02d}" if programme == "UG" else f"{yy}MIT{i:02d}"
            conn.execute("INSERT INTO students (roll_no, full_name, programme, class_id, status) VALUES (?,?,?,?,?)",
                         (roll, student_name(), programme, class_id if status == "Active" else None, status))
            joined = date(admission, 8, 1).isoformat()
            if status == "Active":
                conn.execute("INSERT INTO student_class_history (roll_no, class_id, from_date, action) VALUES (?,?,?,'Added')", (roll, class_id, joined))
            else:
                conn.execute("INSERT INTO student_class_history (roll_no, class_id, from_date, to_date, action) VALUES (?,?,?,?,'Added')", (roll, class_id, joined, graduation.isoformat()))
                conn.execute("INSERT INTO student_class_history (roll_no, class_id, from_date, to_date, action) VALUES (?,NULL,?,?,'Graduated')", (roll, graduation.isoformat(), graduation.isoformat()))
            rolls.append(roll)
        return rolls

    for i, c in enumerate(classes):
        tutor = D.TUTORS[i]
        conn.execute("UPDATE classes SET tutor_id = ?, ay_id = ? WHERE class_id = ?", (tutor, cur_ay, c["class_id"]))
        conn.execute("INSERT INTO class_tutor_history (class_id, tutor_id, from_date) VALUES (?,?,?)", (c["class_id"], tutor, f"{a0}-06-01"))
        conn.execute("INSERT INTO class_term_history (class_id, ay_id, semester_no, changed_by) VALUES (?,?,?,?)", (c["class_id"], cur_ay, c["year_no"] * 2 - 1, tutor))
        admission = a0 - (c["year_no"] - 1)
        rolls = add_students(c["class_id"], c["programme"], c["grp"], admission, 18 if c["programme"] == "PG" else 28, "Active")
        cohorts.append(Cohort(c["class_id"], rolls, date(admission, 8, 15), today, c["year_no"] == (2 if c["programme"] == "PG" else 4), c["programme"], c["grp"]))

    # two earlier batches that have already graduated: their placements fill the diary's three-year window
    from backend.master import people
    for back, grp in ((2, "G1"), (1, "G2")):
        grad_ay = ensure_ay(conn, f"{a0 - back}-{(a0 - back + 1) % 100:02d}")
        code = people.next_class_code(conn, "UG", grp, 8)
        cid = conn.execute("INSERT INTO classes (class_code, programme, grp, year_no, current_semester, ay_id, tutor_id, status) VALUES (?,?,?,?,?,?,NULL,'Completed')",
                           (code, "UG", grp, 4, 8, grad_ay)).lastrowid
        admission, graduation = a0 - back - 3, date(a0 - back + 1, 5, 31)
        rolls = add_students(cid, "UG", grp, admission, 30, "Graduated", graduation)
        cohorts.append(Cohort(cid, rolls, date(admission, 8, 15), graduation, True, "UG", grp))
    return cohorts


# ---------------------------------------------------------------- form submissions
def _submit(conn, form_id: str, row: Dict[str, str]) -> None:
    res = ingest.ingest_row(conn, form_id, row)
    if res["status"] == "error":
        raise RuntimeError(f"demo row rejected for {form_id}: {res['errors']}")


def _seed_submissions(conn, cohorts: List[Cohort]) -> None:
    today = date.today()
    lo, hi = today - timedelta(days=3 * 365), today - timedelta(days=4)
    fac = [f[0] for f in D.FACULTY]
    senior = [f[0] for f in D.FACULTY if "Professor" in f[2] and "Assistant" not in f[2]]
    all_rolls = [r for c in cohorts for r in c.rolls]
    final_rolls = [r for c in cohorts if c.final for r in c.rolls]
    yes, perm = _choice("form_research", "is_landmark", "Yes"), "Yes - may be published in the IT Chronicles newsletter"
    no_lm = _choice("form_research", "is_landmark", "No")
    lm = lambda p=0.08: yes if _R.random() < p else no_lm
    ext_line = lambda: "EXT - " + " - ".join(_R.choice(D.EXTERNAL_PEOPLE))

    # ---- research & innovation
    cats = _categories("form_research")
    for ci, count in enumerate([24, 20, 5, 9, 6, 9, 6]):
        cat = cats[ci]
        for n in range(count):
            lead = _R.choice(senior if _R.random() < .55 else fac)
            authors = [lead] + _R.sample([f for f in fac if f != lead], _R.choice([0, 1, 1, 2])) + _R.sample(final_rolls, _R.choice([0, 1, 2, 3]))
            if _R.random() < .3:
                authors.append(ext_line())
            when = _rdate(lo, hi)
            title = f"{_R.choice(D.APPROACHES)} {_R.choice(['Framework', 'Model', 'Approach', 'Architecture'])} for {_R.choice(D.APPLICATIONS).title()} Using {_R.choice(D.TOPICS).title()}"
            k: Dict[str, Any] = dict(_submitter=lead, category=cat, title=title, _contributors="\n".join(authors), output_date=when.isoformat(), is_landmark=lm(),
                                     publish_permission=perm, abstract=f"This work studies {_R.choice(D.TOPICS)} for {_R.choice(D.APPLICATIONS)} and reports measurable gains over strong baselines on a real dataset.",
                                     key_findings="Improved accuracy and lower cost than the existing approach.", impact="Ready to be piloted by the department and an industry partner.")
            if ci == 0:
                v, idx = _R.choice(D.JOURNALS)
                k.update(current_status=_R.choice(["Published"] * 4 + ["Accepted", "Under Review"]), venue_publisher=v, indexing=idx, quartile=_R.choice(["Q1", "Q2", "Q2", "Q3", "Q4"]) if idx != "UGC-CARE" else "Not applicable",
                         impact_factor=round(_R.uniform(1.4, 9.2), 1), review_status="Peer reviewed", identifier=f"10.{_R.randint(1000, 1109)}/{v.split()[0].lower()}.{when.year}.{_R.randint(100000, 999999)}",
                         funding_status="Not funded")
            elif ci == 1:
                k.update(current_status=_R.choice(["Published", "Published", "Accepted"]), venue_publisher=_R.choice(D.CONFERENCES), indexing=_R.choice(["Scopus", "IEEE Xplore", "Not indexed"]),
                         conference_level=_R.choice(["International", "International", "National"]), review_status="Peer reviewed", quartile="Not applicable")
            elif ci == 2:
                k.update(current_status="Published", venue_publisher=_R.choice(D.PUBLISHERS), identifier=f"978-{_R.randint(81, 93)}-{_R.randint(1000, 9999)}-{_R.randint(100, 999)}-{_R.randint(0, 9)}", indexing="Not applicable")
            elif ci == 3:
                k.update(current_status=_R.choice(["Ongoing", "Ongoing", "Completed"]), venue_publisher=_R.choice(D.AGENCIES), funding_status="Funded", funding_amount=_R.choice([3, 5, 7.5, 12, 18, 25, 40]) * 100000,
                         project_start=(when - timedelta(days=_R.randint(200, 700))).isoformat(), collaborators=_R.choice(D.INSTITUTIONS), identifier=f"SERB/F/{_R.randint(1000, 9999)}/{when.year}")
            elif ci == 4:
                k.update(current_status=_R.choice(["Completed", "Ongoing"]), venue_publisher=_R.choice(D.CLIENTS), funding_status="Funded", funding_amount=_R.choice([0.5, 1, 2, 3.5, 6, 9]) * 100000)
            elif ci == 5:
                k.update(current_status=_R.choice(["Filed", "Filed", "Granted"]), venue_publisher="Indian Patent Office", identifier=f"{when.year}41{_R.randint(100000, 999999)}", ip_status="Filed jointly with the institution")
            else:
                k.update(current_status="Completed", venue_publisher="Department Innovation Cell", ip_status="Open source release")
            _submit(conn, "form_research", _row("form_research", when, _fac_email(lead), **k))

    # ---- faculty achievements
    cats = _categories("form_faculty")
    recog = ["Award", "Certification", "Invited lecture / Keynote", "Resource person / Session chair", "FDP / Workshop attended", "Editorial / Reviewer role"]
    for ci, count in enumerate([12, 14, 12, 8, 14, 8]):
        for n in range(count):
            emp = fac[(ci * 7 + n * 3) % len(fac)]
            when = _rdate(lo, hi)
            title, host, hours = {
                0: (_R.choice(D.AWARDS), _R.choice(D.AWARD_BODIES), None), 1: (_R.choice(D.CERTIFICATIONS), "NPTEL / Industry certification body", _R.choice([40, 60, 120])),
                2: (f"Keynote: {_R.choice(D.TALKS)}", _R.choice(D.INSTITUTIONS), 2), 3: (f"Resource person: {_R.choice(D.TALKS)}", _R.choice(D.INSTITUTIONS), _R.choice([3, 6])),
                4: (f"FDP: {_R.choice(D.FDP_TOPICS)}", _R.choice(D.INSTITUTIONS), _R.choice([30, 40])), 5: (_R.choice(D.PROFESSIONAL_ROLES), "Professional body", None)}[ci]
            k = dict(emp_id=emp, category=cats[ci], title=title, recognition_type=recog[ci], host_org=host, level=_R.choice(["State", "National", "National", "International", "College"]),
                     start_date=when.isoformat(), end_date=(when + timedelta(days=int(hours // 6) if hours and hours >= 30 else 0)).isoformat(), city_venue=_R.choice(["Coimbatore", "Chennai", "Madurai", "Online"]),
                     duration_hours=hours, description=f"{title} - recognised for contributions to teaching and research in the department.", outcome_impact="Shared learnings with colleagues through an internal session.",
                     is_team="Individual", is_landmark=lm(), publish_permission=perm)
            _submit(conn, "form_faculty", _row("form_faculty", when, _fac_email(emp), **k))

    # ---- departmental highlights
    cats = _categories("form_departmental")
    for ci, count in enumerate([9, 4, 4, 6, 4]):
        for n in range(count):
            conv = _R.choice(fac)
            when = _rdate(lo, hi)
            title, over = {0: (_R.choice(D.WORKSHOPS), "A hands-on programme for students and faculty with practical sessions."), 1: (_R.choice(D.CONFERENCES_ORG), "Paper presentations, keynotes and a poster session."),
                           2: (D.INFRA[n % len(D.INFRA)][0] + " inaugurated", D.INFRA[n % len(D.INFRA)][1]), 3: (_R.choice(D.CLUBS), "Student-run activity supported by faculty coordinators."),
                           4: (_R.choice(D.MILESTONES), "A department-wide milestone shared with all stakeholders.")}[ci]
            k = dict(_submitter=conv, convener_emp_id=conv, _faculty_involved="\n".join(_R.sample([f for f in fac if f != conv], 2)), category=cats[ci], title=title,
                     highlight_type=["Event", "Event", "Infrastructure upgrade", "Student activity", "Milestone"][ci], start_date=when.isoformat(), end_date=(when + timedelta(days=_R.choice([0, 1, 2, 4]))).isoformat(),
                     impl_status="Completed", venue="IT Department Seminar Hall", target_audience="Students and faculty", participant_count=_R.choice([40, 65, 90, 120, 180, 250]),
                     overview=over, budget_amount=_R.choice([15000, 40000, 75000, 150000, 600000]) if ci in (0, 1, 2) else None, funding_source=_R.choice(["Department fund", "AICTE grant", "Alumni contribution"]),
                     is_landmark=lm(.12), publish_permission=perm)
            _submit(conn, "form_departmental", _row("form_departmental", when, _fac_email(conv), **k))

    # ---- industry, alumni and outreach (with student rosters and MoU dates spread over active / expiring / expired)
    cats = _categories("form_industry")
    mou_n = 0
    for ci, count in enumerate([8, 9, 8, 6, 5]):
        for n in range(count):
            lead = _R.choice(fac)
            when = _rdate(lo, hi)
            partner, ptype = D.PARTNERS[(ci * 3 + n) % len(D.PARTNERS)] if ci != 4 else D.PARTNERS[-1]
            roster = "\n".join(_R.sample(all_rolls, _R.choice([0, 15, 25, 40])))
            k = dict(_submitter=lead, lead_emp_id=lead, _faculty_involved="\n".join(_R.sample([f for f in fac if f != lead], 1)), category=cats[ci], _partner=partner, partner_type=ptype,
                     start_date=when.isoformat(), venue=_R.choice(["Partner campus", "IT Department Seminar Hall", "Online"]), target_audience="Second and third year students",
                     expected_count=_R.choice([40, 60, 100]), actual_count=_R.choice([32, 55, 90, 120]), _event_participants=roster, is_landmark=lm(), publish_permission=perm)
            if ci == 0:
                k.update(title=f"Industrial visit to {partner}", activity_format="Industrial visit", summary_outcomes=f"Students toured {_R.choice(D.VISIT_PLACES)} and met the engineering teams.")
            elif ci == 1:
                k.update(title=f"Expert talk: {_R.choice(D.OUTREACH_TALKS)}", activity_format="Guest lecture / Talk", speakers=f"Engineering lead, {partner}", summary_outcomes="An interactive session followed by a Q&A.")
            elif ci == 2:
                bucket = mou_n % 4                                                # active, active, expiring within 90 days, expired
                eff = today - timedelta(days={0: 400, 1: 700, 2: 1000, 3: 1200}[bucket])
                exp = {0: today + timedelta(days=700), 1: today + timedelta(days=380), 2: today + timedelta(days=_R.randint(25, 80)), 3: today - timedelta(days=_R.randint(20, 120))}[bucket]
                k.update(title=f"MoU with {partner}", activity_format="MoU / Partnership", mou_scope="Joint projects, internships, guest lectures and lab support for three years.", start_date=eff.isoformat(),
                         agreement_effective=eff.isoformat(), agreement_expiry=exp.isoformat(), summary_outcomes="Agreement signed in the presence of both leadership teams.", expected_count=None, actual_count=None, _event_participants="")
                when = eff
                mou_n += 1
            elif ci == 3:
                k.update(title=f"Alumni interaction with {partner}", activity_format="Alumni meet / Mentoring", partner_type="Alumni", _partner="Coimbatore Alumni Association",
                         summary_outcomes="Alumni shared career journeys and offered mentoring to final years.")
            else:
                k.update(title="Digital literacy camp for rural schools", activity_format="Community camp", _partner=partner, partner_type="NGO / Community", summary_outcomes="Students taught basic computing to school children.")
            _submit(conn, "form_industry", _row("form_industry", when, _fac_email(lead), **k))

    # ---- student achievements and participation
    cats = _categories("form_student")
    domains = {key: _choice("form_student", "domain", key) for key in ("AI", "Web", "Cyber", "IoT", "Cloud", "Algorithms", "Sports", "Cultural", "Data", "Other")}
    weights = [len(c.rolls) * max(1, (c.end - c.start).days) for c in cohorts]
    ach, part = _choice("form_student", "entry_kind", "Achievement"), _choice("form_student", "entry_kind", "Participation")
    tutor_of = {c.class_id: D.TUTORS[i] for i, c in enumerate(cohorts[:10])}
    for ci, count in enumerate([18, 34, 14, 30, 24]):
        made, guard = 0, 0
        while made < count and guard < 500:
            guard += 1
            c = _R.choices(cohorts, weights)[0]
            if ci == 2 and not c.final:
                continue
            size = _R.choice([2, 3, 4]) if ci in (1, 3) and _R.random() < .7 else 1
            team = _R.sample(c.rolls, size)
            lo_c, hi_c = max(c.start + timedelta(days=60), lo), min(c.end, hi)
            if hi_c <= lo_c:
                continue
            when = _rdate(lo_c, hi_c)
            participation = ci in (1, 3, 4) and _R.random() < .3
            mentor = tutor_of.get(c.class_id) or _R.choice(fac)
            level, prize = _R.choice(["College", "Inter-college", "State", "National", "National"]), None
            if ci == 0:
                ev, org = _R.choice(D.RANK_EVENTS)
                title, organizer, position, dom, level = f"University rank {_R.randint(1, 15)} - {ev}", org, f"Rank {_R.randint(1, 15)}", domains["Other"], "State"
            elif ci == 1:
                ev, org = _R.choice(D.HACKATHONS)
                title, organizer, position, dom = f"{ev} {when.year}", org, "Participated" if participation else _R.choice(D.POSITIONS_WIN), domains[_R.choice(["AI", "Web", "Cyber", "IoT", "Cloud", "Algorithms"])]
                prize = None if participation else _R.choice([10000, 25000, 50000, 100000])
            elif ci == 2:
                ev, org = _R.choice(D.HIGHER_ED)
                title, organizer, position, dom, level = ev, org, "Admitted", domains["Other"], "National"
            elif ci == 3:
                ev, org = _R.choice(D.PROJECT_EVENTS)
                title, organizer, position, dom = f"{_R.choice(D.PROJECT_TITLES)} ({ev})", org, "Participated" if participation else _R.choice(D.POSITIONS_WIN), domains[_R.choice(["AI", "Web", "IoT", "Data", "Cloud"])]
                prize = None if participation else _R.choice([5000, 10000, 20000])
            else:
                ev, org, kind = _R.choice(D.SPORTS)
                title, organizer, position, dom = ev, org, "Participated" if participation else _R.choice(D.POSITIONS_WIN[:5]), domains[kind]
            k = dict(entry_kind=part if participation else ach, _participants="\n".join(team), _lead_roll=team[0], is_team="Team" if size > 1 else "Individual", category=cats[ci], title=title,
                     organizer=organizer, level=level, position=position, prize_amount=prize, result_date=when.isoformat(), domain=dom, mentor_emp_id=mentor,
                     abstract=f"{title}: the team prepared for weeks, with guidance from the mentor.", tools_used=_R.choice(["Python, TensorFlow", "React, Node.js", "Java, Spring Boot", "Arduino, MQTT", "Flutter, Firebase"]) if ci in (1, 3) else None,
                     previously_reported="No", is_landmark=lm(.07), publish_permission=perm)
            _submit(conn, "form_student", _row("form_student", when, _fac_email(mentor), **k))
            made += 1


# ---------------------------------------------------------------- placements
def _seed_placements(conn, cohorts: List[Cohort]) -> None:
    today = date.today()
    a0 = int(ay_for(today)[:4])
    companies = {}
    for name, sector, *_ in D.COMPANIES:
        companies[name] = ingest.upsert_org(conn, name, sector=sector)
    pool = [c for c in D.COMPANIES for _ in range(c[3])]
    batches = [(cohorts[0 + 3], a0), (cohorts[7], a0), (cohorts[10], a0 - 2), (cohorts[11], a0 - 1)]      # current UG-G1-4, UG-G2-4 and the two graduated batches
    # cohorts[3] is UG-G1-4 and cohorts[7] UG-G2-4 (class order: G1 years 1-4, G2 years 1-4, PG 1-2)
    for cohort, ay_start in batches:
        ay = ensure_ay(conn, f"{ay_start}-{(ay_start + 1) % 100:02d}")
        current = ay_start == a0
        for roll in cohort.rolls:
            if _R.random() < .1:
                conn.execute("INSERT INTO placement_profiles (roll_no, ay_id, opt_status, opt_out_reason, updated_by) VALUES (?,?,'OPTED_OUT',?,?)", (roll, ay, _R.choice(D.OPT_OUT_REASONS), D.TUTORS[3]))
                continue
            conn.execute("INSERT INTO placement_profiles (roll_no, ay_id, opt_status, updated_by) VALUES (?,?,'OPTED_IN',?)", (roll, ay, D.TUTORS[3]))
            if _R.random() < (.55 if current else .9):                           # this year's season is still running
                name, sector, (lo_p, hi_p), _w, roles, stipend = _R.choice(pool)
                kind = _R.choices(["FTE", "FTE+INTERN", "INTERN_CONVERTED_FTE"], [70, 15, 15])[0]
                org, role, loc = companies[name], _R.choice(roles), _R.choice(D.LOCATIONS)
                odate = date(ay_start, 8, 15) + timedelta(days=_R.randint(0, 150 if not current else 70))
                pkg = round(_R.uniform(lo_p, hi_p), 1)

                def offer(otype, package, stip, status="Accepted", when=odate):
                    conn.execute("INSERT INTO placement_offers (roll_no, ay_id, org_id, offer_type, package_lpa, stipend_per_month, job_role, work_location, offer_date, offer_status, is_on_campus, updated_by) "
                                 "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (roll, ay, org, otype, package, stip, role, loc, when.isoformat(), status, 1 if _R.random() < .85 else 0, D.TUTORS[3]))
                if kind == "INTERN_CONVERTED_FTE":
                    offer("INTERN", None, stipend, when=odate - timedelta(days=150))
                    offer("INTERN_CONVERTED_FTE", pkg, None)
                elif kind == "FTE+INTERN":
                    offer("FTE+INTERN", pkg, stipend)
                else:
                    offer("FTE", pkg, None)
                share = 1 if _R.random() < .85 else 0
                if _R.random() < .45:
                    conn.execute("INSERT INTO interview_experiences (roll_no, ay_id, org_id, rounds_count, round_details, difficulty, questions_asked, result, experience, tips, is_shareable) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                                 (roll, ay, org, _R.choice([3, 3, 4, 5]), _R.choice(D.ROUND_DETAILS), _R.choice(D.DIFFICULTY), _R.choice(D.QUESTIONS), "Selected", _R.choice(D.INTERVIEW_TEXT), _R.choice(D.TIPS), share))
                if kind != "FTE" and _R.random() < .8:
                    conn.execute("INSERT INTO internship_experiences (roll_no, ay_id, org_id, duration, mode, role, tech_stack, work_summary, learnings, rating, experience, is_shareable) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                                 (roll, ay, org, _R.choice(["2 months", "6 months", "6 months"]), _R.choice(["Onsite", "Hybrid", "Remote"]), _R.choice(D.INTERN_ROLES), _R.choice(D.TECH), _R.choice(D.INTERN_WORK),
                                  _R.choice(D.INTERN_LEARN), _R.choice([3, 4, 4, 5, 5]), _R.choice(D.INTERN_TEXT), share))


# ---------------------------------------------------------------- approvals and data sync
def _seed_review(conn) -> None:
    """Pretend sheets, a few responses waiting for approval (some with problems), some already sent back to a faculty member, and a pull history."""
    from backend.demo import fake_sheets
    from backend.master.auth import load_user
    from backend.review import schedule, service
    fake_sheets.reset()
    fake_sheets.prime(conn)
    for src in schedule.SOURCES:
        conn.execute("INSERT INTO sync_sources (form_id, sheet_url) VALUES (?, ?)", (src, f"demo://{src}"))
        result = service.stage_rows(conn, src, fake_sheets.initial(src))
        conn.execute("UPDATE sync_sources SET last_pulled_at = CURRENT_TIMESTAMP, last_result = ? WHERE form_id = ?", (json.dumps({"rows": sum(result.values()), **result}), src))
    conn.execute("INSERT OR IGNORE INTO sync_settings (id) VALUES (1)")
    conn.execute("UPDATE sync_settings SET enabled = 1, mode = 'days', every_days = 2, hour = 2, minute = 0, timezone = 'Asia/Kolkata' WHERE id = 1")
    conn.execute("INSERT INTO sync_runs (trigger, actor, status, finished_at, summary_json) VALUES ('schedule', NULL, 'done', CURRENT_TIMESTAMP, ?)",
                 (json.dumps({"sources": {}, "new_or_updated": 0, "failed": [], "none_configured": False}),))
    hod = load_user(conn, D.HOD, "STAFF")
    pending = [dict(r) for r in conn.execute("SELECT item_id, form_id, submitter_emp_id FROM staged_items WHERE kind = 'FORM' AND status = 'PENDING' ORDER BY item_id")]
    # one research and one student response were already looked at and sent back to the person who entered them
    for it in [x for x in pending if x["form_id"] in ("form_research", "form_student") and x["submitter_emp_id"]][:2]:
        service.reject(conn, hod, it["item_id"], "Please check the details and the evidence link before this goes in.", it["submitter_emp_id"])
    for it in [x for x in pending if x["form_id"] == "form_faculty"][:1]:           # and one already approved
        service.approve(conn, hod, it["item_id"])


# ---------------------------------------------------------------- newsletter side
def _seed_newsletter() -> None:
    from backend.services import front_matter_service as fms
    from backend.services.front_matter_service import FrontMatterService
    from backend.services.master_sync import MasterSync
    if not os.path.isdir(DEFAULTS):
        # not inside the Docker image (someone is trying the demo on their own computer): keep the demo's front pages out of the
        # project's real config folder
        from database.master_db import db_path
        fms.CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(db_path())), "demo_front_matter.json")
    from database.db_manager import get_entries, update_entry_status
    FrontMatterService().save({
        "cover": {"photo": ""}, "hod": {"name": "Dr. S. Venkatesan", "designation": "Professor & Head", "message": D.HOD_MESSAGE, "photo": ""}, "vision": D.VISION, "mission": D.MISSION,
        "advisor": {"name": "Dr. R. Lakshmi Priya", "designation": "Faculty Advisor", "photo": ""},
        "students": [{"name": n, "year": y, "photo": ""} for n, y in (("Aarthi Krishnan", "IV Year"), ("Surya Natarajan", "IV Year"), ("Divya Iyer", "III Year"), ("Karthik Raman", "III Year"))]})
    MasterSync().sync(issue_id=ISSUE_ID)
    for n, e in enumerate(get_entries(issue_id=ISSUE_ID)):
        if n % 23 == 5:                                                                  # everything is in unless rejected: a few the editor left out
            update_entry_status(e["entry_id"], "Rejected", rejection_reason="Left out of this issue", performer="Demo")


# ---------------------------------------------------------------- orchestration
def _student_account(conn) -> Optional[str]:
    row = conn.execute("SELECT roll_no FROM students WHERE status = 'Active' AND class_id = 4 ORDER BY roll_no LIMIT 1").fetchone()
    return row[0] if row else None


def seed_all() -> Dict[str, int]:
    global _R
    _R = random.Random(2026)                                                              # the same department every time
    with db() as conn:
        _wipe_master(conn)
    _wipe_newsletter()
    _restore_settings()
    init_master_db()                                                                      # classes and the ADMIN login
    with db() as conn:
        conn.execute("UPDATE users SET password_hash = ?, must_change = 0 WHERE user_id = 'ADMIN'", (hash_password(PASSWORD),))
        cohorts = _seed_people(conn)
        _seed_submissions(conn, cohorts)
        _seed_placements(conn, cohorts)
        _seed_review(conn)
        roll = _student_account(conn)
        if roll:
            conn.execute("INSERT OR REPLACE INTO users (user_id, user_type, password_hash, must_change) VALUES (?, 'STUDENT', ?, 0)", (roll, hash_password(PASSWORD)))
        conn.execute("INSERT OR REPLACE INTO demo_state (id, seeded_at) VALUES (1, ?)", (datetime.now().isoformat(timespec="seconds"),))
        audit(conn, "demo", "SEED", "demo", None, "demo data created")
        counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("faculty", "students", "form_submissions", "placement_offers")}
    _seed_newsletter()
    _state["last_reset"] = time.time()
    return counts


def reset(manual: bool = False) -> Dict[str, int]:
    with _lock:
        counts = seed_all()
        if manual:
            _state["last_manual"] = time.time()
        return counts


def manual_reset_wait(cooldown: int = 300) -> int:
    """Seconds a visitor must still wait before they can reset the demo again (the button is public, so it is rate limited)."""
    return max(0, int(cooldown - (time.time() - _state["last_manual"])))


def _loop():
    while True:
        time.sleep(max(60, reset_hours() * 3600))
        try:
            reset()
            print("[demo] data reset on schedule")
        except Exception as e:                                                            # never let the timer thread die
            print("[demo] scheduled reset failed:", e)


def start() -> None:
    """Server start-up in demo mode."""
    os.environ.setdefault("MASTER_ADMIN_PASSWORD", PASSWORD)
    init_master_db()
    with db() as conn:
        ensure_safe(conn)                                  # raises (and so stops the server) if there is real data
        seeded = conn.execute("SELECT 1 FROM demo_state").fetchone()
    if not seeded:
        print("[demo] seeding the demo department ...")
        print("[demo] done:", reset())
    else:
        _state["last_reset"] = time.time()
    if not _state["thread"]:
        t = threading.Thread(target=_loop, name="demo-reset", daemon=True)
        t.start()
        _state["thread"] = t


ACCOUNTS = [
    ("ADMIN", "Admin", "Runs the system: faculty, roles, class tutors, uploads and every analytic."),
    (D.HOD, "Head of Department", "Sees everything, explores all work by type, opens the Newsletter studio."),
    ("EMP102", "Programme Coordinator (UG)", "Sees the classes of both groups, G1 and G2."),
    (D.TUTORS[2], "Class tutor", "Looks after one class: its students, semester and placements."),
    ("EMP115", "Faculty", "Has a personal page of papers, awards, events and students mentored."),
]


def info() -> Dict[str, Any]:
    with db() as conn:
        roll = _student_account(conn)
    accounts = [{"id": i, "role": r, "about": a} for i, r, a in ACCOUNTS]
    if roll:
        accounts.append({"id": roll, "role": "Student", "about": "Opens the Placements Diary: companies, packages and anonymous experiences."})
    last = _state["last_reset"]
    return {"enabled": True, "password": PASSWORD, "accounts": accounts, "reset_hours": reset_hours(),
            "next_reset_in_minutes": max(0, int(((last or time.time()) + reset_hours() * 3600 - time.time()) / 60))}
