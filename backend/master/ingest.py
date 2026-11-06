"""Turns one Google-Form response row (any of the 5 forms) into master-database records.

The questions, their master-DB columns and special handlers come from config/master_forms.json,
which is generated together with the Apps Scripts, so the form and the importer cannot drift apart.
"""
import hashlib
import json
import os
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from backend.master.common import (person_name, clean_cell, norm_header, org_key, parse_date, parse_datetime, parse_int,
                                   parse_lines, parse_num, read_xlsx, truthy)
from database.master_db import db, ay_for, ensure_ay

SPEC_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "config", "master_forms.json")
DETAIL_TABLE = {"STUDENT": "student_achievements", "RESEARCH": "research_outputs", "FACULTY": "faculty_achievements",
                "DEPARTMENT": "department_highlights", "OUTREACH": "outreach_activities"}
COMMON = {"category", "title", "evidence_url", "media_url", "photo_caption", "badge_tag", "is_landmark", "publish_permission",
          "authorization_confirmed"}
BOOL_KEYS = {"is_team", "previously_reported"}

_spec_cache = {"mtime": None, "data": {}}


def specs() -> Dict[str, Any]:
    mtime = os.path.getmtime(SPEC_PATH)
    if _spec_cache["mtime"] != mtime:
        with open(SPEC_PATH, encoding="utf-8") as f:
            _spec_cache.update(mtime=mtime, data=json.load(f))
    return _spec_cache["data"]


def form_ids() -> List[str]:
    return list(specs()["forms"].keys())


def template_headers(form_id: str) -> List[str]:
    return [q["q"] for q in specs()["forms"][form_id]["questions"] if q["type"] != "section"]


# ---------------------------------------------------------------- lookups
def resolve_faculty(conn, text: str) -> Optional[str]:
    t = (text or "").strip()
    if not t or t.upper() in ("NA", "N/A"):
        return None
    first = t.split(" - ")[0].strip()
    for sql, arg in (("SELECT emp_id FROM faculty WHERE upper(emp_id) = upper(?)", first),
                     ("SELECT emp_id FROM faculty WHERE lower(email) = lower(?)", t),
                     ("SELECT emp_id FROM faculty WHERE lower(full_name) = lower(?)", t.split(" - ")[-1].strip())):
        row = conn.execute(sql, (arg,)).fetchone()
        if row:
            return row[0]
    return None


def resolve_student(conn, roll: str) -> Optional[str]:
    row = conn.execute("SELECT roll_no FROM students WHERE upper(roll_no) = upper(?)", ((roll or "").strip(),)).fetchone()
    return row[0] if row else None


def semester_at(conn, class_id: Optional[int], on: str) -> Optional[int]:
    """The semester a class was in on a date, from the semesters its tutor set over time."""
    if not class_id:
        return None
    row = conn.execute("SELECT semester_no FROM class_term_history WHERE class_id = ? AND date(changed_at) <= date(?) ORDER BY changed_at DESC, id DESC LIMIT 1",
                       (class_id, on)).fetchone()
    if row:
        return row[0]
    first = conn.execute("SELECT semester_no FROM class_term_history WHERE class_id = ? ORDER BY changed_at, id LIMIT 1", (class_id,)).fetchone()
    if first:
        return max(1, first[0] - 1)                      # before the first recorded change the class was a semester behind it
    cur = conn.execute("SELECT current_semester FROM classes WHERE class_id = ?", (class_id,)).fetchone()
    return cur[0] if cur else None


def class_at(conn, roll_no: str, on: str):
    """(class_id, year of study) the student was in on a date (the year follows the class's semester then); falls back to the current class."""
    row = conn.execute(
        "SELECT h.class_id, c.year_no FROM student_class_history h JOIN classes c ON c.class_id = h.class_id "
        "WHERE h.roll_no = ? AND h.class_id IS NOT NULL AND h.from_date <= ? AND (h.to_date IS NULL OR h.to_date >= ?) "
        "ORDER BY h.from_date DESC LIMIT 1", (roll_no, on, on)).fetchone()
    if not row:
        row = conn.execute("SELECT s.class_id, c.year_no FROM students s JOIN classes c ON c.class_id = s.class_id WHERE s.roll_no = ?", (roll_no,)).fetchone()
    if not row:
        return (None, None)
    sem = semester_at(conn, row[0], on)
    return (row[0], (sem + 1) // 2 if sem else row[1])


def upsert_org(conn, name: str, org_type: str = None, sector: str = None) -> Optional[int]:
    name = (name or "").strip()
    key = org_key(name)
    if not key:
        return None
    row = conn.execute("SELECT org_id FROM organizations WHERE name_key = ?", (key,)).fetchone()
    if row:
        if org_type or sector:
            conn.execute("UPDATE organizations SET org_type = COALESCE(org_type, ?), sector = COALESCE(sector, ?) WHERE org_id = ?",
                         (org_type, sector, row[0]))
        return row[0]
    return conn.execute("INSERT INTO organizations (name, name_key, org_type, sector) VALUES (?,?,?,?)", (name, key, org_type, sector)).lastrowid


# ---------------------------------------------------------------- one row
def _hash(form_id: str, by_norm: Dict[str, str]) -> str:
    canon = json.dumps(sorted((k, clean_cell(v)) for k, v in by_norm.items() if clean_cell(v)), ensure_ascii=False)
    return hashlib.sha256((form_id + canon).encode()).hexdigest()


def _convert(conn, key: str, col_type: str, text: str, warnings: List[str]):
    if key.endswith("emp_id"):
        emp = resolve_faculty(conn, text)
        if text.strip().upper() not in ("NA", "N/A") and not emp:
            warnings.append(f"Faculty not found: '{text}'")
        return emp
    t = (col_type or "").upper()
    if key in BOOL_KEYS:
        return truthy(text)
    if t == "DATE":
        return parse_date(text)
    if t == "REAL":
        return parse_num(text)
    if t == "INTEGER":
        return parse_int(text)
    return text


def ingest_row(conn, form_id: str, raw: Dict[str, Any], newsletter_entry_id: Optional[str] = None) -> Dict[str, Any]:
    spec = specs()["forms"].get(form_id)
    if not spec:
        return {"status": "skipped", "warnings": [f"No master-database mapping for '{form_id}'"]}
    ftype = spec["form_type"]
    by_norm = {norm_header(k): str(v) for k, v in raw.items() if v is not None and str(v).strip() != ""}
    vals, submitter_ids = {}, []
    for q in spec["questions"]:
        if q["type"] != "section" and q.get("key"):
            for title in (q["q"], *q.get("aliases", [])):         # earlier titles of a renamed question still import
                if norm_header(title) in by_norm:
                    vals[q["key"]] = by_norm[norm_header(title)].strip()
                    break
    warnings: List[str] = []
    if not vals.get("title"):
        return {"status": "error", "errors": ["Title is missing (check the column headers match the form)"]}

    digest = _hash(form_id, by_norm)
    dup = conn.execute("SELECT submission_id, newsletter_entry_id FROM form_submissions WHERE source_row_hash = ?", (digest,)).fetchone()
    if dup:
        if newsletter_entry_id and not dup[1]:
            conn.execute("UPDATE form_submissions SET newsletter_entry_id = ? WHERE submission_id = ?", (newsletter_entry_id, dup[0]))
        return {"status": "duplicate", "submission_id": dup[0]}

    event_date = parse_date(vals.get(spec["date_key"]))
    submitted = parse_datetime(by_norm.get("timestamp"))
    ay_id = ensure_ay(conn, ay_for((parse_datetime(event_date) or submitted or datetime.now()).date()))
    if not event_date:
        warnings.append("Date missing or not understood")

    email = by_norm.get("email address", "").strip()
    submitter = None
    for q in spec["questions"]:
        if q.get("submitter") and q.get("key") in vals:
            submitter = resolve_faculty(conn, vals[q["key"]])
    if not submitter and email:
        submitter = resolve_faculty(conn, email)
    if not submitter and ftype != "STUDENT":
        warnings.append("Submitting faculty could not be matched (select from the list / check email)")

    sid = conn.execute(
        """INSERT INTO form_submissions (form_type, ay_id, submitted_at, submitter_email, submitter_emp_id, event_date, category, title,
           evidence_url, media_url, photo_caption, badge_tag, is_landmark, publish_permission, authorization_confirmed,
           newsletter_entry_id, source_row_hash, raw_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (ftype, ay_id, submitted.strftime("%Y-%m-%d %H:%M:%S") if submitted else None, email, submitter, event_date,
         vals.get("category"), vals["title"], vals.get("evidence_url"), vals.get("media_url"), vals.get("photo_caption"),
         vals.get("badge_tag"), truthy(vals.get("is_landmark")),
         truthy(vals["publish_permission"]) if "publish_permission" in vals else None,      # unanswered is not the same as No
         1 if vals.get("authorization_confirmed") else 0, newsletter_entry_id, digest,
         json.dumps({k: clean_cell(v) for k, v in raw.items()}, ensure_ascii=False))).lastrowid

    table = DETAIL_TABLE[ftype]
    cols = {r["name"]: r["type"] for r in conn.execute(f"PRAGMA table_info({table})")}
    detail = {"submission_id": sid}
    for key, text in vals.items():
        if key in cols and key != "submission_id" and key not in COMMON:
            detail[key] = _convert(conn, key, cols[key], text, warnings)
    if "entry_kind" in detail:
        detail["entry_kind"] = "PARTICIPATION" if str(detail["entry_kind"]).lower().startswith("participation") else "ACHIEVEMENT"
    conn.execute(f"INSERT INTO {table} ({', '.join(detail)}) VALUES ({', '.join('?' * len(detail))})", list(detail.values()))

    on = event_date or date.today().isoformat()
    if ftype == "STUDENT":
        _student_people(conn, sid, vals, on, warnings)
    elif ftype == "RESEARCH":
        _contributors(conn, sid, vals.get("_contributors", ""), warnings)
    for ln in parse_lines(vals.get("_faculty_involved", "")):
        emp = resolve_faculty(conn, ln["id"])
        if emp:
            conn.execute("INSERT OR IGNORE INTO submission_faculty (submission_id, emp_id, role) VALUES (?,?,?)", (sid, emp, "Involved"))
        else:
            warnings.append(f"Faculty not found: '{ln['raw']}'")
    for col, role in (("convener_emp_id", "Convener"), ("lead_emp_id", "Lead")):
        if detail.get(col):
            conn.execute("INSERT OR IGNORE INTO submission_faculty (submission_id, emp_id, role) VALUES (?,?,?)", (sid, detail[col], role))
    for ln in parse_lines(vals.get("_event_participants", "")):
        roll = resolve_student(conn, ln["id"])
        if roll:
            conn.execute("INSERT OR IGNORE INTO event_participants (submission_id, roll_no, class_id_snapshot) VALUES (?,?,?)",
                         (sid, roll, class_at(conn, roll, on)[0]))
        else:
            warnings.append(f"Student not found: '{ln['raw']}'")
    if vals.get("_partner"):
        org = upsert_org(conn, vals["_partner"], vals.get("partner_type"))
        conn.execute("UPDATE outreach_activities SET partner_org_id = ? WHERE submission_id = ?", (org, sid))
    return {"status": "inserted", "submission_id": sid, "warnings": warnings}


def _student_people(conn, sid, vals, on, warnings):
    lead = (vals.get("_lead_roll") or "").strip().upper()
    lines = parse_lines(vals.get("_participants", ""))
    seen = set()
    d = parse_datetime(on) or datetime.now()
    for i, ln in enumerate(lines, 1):
        roll = resolve_student(conn, ln["id"]) if ln["id"] else None
        cls, year = class_at(conn, roll, on) if roll else (None, None)
        if not roll:
            warnings.append(f"Student not found: '{ln['raw']}'")
        seen.add(ln["id"])
        conn.execute(
            "INSERT INTO student_achievement_participants (submission_id, line_no, roll_no, raw_text, name, role, is_lead, class_id_snapshot, year_snapshot, semester_snapshot) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (sid, i, roll, ln["raw"], ln["name"] or (person_name(roll, conn) if roll else None), ln["extra"] or None, 1 if ln["id"] == lead else 0, cls, year,
             semester_at(conn, cls, on) if cls else None))
    if lead and lead not in seen:
        roll = resolve_student(conn, lead)
        cls, year = class_at(conn, roll, on) if roll else (None, None)
        if not roll:
            warnings.append(f"Lead student not found: '{lead}'")
        conn.execute(
            "INSERT INTO student_achievement_participants (submission_id, line_no, roll_no, raw_text, name, is_lead, class_id_snapshot, year_snapshot, semester_snapshot) "
            "VALUES (?,?,?,?,?,1,?,?,?)", (sid, len(lines) + 1, roll, lead, person_name(roll, conn) if roll else None, cls, year, semester_at(conn, cls, on) if cls else None))


def _contributors(conn, sid, text, warnings):
    for order, ln in enumerate(parse_lines(text), 1):
        ident, ptype, emp, roll, aff = ln["id"], "EXTERNAL", None, None, ln["extra"] or None
        if ident and ident != "EXT":
            emp = resolve_faculty(conn, ident) if conn.execute("SELECT 1 FROM faculty WHERE upper(emp_id)=?", (ident,)).fetchone() else None
            roll = None if emp else resolve_student(conn, ident)
            ptype = "FACULTY" if emp else "STUDENT" if roll else "EXTERNAL"
            if ptype == "EXTERNAL":
                warnings.append(f"Author id not found, stored as external: '{ln['raw']}'")
        conn.execute("INSERT INTO research_contributors (submission_id, author_order, person_type, emp_id, roll_no, name, affiliation) VALUES (?,?,?,?,?,?,?)",
                     (sid, order, ptype, emp, roll, ln["name"] or ln["raw"], aff))


# ---------------------------------------------------------------- many rows
def ingest_rows(form_id: str, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    inserted = duplicates = 0
    problems: List[Dict[str, Any]] = []
    with db() as conn:
        for n, raw in enumerate(rows, 2):          # row 1 is the header
            conn.execute("SAVEPOINT r")
            try:
                res = ingest_row(conn, form_id, raw)
                conn.execute("RELEASE r")
            except Exception as e:                  # one bad row never blocks the file
                conn.execute("ROLLBACK TO r")
                conn.execute("RELEASE r")
                res = {"status": "error", "errors": [str(e)]}
            if res["status"] == "inserted":
                inserted += 1
            elif res["status"] == "duplicate":
                duplicates += 1
            if res.get("errors") or res.get("warnings"):
                problems.append({"row": n, "status": res["status"], "messages": res.get("errors") or res.get("warnings")})
    return {"rows": len(rows), "inserted": inserted, "duplicates_skipped": duplicates, "needs_attention": problems}


def upload_excel(form_id: str, content: bytes) -> Dict[str, Any]:
    return ingest_rows(form_id, read_xlsx(content))


def ingest_form_row(form_id: str, raw: Dict[str, Any], newsletter_entry_id: Optional[str] = None) -> Dict[str, Any]:
    """Entry point used by the newsletter importer; never raises."""
    try:
        with db() as conn:
            return ingest_row(conn, form_id, raw, newsletter_entry_id)
    except Exception as e:
        return {"status": "error", "errors": [str(e)]}
