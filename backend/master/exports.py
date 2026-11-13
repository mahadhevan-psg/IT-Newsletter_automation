"""Column-by-column CSV downloads for the Submissions tab and the two Placements views.

Each download has a catalog of columns (key, label, part of the pop-up they are listed under). The portal shows the catalog as a tick-list,
the person picks the columns and the dates, and gets exactly those columns for the rows the page's filters select. Rows are always limited to what
the person may see (the same rules as the lists). Column expressions are written here, never taken from the request: the request only names keys.
"""
import csv
import io
from typing import Any, Dict, List

from fastapi import HTTPException

from backend.master import placements, submissions
from backend.master.auth import User
from backend.master.common import EFF_CLASS
from backend.master.works import EXPORT_LIMIT, _safe

FORM_NAMES = "CASE fs.form_type WHEN 'STUDENT' THEN 'Student achievement' WHEN 'RESEARCH' THEN 'Research & innovation' WHEN 'FACULTY' THEN 'Faculty achievement' WHEN 'DEPARTMENT' THEN 'Departmental highlight' WHEN 'OUTREACH' THEN 'Industry, alumni & outreach' ELSE fs.form_type END"


def _col(key, label, part, expr):
    return {"key": key, "label": label, "part": part, "expr": expr}


SUBMISSIONS = [
    _col("date", "Date", "Basics", "fs.event_date"), _col("form", "Form", "Basics", FORM_NAMES), _col("category", "Category", "Basics", "fs.category"),
    _col("title", "Title", "Basics", "fs.title"), _col("ay", "Academic year", "Basics", "fs.ay_id"),
    _col("submitted_by", "Submitted by (faculty)", "People", "u.full_name"), _col("submitter_emp_id", "Submitter employee ID", "People", "fs.submitter_emp_id"),
    _col("submitter_email", "Submitter e-mail", "People", "fs.submitter_email"),
    _col("students", "Students (roll numbers)", "People",
         "(SELECT GROUP_CONCAT(p.roll_no, '; ') FROM student_achievement_participants p WHERE p.submission_id = fs.submission_id AND p.roll_no IS NOT NULL)"),
    _col("event_students", "Event participants (roll numbers)", "People",
         "(SELECT GROUP_CONCAT(e.roll_no, '; ') FROM event_participants e WHERE e.submission_id = fs.submission_id)"),
    _col("faculty", "Faculty involved", "People",
         "(SELECT GROUP_CONCAT(f.full_name, '; ') FROM submission_faculty sf JOIN faculty f ON f.emp_id = sf.emp_id WHERE sf.submission_id = fs.submission_id)"),
    _col("evidence_url", "Evidence link", "Links", "fs.evidence_url"), _col("media_url", "Photo link", "Links", "fs.media_url"),
    _col("photo_caption", "Photo caption", "Links", "fs.photo_caption"), _col("submitted_at", "Submitted on", "Submission", "fs.submitted_at"),
]
OFFERS = [
    _col("roll_no", "Roll no", "Student", "s.roll_no"), _col("name", "Student name", "Student", "s.full_name"), _col("class", "Class", "Student", "c.class_code"),
    _col("programme", "Programme", "Student", "c.programme"), _col("ay", "Academic year", "Offer", "o.ay_id"), _col("company", "Company", "Offer", "g.name"),
    _col("offer_type", "Offer type", "Offer", "o.offer_type"), _col("status", "Offer status", "Offer", "o.offer_status"), _col("role", "Job role", "Offer", "o.job_role"),
    _col("location", "Work location", "Offer", "o.work_location"), _col("offer_date", "Offer date", "Offer", "o.offer_date"),
    _col("campus", "Campus drive", "Offer", "CASE o.is_on_campus WHEN 1 THEN 'On-campus' WHEN 0 THEN 'Off-campus' END"),
    _col("package", "Package (LPA)", "Money", "o.package_lpa"), _col("stipend", "Stipend per month (₹)", "Money", "o.stipend_per_month"),
]
PROFILES = [
    _col("roll_no", "Roll no", "Student", "s.roll_no"), _col("name", "Student name", "Student", "s.full_name"), _col("class", "Class", "Student", "c.class_code"),
    _col("programme", "Programme", "Student", "c.programme"), _col("ay", "Academic year", "Placement", "p.ay_id"),
    _col("opt", "Preference", "Placement", "CASE p.opt_status WHEN 'OPTED_IN' THEN 'Opted in' ELSE 'Opted out' END"), _col("reason", "Reason for opting out", "Placement", "p.opt_out_reason"),
    _col("offers", "Accepted offers", "Placement", "(SELECT COUNT(*) FROM placement_offers o WHERE o.roll_no = p.roll_no AND o.ay_id = p.ay_id AND o.offer_status = 'Accepted')"),
    _col("best", "Best package (LPA)", "Placement", "(SELECT MAX(package_lpa) FROM placement_offers o WHERE o.roll_no = p.roll_no AND o.ay_id = p.ay_id AND o.offer_status = 'Accepted')"),
]
# name -> (columns, default keys, query-builder, ordering, file name)
KINDS: Dict[str, Dict[str, Any]] = {
    "submissions": {"columns": SUBMISSIONS, "default": ["date", "form", "category", "title", "submitted_by"], "base": submissions._base,
                    "order": "fs.event_date DESC, fs.submission_id DESC", "parts": ["Basics", "People", "Links", "Submission"]},
    "offers": {"columns": OFFERS, "default": ["roll_no", "name", "class", "ay", "company", "offer_type", "package"], "base": placements._offers_base,
               "order": "o.ay_id DESC, g.name, s.roll_no", "parts": ["Student", "Offer", "Money"]},
    "profiles": {"columns": PROFILES, "default": ["roll_no", "name", "class", "ay", "opt", "offers", "best"], "base": placements._profiles_base,
                 "order": "p.ay_id DESC, c.class_code, s.roll_no", "parts": ["Student", "Placement"]},
}


def _kind(name: str) -> Dict[str, Any]:
    if name not in KINDS:
        raise HTTPException(404, "Unknown download")
    return KINDS[name]


def catalog(name: str) -> Dict[str, Any]:
    k = _kind(name)
    return {"columns": [{c: col[c] for c in ("key", "label", "part")} for col in k["columns"]], "default_columns": k["default"], "parts": k["parts"]}


def export_csv(conn, user: User, name: str, f: Dict[str, Any], columns: List[str]) -> bytes:
    k = _kind(name)
    by_key = {c["key"]: c for c in k["columns"]}
    bad = [c for c in columns if c not in by_key]
    if bad or not columns:
        raise HTTPException(400, "Choose at least one column" if not columns else "Unknown column: " + ", ".join(bad))
    base, args = k["base"](user, f)
    chosen = list(dict.fromkeys(columns))
    sql = f"SELECT {', '.join(by_key[c]['expr'] for c in chosen)} {base} ORDER BY {k['order']} LIMIT {EXPORT_LIMIT}"
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([by_key[c]["label"] for c in chosen])
    for row in conn.execute(sql, args):
        w.writerow([_safe(v) for v in row])
    return ("﻿" + buf.getvalue()).encode("utf-8")
