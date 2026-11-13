"""Placement records: Excel upload (replaces a student's earlier rows for that year) and scoped queries."""
import re
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from backend.master.auth import User
from backend.master.common import EFF_CLASS, norm_header, parse_date, parse_int, parse_num, read_xlsx
from backend.master.ingest import specs, upsert_org
from database.master_db import audit, ay_for, ensure_ay

EXAMPLE = ["21IT001", "2026-27", "Opted In", "", "Acme Technologies", "Product", "FTE", "8.5", "", "Software Engineer", "Chennai",
           "Accepted", "On-campus", "2026-09-15", "3", "Online test, technical, HR", "Medium", "Arrays, SQL joins", "Selected",
           "Friendly panel, focus on projects", "Practise DSA daily", "", "", "", "", "", "", "", "", "Yes - share anonymously with juniors",
           "I confirm the information is accurate."]


def questions():
    return [q for q in specs()["placement"]["questions"] if q["type"] != "section"]


def template_headers() -> List[str]:
    return [q["q"] for q in questions()]


def _offer_type(text: str, package, stipend) -> Optional[str]:
    t = (text or "").lower()
    if "convert" in t:
        return "INTERN_CONVERTED_FTE"
    if "+" in t:
        return "FTE+INTERN"
    if "intern" in t:
        return "INTERN"
    if "fte" in t or "full" in t:
        return "FTE"
    return "FTE" if package else "INTERN" if stipend else None


def _can_edit_student(conn, user: User, roll: str) -> bool:
    if user.is_admin:
        return True
    row = conn.execute("SELECT class_id FROM students WHERE roll_no = ?", (roll,)).fetchone()
    cid = row[0] if row else None
    if cid is None:       # graduated: use the last class they were in
        h = conn.execute("SELECT class_id FROM student_class_history WHERE roll_no = ? AND class_id IS NOT NULL ORDER BY from_date DESC, id DESC LIMIT 1", (roll,)).fetchone()
        cid = h[0] if h else None
    return cid is not None and user.can_edit_class(cid)


def keyed(rows: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Rows as they stand in a sheet ({column title: text}) -> {field name: text}, empty cells dropped."""
    keymap = {norm_header(q["q"]): q["key"] for q in questions()}
    out = []
    for rec in rows:
        row = {keymap[norm_header(k)]: str(v).strip() for k, v in rec.items() if norm_header(k) in keymap and v is not None and str(v).strip()}
        if row:
            out.append(row)
    return out


def group_by_roll(rows: List[Dict[str, str]]) -> Dict[str, List[Dict[str, str]]]:
    by_roll: Dict[str, List[Dict[str, str]]] = {}
    for row in rows:
        if row.get("roll_no"):
            by_roll.setdefault(row["roll_no"].upper(), []).append(row)
    return by_roll


def apply_rows(conn, user: User, by_roll: Dict[str, List[Dict[str, str]]], default_ay: Optional[str]) -> Dict[str, Any]:
    """Write placement rows into the live tables: for each student, what is there for that year is REPLACED by these rows.
    Used by the Excel upload and by the approval of a student's placement record."""
    stats = {"students": 0, "offers": 0, "interview_experiences": 0, "internship_experiences": 0, "replaced_students": 0, "errors": []}
    for roll, rows in by_roll.items():
        conn.execute("SAVEPOINT p")
        try:
            student = conn.execute("SELECT roll_no FROM students WHERE roll_no = ?", (roll,)).fetchone()
            if not student:
                raise ValueError("Roll number not found in the student list")
            if not _can_edit_student(conn, user, roll):
                raise ValueError("This student is not in your class")
            ay = next((r["ay_id"] for r in rows if r.get("ay_id")), None) or default_ay or ay_for(__import__("datetime").date.today())
            if not re.fullmatch(r"\d{4}-\d{2}", ay):
                raise ValueError(f"Academic year '{ay}' must look like 2026-27")
            ensure_ay(conn, ay)
            had = conn.execute("SELECT 1 FROM placement_profiles WHERE roll_no = ? AND ay_id = ? UNION SELECT 1 FROM placement_offers WHERE roll_no = ? AND ay_id = ? LIMIT 1",
                               (roll, ay, roll, ay)).fetchone()
            for t in ("placement_offers", "interview_experiences", "internship_experiences", "placement_profiles"):
                conn.execute(f"DELETE FROM {t} WHERE roll_no = ? AND ay_id = ?", (roll, ay))   # replace, don't merge
            has_offer = False
            for r in rows:
                if not r.get("company"):
                    continue
                share = 1 if r.get("consent", "").lower().startswith("yes") else 0
                org = upsert_org(conn, r["company"], sector=r.get("sector"))
                pkg, stp = parse_num(r.get("package_lpa")), parse_num(r.get("stipend_per_month"))
                otype = _offer_type(r.get("offer_type"), pkg, stp)
                if otype:
                    status = next((s for s in ("Accepted", "Declined", "Pending", "Revoked") if s.lower() in r.get("offer_status", "accepted").lower()), "Accepted")
                    conn.execute(
                        "INSERT INTO placement_offers (roll_no, ay_id, org_id, offer_type, package_lpa, stipend_per_month, job_role, work_location, offer_date, offer_status, is_on_campus, updated_by) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (roll, ay, org, otype, pkg, stp, r.get("job_role"), r.get("work_location"), parse_date(r.get("offer_date")), status,
                         None if not r.get("recruitment_mode") else 1 if r["recruitment_mode"].lower().startswith("on") else 0, user.id))
                    stats["offers"] += 1
                    has_offer = True
                if any(r.get(k) for k in ("rounds_count", "round_details", "difficulty", "questions_asked", "result", "interview_experience", "tips")):
                    conn.execute(
                        "INSERT INTO interview_experiences (roll_no, ay_id, org_id, rounds_count, round_details, difficulty, questions_asked, result, experience, tips, is_shareable) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (roll, ay, org, parse_int(r.get("rounds_count")), r.get("round_details"), r.get("difficulty"), r.get("questions_asked"),
                         r.get("result"), r.get("interview_experience"), r.get("tips"), share))
                    stats["interview_experiences"] += 1
                if any(r.get(k) for k in ("intern_duration", "intern_mode", "intern_role", "tech_stack", "work_summary", "learnings", "rating", "internship_experience")):
                    rating = parse_int(r.get("rating"))
                    conn.execute(
                        "INSERT INTO internship_experiences (roll_no, ay_id, org_id, duration, mode, role, tech_stack, work_summary, learnings, rating, experience, is_shareable) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (roll, ay, org, r.get("intern_duration"), r.get("intern_mode"), r.get("intern_role"), r.get("tech_stack"), r.get("work_summary"),
                         r.get("learnings"), rating if rating and 1 <= rating <= 5 else None, r.get("internship_experience"), share))
                    stats["internship_experiences"] += 1
            opt_text = next((r["opt_status"] for r in reversed(rows) if r.get("opt_status")), "")
            opted_out = "out" in opt_text.lower() and not has_offer
            reason = next((r["opt_out_reason"] for r in rows if r.get("opt_out_reason")), None) if opted_out else None
            conn.execute("INSERT INTO placement_profiles (roll_no, ay_id, opt_status, opt_out_reason, updated_by) VALUES (?,?,?,?,?)",
                         (roll, ay, "OPTED_OUT" if opted_out else "OPTED_IN", reason, user.id))
            stats["students"] += 1
            stats["replaced_students"] += 1 if had else 0
            conn.execute("RELEASE p")
        except Exception as e:
            conn.execute("ROLLBACK TO p")
            conn.execute("RELEASE p")
            stats["errors"].append({"roll_no": roll, "message": str(e)})
    return stats


def upload_placements(conn, user: User, content: bytes, default_ay: Optional[str]) -> Dict[str, Any]:
    stats = apply_rows(conn, user, group_by_roll(keyed(read_xlsx(content))), default_ay)
    audit(conn, user.id, "PLACEMENT_UPLOAD", "placements", None, f"{stats['students']} students, {stats['offers']} offers")
    return stats


# ---------------------------------------------------------------- queries
def _scope(user: User, where: List[str], args: List[Any], alias: str = "s"):
    if not user.all_access:
        ids = sorted(user.class_ids) or [-1]
        where.append(f"{EFF_CLASS} IN ({','.join('?' * len(ids))})")
        args += ids


def _offers_base(user: User, f: Dict[str, Any]):
    """FROM ... WHERE ... (and values) for the offer filters, limited to the person's classes. Shared by the list and the download."""
    where, args = ["1=1"], []
    _scope(user, where, args)
    for col, key in (("o.ay_id", "ay_id"), ("o.org_id", "org_id"), ("o.offer_type", "offer_type"), ("o.offer_status", "offer_status"),
                     (EFF_CLASS, "class_id"), ("c.programme", "programme"), ("c.grp", "grp"), ("c.year_no", "year_no")):
        if f.get(key) not in (None, ""):
            where.append(f"{col} = ?")
            args.append(f[key])
    if f.get("min_package"):
        where.append("o.package_lpa >= ?")
        args.append(float(f["min_package"]))
    if f.get("max_package"):
        where.append("o.package_lpa <= ?")
        args.append(float(f["max_package"]))
    if f.get("q"):
        where.append("(s.roll_no LIKE ? OR s.full_name LIKE ? OR g.name LIKE ?)")
        args += [f"%{f['q']}%"] * 3
    base = ("FROM placement_offers o JOIN students s ON s.roll_no = o.roll_no JOIN organizations g ON g.org_id = o.org_id "
            f"LEFT JOIN classes c ON c.class_id = {EFF_CLASS} WHERE {' AND '.join(where)}")
    return base, args


def list_offers(conn, user: User, f: Dict[str, Any], limit=200, offset=0) -> Dict[str, Any]:
    base, args = _offers_base(user, f)
    total = conn.execute(f"SELECT COUNT(*) {base}", args).fetchone()[0]
    rows = conn.execute(
        f"SELECT s.roll_no, s.full_name, c.class_code, o.ay_id, g.org_id, g.name AS company, o.offer_type, o.package_lpa, o.stipend_per_month, "
        f"o.job_role, o.work_location, o.offer_status, o.is_on_campus {base} ORDER BY o.ay_id DESC, g.name, s.roll_no LIMIT ? OFFSET ?",
        args + [limit, offset]).fetchall()
    return {"total": total, "rows": [dict(r) for r in rows]}


def _profiles_base(user: User, f: Dict[str, Any]):
    """FROM ... WHERE ... (and values) for the opt-in / opt-out filters. Shared by the list and the download."""
    where, args = ["1=1"], []
    _scope(user, where, args)
    for col, key in (("p.ay_id", "ay_id"), ("p.opt_status", "opt_status"), (EFF_CLASS, "class_id"), ("c.programme", "programme"), ("c.grp", "grp")):
        if f.get(key) not in (None, ""):
            where.append(f"{col} = ?")
            args.append(f[key])
    base = f"FROM placement_profiles p JOIN students s ON s.roll_no = p.roll_no LEFT JOIN classes c ON c.class_id = {EFF_CLASS} WHERE {' AND '.join(where)}"
    return base, args


def list_profiles(conn, user: User, f: Dict[str, Any], limit=200, offset=0) -> Dict[str, Any]:
    base, args = _profiles_base(user, f)
    total = conn.execute(f"SELECT COUNT(*) {base}", args).fetchone()[0]
    rows = conn.execute(
        f"SELECT s.roll_no, s.full_name, c.class_code, p.ay_id, p.opt_status, p.opt_out_reason, "
        f"(SELECT COUNT(*) FROM placement_offers o WHERE o.roll_no = p.roll_no AND o.ay_id = p.ay_id AND o.offer_status = 'Accepted') AS offers, "
        f"(SELECT MAX(package_lpa) FROM placement_offers o WHERE o.roll_no = p.roll_no AND o.ay_id = p.ay_id AND o.offer_status = 'Accepted') AS best_package_lpa "
        f"{base} ORDER BY p.ay_id DESC, c.class_code, s.roll_no LIMIT ? OFFSET ?", args + [limit, offset]).fetchall()
    return {"total": total, "rows": [dict(r) for r in rows]}


def student_detail(conn, user: User, roll: str) -> Dict[str, Any]:
    from backend.master.people import student_in_scope
    student_in_scope(conn, user, roll)
    q = lambda sql: [dict(r) for r in conn.execute(sql, (roll,))]
    return {
        "profiles": q("SELECT ay_id, opt_status, opt_out_reason FROM placement_profiles WHERE roll_no = ? ORDER BY ay_id DESC"),
        "offers": q("SELECT o.*, g.name AS company FROM placement_offers o JOIN organizations g ON g.org_id = o.org_id WHERE o.roll_no = ? ORDER BY o.ay_id DESC"),
        "interviews": q("SELECT e.*, g.name AS company FROM interview_experiences e JOIN organizations g ON g.org_id = e.org_id WHERE e.roll_no = ?"),
        "internships": q("SELECT e.*, g.name AS company FROM internship_experiences e JOIN organizations g ON g.org_id = e.org_id WHERE e.roll_no = ?"),
    }


# ---------------------------------------------------------------- review support (placements waiting for a tutor's approval)
def student_class(conn, roll: str) -> Optional[int]:
    """The class whose tutor reviews this student's placement data: the current class, else the last one they were in."""
    row = conn.execute(f"SELECT {EFF_CLASS} FROM students s WHERE s.roll_no = ?", (roll,)).fetchone()
    return row[0] if row else None


def describe_rows(rows: List[Dict[str, str]]) -> Dict[str, Any]:
    """Plain-language view of a student's rows plus the problems an approver should see. rows are {field: text} (see keyed)."""
    notes: List[str] = []
    blockers: List[str] = []
    summary: List[str] = []
    ay = next((r["ay_id"] for r in rows if r.get("ay_id")), None)
    if ay and not re.fullmatch(r"\d{4}-\d{2}", ay):
        blockers.append(f"The academic year '{ay}' must look like 2026-27")
    opt = next((r["opt_status"] for r in reversed(rows) if r.get("opt_status")), "")
    offers = [r for r in rows if r.get("company")]
    for n, r in enumerate(rows, 1):
        if r.get("company"):
            pkg, stp = parse_num(r.get("package_lpa")), parse_num(r.get("stipend_per_month"))
            otype = _offer_type(r.get("offer_type"), pkg, stp)
            summary.append(f"{r['company']} - {(otype or 'offer type?').replace('_', ' ')}" + (f" - {pkg:g} LPA" if pkg else "") + (f" - Rs {stp:,.0f}/month" if stp else ""))
            if not otype:
                notes.append(f"Offer {n}: no offer type, package or stipend was given for {r['company']}")
            elif otype in ("FTE", "FTE+INTERN", "INTERN_CONVERTED_FTE") and not pkg:
                notes.append(f"Offer {n}: {r['company']} is a full-time offer but the package is empty")
            if r.get("package_lpa") and pkg is None:
                notes.append(f"Offer {n}: the package '{r['package_lpa']}' is not a number")
    if not offers:
        if "out" in opt.lower():
            reason = next((r["opt_out_reason"] for r in rows if r.get("opt_out_reason")), None)
            summary.append("Opted out of placements" + (f" ({reason})" if reason else ""))
        else:
            summary.append("Opted in, no offer yet")
    if offers and "out" in opt.lower():
        notes.append("The student says 'Opted out' but also listed an offer: they will be recorded as opted in")
    if not offers and not opt:
        notes.append("Neither an offer nor an opt-in / opt-out choice was given")
    return {"ay": ay, "summary": summary, "warnings": notes, "blockers": blockers}


def preview_student(conn, rows: List[Dict[str, str]], roll: str) -> Dict[str, Any]:
    d = describe_rows(rows)
    student = conn.execute("SELECT full_name FROM students WHERE roll_no = ?", (roll,)).fetchone()
    class_id = None
    if not student:
        d["blockers"].append(f"Roll number {roll} is not in the student list. Add the student first, or correct the roll number.")
    else:
        class_id = student_class(conn, roll)
        tutor = conn.execute("SELECT f.full_name FROM classes c LEFT JOIN faculty f ON f.emp_id = c.tutor_id WHERE c.class_id = ?", (class_id,)).fetchone() if class_id else None
        if not class_id or not tutor or not tutor[0]:
            d["warnings"].append("This student's class has no tutor, so only the Admin can approve this")
        ay = d["ay"] or ay_for(__import__("datetime").date.today())
        if conn.execute("SELECT 1 FROM placement_profiles WHERE roll_no = ? AND ay_id = ?", (roll, ay)).fetchone():
            d["warnings"].append(f"This student already has placement records for {ay}; approving replaces them with these")
    d.update(student_name=student[0] if student else None, class_id=class_id)
    return d
