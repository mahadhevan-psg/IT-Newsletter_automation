"""A fixed set of demo entries that are waiting for approval when the demo starts."""
import random
import threading
from datetime import date, datetime, timedelta
from typing import Dict, List

from backend.demo import data as D

TOTAL = 14                       # responses each pretend sheet will hold in the end
INITIAL = {"form_student": 6, "form_research": 4, "form_faculty": 3, "form_departmental": 3, "form_industry": 3, "placement": 4}
_lock = threading.Lock()
_released: Dict[str, int] = {}


def reset() -> None:
    with _lock:
        _released.clear()
        _cache.clear()


_pool: Dict[str, list] = {}


def prime(conn) -> None:
    """Who exists in the demo department (read through the seeding connection, whose rows are not yet visible to others)."""
    q = lambda sql: [r[0] for r in conn.execute(sql)]
    _pool["rolls"] = q("SELECT roll_no FROM students WHERE status = 'Active' ORDER BY roll_no")
    _pool["tutor_rolls"] = q("SELECT roll_no FROM students WHERE status = 'Active' AND class_id = 3 ORDER BY roll_no")
    _cache.clear()


def _people():
    if not _pool:                                              # the server restarted since the demo was seeded
        from database.master_db import db
        with db() as conn:
            prime(conn)
    return _pool["rolls"], [f[0] for f in D.FACULTY]


def _stamp(i: int) -> str:
    return (datetime.now().replace(hour=9, minute=0, second=0, microsecond=0) - timedelta(days=TOTAL - i // 3, minutes=-7 * i)).strftime("%Y-%m-%d %H:%M:%S")


def _raw(form_id: str, i: int, email: str, **keys) -> Dict[str, str]:
    from backend.demo.seed import _heads
    heads = _heads(form_id, keys.get("category"))
    raw = {"Timestamp": _stamp(i), "Email Address": email}
    for k, v in keys.items():
        if v not in (None, "") and k in heads:
            raw[heads[k]] = str(v)
    return raw


def _build(form_id: str) -> List[Dict[str, str]]:
    from backend.demo.seed import _choice, _fac_email
    from backend.master.profiles import _categories
    r = random.Random(f"sheet-{form_id}")
    rolls, fac = _people()
    cats = _categories(form_id) if form_id != "placement" else []
    out: List[Dict[str, str]] = []
    for i in range(TOTAL):
        when = date.today() - timedelta(days=r.randint(3, 40))
        if form_id == "form_student":
            team = r.sample(rolls, r.choice([1, 1, 2, 3]))
            if i % 7 == 3:
                team[-1] = "99ITZ99"                                   # a roll number that does not exist: the approver sees it flagged
            mentor = r.choice(fac)
            ev, org = r.choice(D.HACKATHONS)
            k = dict(entry_kind=_choice(form_id, "entry_kind", "Achievement"), _participants="\n".join(team), category="Hackathons / Coding Competitions",
                     title=f"{ev} {when.year}", organizer=org, level=_choice(form_id, "level", r.choice(["State", "National"])), position=r.choice(D.POSITIONS_WIN),
                     result_date=when.isoformat(), mentor_emp_id=mentor, abstract="The team built a working prototype in under 48 hours.")
            out.append(_raw(form_id, i, _fac_email(mentor), **k))
        elif form_id == "form_research":
            lead = r.choice(fac)
            v, idx = r.choice(D.JOURNALS)
            k = dict(_submitter=lead, category=cats[0], title=f"{r.choice(D.APPROACHES)} Model for {r.choice(D.APPLICATIONS).title()}", _contributors="\n".join(r.sample(fac, 1)),
                     output_date=when.isoformat(), venue_publisher=v, indexing=_choice(form_id, "indexing", idx.split()[0], cats[0]), quartile="Q2", impact_factor=round(r.uniform(1.5, 7), 1),
                     identifier=f"10.{r.randint(1000, 1109)}/{v.split()[0].lower()}.{when.year}.{r.randint(100000, 999999)}")
            if i % 5 == 1:
                k["identifier"] = ""                                    # something missing worth a look
            out.append(_raw(form_id, i, _fac_email(lead), **k))
        elif form_id == "form_faculty":
            emp = r.choice(fac)
            k = dict(emp_id=emp, category=cats[0], title=r.choice(D.AWARDS), host_org=r.choice(D.AWARD_BODIES), level=r.choice(["State", "National"]),
                     city_venue=f"{when.strftime('%d %B %Y')}, Coimbatore", description="Recognised for contributions to teaching and research.")
            out.append(_raw(form_id, i, _fac_email(emp), **k))
        elif form_id == "form_departmental":
            conv = r.choice(fac)
            k = dict(_submitter=conv, category=cats[1], title=r.choice(D.WORKSHOPS), venue=f"{when.strftime('%d %B %Y')}, IT Department Seminar Hall",
                     participant_count=r.choice([40, 65, 90]), overview="A hands-on programme with practical sessions.", budget_amount=20000, funding_source="Department fund")
            out.append(_raw(form_id, i, _fac_email(conv), **k))
        elif form_id == "form_industry":
            lead = r.choice(fac)
            partner = r.choice(D.PARTNERS[:-1])[0]
            k = dict(_submitter=lead, category=cats[0], _partner=partner, start_date=when.isoformat(), venue="Partner campus", target_audience="Second and third year students",
                     actual_count=r.choice([48, 55, 70]), title=f"Industrial visit to {partner}", objective="Students toured the facility and met the engineering teams.")
            out.append(_raw(form_id, i, _fac_email(lead), **k))
        else:                                                           # placement: one student's diary row, in the Excel template's column order
            from backend.master import placements
            company, _sector, (lo, hi), _w, roles, _stipend = D.COMPANIES[i % len(D.COMPANIES)]
            cohort = _pool["tutor_rolls"]                                           # the demo tutor's class
            roll = cohort[(i * 5) % len(cohort)]
            vals = placements.example_row()
            heads = placements.template_headers()
            row = dict(zip(heads, vals))
            row[heads[0]] = roll
            for h in heads:
                lh = h.lower()
                if "company" in lh or "organisation" in lh or "organization" in lh:
                    row[h] = company
                elif "package" in lh:
                    row[h] = str(round(r.uniform(lo, hi), 1))
                elif "role" in lh:
                    row[h] = r.choice(roles)
                elif "date" in lh and "offer" in lh:
                    row[h] = when.isoformat()
            row["Timestamp"] = _stamp(i)
            out.append(row)
    return out


_cache: Dict[str, List[Dict[str, str]]] = {}


def _all(form_id: str) -> List[Dict[str, str]]:
    if form_id not in _cache:
        _cache[form_id] = _build(form_id)
    return _cache[form_id]


def initial(form_id: str) -> List[Dict[str, str]]:
    """The responses already in the sheet when the demo starts (seeding uses this; it is not a pull)."""
    with _lock:
        _released[form_id] = INITIAL.get(form_id, 3)
        return [dict(x) for x in _all(form_id)[:_released[form_id]]]
