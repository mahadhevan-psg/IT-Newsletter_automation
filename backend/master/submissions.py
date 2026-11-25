"""Browsing form submissions with the filters from the design, limited to what the caller may see."""
import json
from typing import Any, Dict

from fastapi import HTTPException

from backend.master import answers
from backend.master.auth import User
from backend.master.profiles import form_title


def form_name(form_type: str) -> str:
    fid = answers.form_of(form_type)
    return form_title(fid) if fid else form_type


def _visible(user: User, where, args):
    if user.all_access or "PC" in user.roles:          # Admin, HoD and programme coordinators see every submission
        return
    ids = sorted(user.class_ids) or [-1]
    marks = ",".join("?" * len(ids))
    where.append(
        "(fs.submitter_emp_id = ? OR fs.submission_id IN (SELECT submission_id FROM submission_faculty WHERE emp_id = ?)"
        f" OR fs.submission_id IN (SELECT submission_id FROM student_achievement_participants WHERE class_id_snapshot IN ({marks}))"
        f" OR fs.submission_id IN (SELECT submission_id FROM event_participants WHERE class_id_snapshot IN ({marks})))")
    args += [user.id, user.id, *ids, *ids]


def _base(user: User, f: Dict[str, Any]):
    """FROM ... WHERE ... (and its bound values) for the filters in f, limited to what this person may see. Shared by the list and the download."""
    where, args = ["1=1"], []
    _visible(user, where, args)
    for col, key in (("fs.form_type", "form_type"), ("fs.ay_id", "ay_id"), ("fs.category", "category"), ("fs.submitter_emp_id", "submitter")):
        if f.get(key):
            where.append(f"{col} = ?")
            args.append(f[key])
    if f.get("date_from"):
        where.append("fs.event_date >= ?")
        args.append(f["date_from"])
    if f.get("date_to"):
        where.append("fs.event_date <= ?")
        args.append(f["date_to"])
    if f.get("q"):
        where.append("fs.title LIKE ?")
        args.append(f"%{f['q']}%")
    if f.get("has_media"):
        where.append("fs.media_url IS NOT NULL AND fs.media_url != ''")
    # student-linked filters
    sub = []
    if f.get("roll_no"):
        sub.append("roll_no = ?")
        args.append(f["roll_no"].upper())
    if f.get("class_id"):
        if not user.sees_class(int(f["class_id"])):
            raise HTTPException(403, "That class is outside your scope")
        sub.append("class_id_snapshot = ?")
        args.append(int(f["class_id"]))
    if sub:
        where.append(f"fs.submission_id IN (SELECT submission_id FROM student_achievement_participants WHERE {' AND '.join(sub)})")
    if f.get("level"):
        where.append("fs.submission_id IN (SELECT submission_id FROM student_achievements WHERE level = ? UNION SELECT submission_id FROM faculty_achievements WHERE level = ?)")
        args += [f["level"], f["level"]]
    base = f"FROM form_submissions fs LEFT JOIN faculty u ON u.emp_id = fs.submitter_emp_id WHERE {' AND '.join(where)}"
    return base, args


def list_submissions(conn, user: User, f: Dict[str, Any], limit: int = 100, offset: int = 0) -> Dict[str, Any]:
    base, args = _base(user, f)
    total = conn.execute(f"SELECT COUNT(*) {base}", args).fetchone()[0]
    rows = conn.execute(
        f"SELECT fs.submission_id, fs.form_type, fs.ay_id, fs.event_date, fs.category, fs.title, fs.badge_tag, fs.is_landmark, "
        f"fs.submitter_emp_id, u.full_name AS submitter, fs.submitter_email {base} ORDER BY fs.event_date DESC, fs.submission_id DESC LIMIT ? OFFSET ?",
        args + [limit, offset]).fetchall()
    names: Dict[str, str] = {}
    out = []
    for r in rows:
        d = dict(r)
        d["form"] = names.setdefault(d["form_type"], form_name(d["form_type"]))
        out.append(d)
    return {"total": total, "rows": out}


def get_submission(conn, user: User, sid: int) -> Dict[str, Any]:
    where, args = ["fs.submission_id = ?"], [sid]
    _visible(user, where, args)
    if not conn.execute(f"SELECT 1 FROM form_submissions fs WHERE {' AND '.join(where)}", args).fetchone():
        raise HTTPException(404, "Submission not found")
    head = dict(conn.execute("SELECT * FROM form_submissions WHERE submission_id = ?", (sid,)).fetchone())
    try:
        raw = json.loads(head.pop("raw_json", None) or "{}")
    except ValueError:
        raw = {}
    shown = answers.display(head["form_type"], head["category"], raw)
    entered_by = conn.execute("SELECT full_name FROM faculty WHERE emp_id = ?", (head.get("submitter_emp_id"),)).fetchone()
    q = lambda sql: [dict(r) for r in conn.execute(sql, (sid,))]
    return {
        "header": {"submission_id": sid, "form_type": head["form_type"], "form": form_name(head["form_type"]), "category": head["category"], "title": head["title"],
                   "event_date": head["event_date"], "ay_id": head["ay_id"], "submitted_by": entered_by[0] if entered_by else head.get("submitter_email"), "submitted_at": head["submitted_at"]},
        **shown,
        "participants": q("SELECT p.line_no, p.roll_no, p.name, p.role, p.is_lead, p.raw_text, c.class_code, p.year_snapshot FROM student_achievement_participants p LEFT JOIN classes c ON c.class_id = p.class_id_snapshot WHERE p.submission_id = ? ORDER BY p.line_no"),
        "contributors": q("SELECT c.author_order, c.person_type, c.emp_id, c.roll_no, COALESCE(f.full_name, s.full_name, c.name) AS name, c.affiliation FROM research_contributors c "
                          "LEFT JOIN faculty f ON f.emp_id = c.emp_id LEFT JOIN students s ON s.roll_no = c.roll_no WHERE c.submission_id = ? ORDER BY c.author_order"),
        "faculty": q("SELECT s.emp_id, f.full_name, s.role FROM submission_faculty s JOIN faculty f ON f.emp_id = s.emp_id WHERE s.submission_id = ?"),
        "event_students": q("SELECT e.roll_no, st.full_name FROM event_participants e JOIN students st ON st.roll_no = e.roll_no WHERE e.submission_id = ?"),
    }


def unmatched(conn, user: User):
    """Roll numbers on submissions that did not match a student - for tutors to fix the student list or the form."""
    if not user.is_admin:
        raise HTTPException(403, "Admin only")
    rows = conn.execute(
        "SELECT p.submission_id, p.raw_text, fs.title, fs.submitter_emp_id FROM student_achievement_participants p "
        "JOIN form_submissions fs USING(submission_id) WHERE p.roll_no IS NULL ORDER BY p.submission_id DESC LIMIT 200").fetchall()
    return [dict(r) for r in rows]
