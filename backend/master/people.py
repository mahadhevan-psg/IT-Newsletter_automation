"""Students, classes, faculty and roles. Permission rules live here so the API layer stays thin."""
import secrets
from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from backend.master.auth import User, set_staff_password
from backend.master.common import EFF_CLASS, norm_header, read_xlsx
from database.master_db import audit, ay_for, ensure_ay

from backend.master.excel_templates import FACULTY_HEADERS as FACULTY_TEMPLATE, STUDENT_HEADERS as STUDENT_TEMPLATE  # noqa: E402  (one definition of the upload columns)


def _row(rec: Dict[str, str]) -> Dict[str, str]:
    return {norm_header(k): v for k, v in rec.items()}


def _pick(rec: Dict[str, str], *names: str) -> str:
    for n in names:
        v = rec.get(norm_header(n))
        if v:
            return v.strip()
    return ""


# ================================================================ classes
# A class is a cohort of students, identified by its tutor and its semester. Two semesters make a year (UG: 8 semesters,
# PG: 4), so the year is worked out from the semester and the class code follows it. Two classes can be in the same
# year at once (one in semester 3, another in semester 4); students stay in their class as it moves up, nobody is "promoted".
def max_semester(programme: str) -> int:
    return 4 if programme == "PG" else 8


def year_of(semester: int) -> int:
    return (int(semester) + 1) // 2


def class_label(tutor_name: Optional[str], semester: int) -> str:
    return f"{tutor_name or 'No tutor'} · Sem {semester}"


def next_class_code(conn, programme: str, grp: Optional[str], semester: int, class_id: Optional[int] = None) -> str:
    """UG-G1-2 / PG-2 for the year the semester falls in; when another class already holds that code, the semester is added (UG-G1-2-S3)."""
    year = year_of(semester)
    base = f"UG-{grp}-{year}" if programme == "UG" else f"PG-{year}"
    taken = lambda code: conn.execute("SELECT 1 FROM classes WHERE class_code = ? AND class_id IS NOT ?", (code, class_id)).fetchone()
    if not taken(base):
        return base
    code, n = f"{base}-S{semester}", 1
    while taken(code):
        n += 1
        code = f"{base}-S{semester}-{n}"
    return code


def list_classes(conn, user: User, include_completed: bool = False) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """SELECT c.class_id, c.class_code, c.programme, c.grp, c.year_no, c.current_semester, c.ay_id, c.tutor_id, c.status,
                  f.full_name AS tutor_name,
                  (SELECT COUNT(*) FROM students s WHERE s.class_id = c.class_id AND s.status = 'Active') AS student_count
           FROM classes c LEFT JOIN faculty f ON f.emp_id = c.tutor_id
           ORDER BY c.programme DESC, c.grp, c.year_no, c.current_semester, c.class_id""").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["label"] = class_label(r["tutor_name"], r["current_semester"])
        d["max_semester"] = max_semester(r["programme"])
        d["can_edit"] = user.can_edit_class(r["class_id"]) and r["status"] == "Active"
        if user.sees_class(r["class_id"]) and (include_completed or r["status"] == "Active"):
            out.append(d)
    return out


def _class(conn, class_id: int):
    c = conn.execute("SELECT * FROM classes WHERE class_id = ?", (class_id,)).fetchone()
    if not c:
        raise HTTPException(404, "Class not found")
    return c


def _need_edit(user: User, class_id: int):
    if not user.can_edit_class(class_id):
        raise HTTPException(403, "You can only change your own class")


def set_term(conn, user: User, class_id: int, semester: int, ay_id: Optional[str]) -> Dict[str, Any]:
    """Set the class's semester. The year and the class code follow from it; the students stay where they are."""
    c = _class(conn, class_id)
    _need_edit(user, class_id)
    if c["status"] != "Active":
        raise HTTPException(400, "This class has graduated")
    top = max_semester(c["programme"])
    if not 1 <= semester <= top:
        raise HTTPException(400, f"Semester must be between 1 and {top}")
    ay = ensure_ay(conn, ay_id) if ay_id else c["ay_id"]
    year, code = year_of(semester), next_class_code(conn, c["programme"], c["grp"], semester, class_id)
    conn.execute("UPDATE classes SET current_semester = ?, year_no = ?, class_code = ?, ay_id = ? WHERE class_id = ?", (semester, year, code, ay, class_id))
    conn.execute("INSERT INTO class_term_history (class_id, ay_id, semester_no, changed_by) VALUES (?,?,?,?)", (class_id, ay, semester, user.id))
    audit(conn, user.id, "TERM", "classes", code, f"semester {semester} (year {year}), AY {ay}" + (f"; was {c['class_code']}" if code != c["class_code"] else ""))
    return {"class_code": code, "year_no": year, "current_semester": semester}


def add_class(conn, admin: User, d: Dict[str, Any]) -> Dict[str, Any]:
    """A new class (cohort): programme, group (UG), starting semester and tutor. Admin only."""
    programme = (d.get("programme") or "").upper()
    if programme not in ("UG", "PG"):
        raise HTTPException(400, "Programme must be UG or PG")
    grp = (d.get("grp") or None) if programme == "UG" else None
    if programme == "UG" and grp not in ("G1", "G2"):
        raise HTTPException(400, "A UG class needs a group (G1 or G2)")
    semester = int(d.get("semester") or 1)
    if not 1 <= semester <= max_semester(programme):
        raise HTTPException(400, f"Semester must be between 1 and {max_semester(programme)}")
    tutor = (d.get("tutor_id") or "").strip() or None
    if tutor and not conn.execute("SELECT 1 FROM faculty WHERE emp_id = ? AND status = 'Active'", (tutor,)).fetchone():
        raise HTTPException(400, "Faculty not found or not active")
    ay = ensure_ay(conn, d["ay_id"]) if d.get("ay_id") else conn.execute("SELECT ay_id FROM academic_years WHERE is_current = 1").fetchone()[0]
    code = next_class_code(conn, programme, grp, semester)
    cid = conn.execute("INSERT INTO classes (class_code, programme, grp, year_no, current_semester, ay_id, tutor_id) VALUES (?,?,?,?,?,?,?)",
                       (code, programme, grp, year_of(semester), semester, ay, tutor)).lastrowid
    today = date.today().isoformat()
    conn.execute("INSERT INTO class_term_history (class_id, ay_id, semester_no, changed_by) VALUES (?,?,?,?)", (cid, ay, semester, admin.id))
    if tutor:
        conn.execute("INSERT INTO class_tutor_history (class_id, tutor_id, from_date) VALUES (?,?,?)", (cid, tutor, today))
    audit(conn, admin.id, "ADD_CLASS", "classes", code, f"semester {semester}, tutor {tutor}")
    return {"class_id": cid, "class_code": code}


def graduate_class(conn, user: User, class_id: int) -> Dict[str, Any]:
    """After the final semester: the students become Graduated (their records and the class they were in are kept) and the class closes."""
    c = _class(conn, class_id)
    _need_edit(user, class_id)
    if c["status"] != "Active":
        raise HTTPException(400, "This class has already graduated")
    if c["current_semester"] < max_semester(c["programme"]):
        raise HTTPException(400, f"A {c['programme']} class can be marked graduated only in semester {max_semester(c['programme'])}")
    today = date.today().isoformat()
    rolls = [r[0] for r in conn.execute("SELECT roll_no FROM students WHERE class_id = ? AND status = 'Active'", (class_id,))]
    for roll in rolls:
        conn.execute("UPDATE student_class_history SET to_date = ? WHERE roll_no = ? AND to_date IS NULL", (today, roll))
        conn.execute("INSERT INTO student_class_history (roll_no, class_id, from_date, to_date, action, done_by) VALUES (?,?,?,?,?,?)",
                     (roll, None, today, today, "Graduated", user.id))
        conn.execute("UPDATE students SET class_id = NULL, status = 'Graduated' WHERE roll_no = ?", (roll,))
    conn.execute("UPDATE classes SET status = 'Completed' WHERE class_id = ?", (class_id,))
    conn.execute("UPDATE class_tutor_history SET to_date = ? WHERE class_id = ? AND to_date IS NULL", (today, class_id))
    audit(conn, user.id, "GRADUATE", "classes", c["class_code"], f"{len(rolls)} students")
    return {"graduated": len(rolls), "class_code": c["class_code"]}


def set_tutor(conn, admin: User, class_id: int, emp_id: str):
    c = _class(conn, class_id)
    f = conn.execute("SELECT emp_id FROM faculty WHERE emp_id = ? AND status = 'Active'", (emp_id,)).fetchone() if emp_id else None
    if emp_id and not f:
        raise HTTPException(400, "Faculty not found or not active")
    today = date.today().isoformat()
    conn.execute("UPDATE class_tutor_history SET to_date = ? WHERE class_id = ? AND to_date IS NULL", (today, class_id))
    if emp_id:
        conn.execute("INSERT INTO class_tutor_history (class_id, tutor_id, from_date) VALUES (?,?,?)", (class_id, emp_id, today))
    conn.execute("UPDATE classes SET tutor_id = ? WHERE class_id = ?", (emp_id or None, class_id))
    audit(conn, admin.id, "TUTOR_CHANGE", "classes", c["class_code"], f"{c['tutor_id']} -> {emp_id}")


# ================================================================ students
def _student_scope(user: User, where: List[str], args: List[Any]):
    if not user.all_access:
        ids = sorted(user.class_ids) or [-1]
        where.append(f"s.class_id IN ({','.join('?' * len(ids))})")
        args += ids


def list_students(conn, user: User, f: Dict[str, Any], limit: int = 100, offset: int = 0) -> Dict[str, Any]:
    where, args = ["1=1"], []
    _student_scope(user, where, args)
    for col, key in (("s.class_id", "class_id"), ("c.programme", "programme"), ("c.grp", "grp"), ("c.year_no", "year_no"),
                     ("s.status", "status")):
        if f.get(key) not in (None, ""):
            where.append(f"{col} = ?")
            args.append(f[key])
    if f.get("q"):
        where.append("(s.roll_no LIKE ? OR s.full_name LIKE ?)")
        args += [f"%{f['q']}%"] * 2
    base = f"FROM students s LEFT JOIN classes c ON c.class_id = s.class_id WHERE {' AND '.join(where)}"
    total = conn.execute(f"SELECT COUNT(*) {base}", args).fetchone()[0]
    rows = conn.execute(
        f"SELECT s.roll_no, s.full_name, s.programme, s.class_id, c.class_code, c.year_no, c.current_semester, s.status "
        f"{base} ORDER BY c.class_code, s.roll_no LIMIT ? OFFSET ?",
        args + [limit, offset]).fetchall()
    return {"total": total, "rows": [dict(r) for r in rows]}


def student_in_scope(conn, user: User, roll_no: str):
    s = conn.execute(f"SELECT s.*, {EFF_CLASS} AS eff_class FROM students s WHERE s.roll_no = ?", (roll_no,)).fetchone()
    if not s:
        raise HTTPException(404, "Student not found")
    if not user.sees_class(s["eff_class"]):
        raise HTTPException(403, "Student is outside your classes")
    return s


def _history(conn, roll, class_id, action, user_id):
    today = date.today().isoformat()
    conn.execute("UPDATE student_class_history SET to_date = ? WHERE roll_no = ? AND to_date IS NULL", (today, roll))
    conn.execute("INSERT INTO student_class_history (roll_no, class_id, from_date, action, done_by) VALUES (?,?,?,?,?)",
                 (roll, class_id, today, action, user_id))


def add_student(conn, user: User, d: Dict[str, Any]) -> str:
    roll = (d.get("roll_no") or "").strip().upper()
    name = (d.get("full_name") or "").strip()
    if not roll or not name:
        raise HTTPException(400, "Roll number and name are required")
    c = _class(conn, int(d.get("class_id") or 0))
    _need_edit(user, c["class_id"])
    if conn.execute("SELECT 1 FROM students WHERE upper(roll_no) = ?", (roll,)).fetchone():
        raise HTTPException(409, f"Roll number {roll} already exists")
    conn.execute("INSERT INTO students (roll_no, full_name, programme, class_id) VALUES (?,?,?,?)", (roll, name, c["programme"], c["class_id"]))
    _history(conn, roll, c["class_id"], "Added", user.id)
    audit(conn, user.id, "ADD", "students", roll, c["class_code"])
    return roll


def update_student(conn, user: User, roll_no: str, d: Dict[str, Any]):
    s = student_in_scope(conn, user, roll_no)
    _need_edit(user, s["class_id"])
    name = (d.get("full_name") or "").strip()
    if name:
        conn.execute("UPDATE students SET full_name = ? WHERE roll_no = ?", (name, roll_no))
    audit(conn, user.id, "UPDATE", "students", roll_no)


def remove_student(conn, user: User, roll_no: str):
    s = student_in_scope(conn, user, roll_no)
    _need_edit(user, s["class_id"])
    today = date.today().isoformat()
    conn.execute("UPDATE student_class_history SET to_date = ? WHERE roll_no = ? AND to_date IS NULL", (today, roll_no))
    conn.execute("INSERT INTO student_class_history (roll_no, class_id, from_date, to_date, action, done_by) VALUES (?,?,?,?,?,?)",
                 (roll_no, None, today, today, "Removed", user.id))
    conn.execute("UPDATE students SET class_id = NULL, status = 'Removed' WHERE roll_no = ?", (roll_no,))
    audit(conn, user.id, "REMOVE", "students", roll_no)


def transfer_student(conn, user: User, roll_no: str, class_id: int):
    s = student_in_scope(conn, user, roll_no)
    _need_edit(user, s["class_id"])
    c = _class(conn, class_id)
    conn.execute("UPDATE students SET class_id = ?, programme = ?, status = 'Active' WHERE roll_no = ?", (class_id, c["programme"], roll_no))
    _history(conn, roll_no, class_id, "Transferred", user.id)
    audit(conn, user.id, "TRANSFER", "students", roll_no, c["class_code"])


def upload_students(conn, user: User, content: bytes, default_class_id: Optional[int]) -> Dict[str, Any]:
    added = updated = 0
    errors = []
    codes = {r["class_code"].upper(): r["class_id"] for r in conn.execute("SELECT class_id, class_code FROM classes WHERE status = 'Active'")}
    mine = sorted(user.tutor_class_ids & set(codes.values()))
    own_class = mine[0] if len(mine) == 1 and not user.is_admin else None          # a tutor with one class need not name it
    for n, rec in enumerate((_row(r) for r in read_xlsx(content)), 2):
        roll = _pick(rec, "Roll No", "Roll Number").upper()
        name = _pick(rec, "Full Name", "Name")
        cid = codes.get(_pick(rec, "Class Code", "Class").upper()) or default_class_id or own_class
        if not roll or not name or not cid:
            errors.append({"row": n, "message": "Roll no, name and a class (the class chosen above, or a Class Code column) are required"})
            continue
        data = {"roll_no": roll, "full_name": name, "class_id": cid}
        conn.execute("SAVEPOINT s")
        try:
            existing = conn.execute("SELECT class_id, status FROM students WHERE roll_no = ?", (roll,)).fetchone()
            if existing:
                if existing["class_id"] != cid:
                    _need_edit(user, cid)
                    if existing["class_id"]:
                        _need_edit(user, existing["class_id"])
                    transfer_student(conn, user, roll, cid) if existing["class_id"] else _revive(conn, user, roll, cid)
                else:
                    _need_edit(user, cid)
                update_student(conn, user, roll, {k: v for k, v in data.items() if k not in ("roll_no", "class_id")})
                updated += 1
            else:
                add_student(conn, user, data)
                added += 1
            conn.execute("RELEASE s")
        except HTTPException as e:
            conn.execute("ROLLBACK TO s")
            conn.execute("RELEASE s")
            errors.append({"row": n, "roll_no": roll, "message": e.detail})
    return {"added": added, "updated": updated, "errors": errors}


def _revive(conn, user, roll, class_id):
    c = _class(conn, class_id)
    conn.execute("UPDATE students SET class_id = ?, programme = ?, status = 'Active' WHERE roll_no = ?", (class_id, c["programme"], roll))
    _history(conn, roll, class_id, "Added", user.id)


# ================================================================ faculty (Admin)
def list_faculty(conn, user: User, q: str = "", status: str = "") -> List[Dict[str, Any]]:
    cols = "f.emp_id, f.full_name, f.designation" + (", f.email, f.phone, f.qualification, f.date_of_joining, f.status" if user.all_access else "")
    where, args = ["f.emp_id != 'ADMIN'"], []
    if q:
        where.append("(f.emp_id LIKE ? OR f.full_name LIKE ?)")
        args += [f"%{q}%"] * 2
    if status:
        where.append("f.status = ?")
        args.append(status)
    rows = conn.execute(f"SELECT {cols} FROM faculty f WHERE {' AND '.join(where)} ORDER BY f.full_name", args).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        if user.all_access:
            d["roles"] = [{"role": x["role"], "programme": x["programme"], "grp": x["grp"]} for x in
                          conn.execute("SELECT role, programme, grp FROM role_assignments WHERE emp_id = ?", (r["emp_id"],))]
            d["tutor_of"] = [x[0] for x in conn.execute("SELECT class_code FROM classes WHERE tutor_id = ?", (r["emp_id"],))]
            d["counts"] = _activity_counts(conn, r["emp_id"])
        out.append(d)
    return out


def _activity_counts(conn, emp: str) -> Dict[str, int]:
    """How much each faculty member has entered, counted the same way as their own page (author / convener / lead / submitter / mentor)."""
    involved = "fs.submission_id IN (SELECT submission_id FROM submission_faculty WHERE emp_id = ?) OR fs.submitter_emp_id = ?"
    one = lambda sql, n: conn.execute(sql, [emp] * n).fetchone()[0]
    return {
        "research": one("SELECT COUNT(*) FROM form_submissions fs WHERE fs.form_type = 'RESEARCH' AND (fs.submission_id IN "
                        "(SELECT submission_id FROM research_contributors WHERE emp_id = ?) OR fs.submitter_emp_id = ?)", 2),
        "achievements": one("SELECT COUNT(*) FROM faculty_achievements WHERE emp_id = ?", 1),
        "events": one(f"SELECT COUNT(*) FROM department_highlights d JOIN form_submissions fs USING (submission_id) WHERE d.convener_emp_id = ? OR {involved}", 3),
        "outreach": one(f"SELECT COUNT(*) FROM outreach_activities o JOIN form_submissions fs USING (submission_id) WHERE o.lead_emp_id = ? OR {involved}", 3),
        "mentored": one("SELECT COUNT(*) FROM student_achievements WHERE mentor_emp_id = ?", 1),
    }


def _temp_password() -> str:
    return secrets.token_urlsafe(7)


def add_faculty(conn, admin: User, d: Dict[str, Any]) -> Dict[str, str]:
    emp = (d.get("emp_id") or "").strip().upper()
    if not emp or not (d.get("full_name") or "").strip() or not (d.get("email") or "").strip():
        raise HTTPException(400, "Employee ID, name and email are required")
    if conn.execute("SELECT 1 FROM faculty WHERE upper(emp_id) = ? OR lower(email) = lower(?)", (emp, d["email"])).fetchone():
        raise HTTPException(409, "Employee ID or email already exists")
    conn.execute("INSERT INTO faculty (emp_id, full_name, email, phone, designation, qualification, date_of_joining) VALUES (?,?,?,?,?,?,?)",
                 (emp, d["full_name"].strip(), d["email"].strip(), d.get("phone"), d.get("designation"), d.get("qualification"), d.get("date_of_joining") or None))
    pw = _temp_password()
    set_staff_password(conn, emp, pw)
    audit(conn, admin.id, "ADD", "faculty", emp)
    return {"emp_id": emp, "temp_password": pw}


def update_faculty(conn, admin: User, emp_id: str, d: Dict[str, Any]):
    if not conn.execute("SELECT 1 FROM faculty WHERE emp_id = ?", (emp_id,)).fetchone():
        raise HTTPException(404, "Faculty not found")
    allowed = ("full_name", "email", "phone", "designation", "qualification", "date_of_joining", "status")
    sets = {k: d[k] for k in allowed if d.get(k) not in (None, "")}
    if sets.get("status") == "Relieved":
        tutor = conn.execute("SELECT class_code FROM classes WHERE tutor_id = ?", (emp_id,)).fetchall()
        if tutor:
            raise HTTPException(400, "Assign another tutor to " + ", ".join(t[0] for t in tutor) + " before relieving this faculty")
    if sets:
        conn.execute(f"UPDATE faculty SET {', '.join(k + ' = ?' for k in sets)} WHERE emp_id = ?", [*sets.values(), emp_id])
    audit(conn, admin.id, "UPDATE", "faculty", emp_id)


def set_roles(conn, admin: User, emp_id: str, roles: List[Dict[str, Any]]):
    if not conn.execute("SELECT 1 FROM faculty WHERE emp_id = ?", (emp_id,)).fetchone():
        raise HTTPException(404, "Faculty not found")
    clean = []
    for r in roles:
        role = (r.get("role") or "").upper()
        if role not in ("ADMIN", "HOD", "PC"):
            raise HTTPException(400, f"Unknown role {role} (Tutor is set on the class)")
        prog, grp = r.get("programme") or None, r.get("grp") or None
        if role == "PC":
            if prog not in ("UG", "PG") or (prog == "UG" and grp not in ("G1", "G2")):
                raise HTTPException(400, "Programme Coordinator needs UG + G1/G2, or PG")
            if prog == "PG":
                grp = None
        else:
            prog = grp = None
        clean.append((role, prog, grp))
    if emp_id == admin.id and not any(c[0] == "ADMIN" for c in clean):
        raise HTTPException(400, "You cannot remove your own Admin role")
    conn.execute("DELETE FROM role_assignments WHERE emp_id = ?", (emp_id,))
    for role, prog, grp in set(clean):
        conn.execute("INSERT INTO role_assignments (emp_id, role, programme, grp) VALUES (?,?,?,?)", (emp_id, role, prog, grp))
    audit(conn, admin.id, "ROLES", "faculty", emp_id, str(clean))


def reset_password(conn, admin: User, emp_id: str) -> str:
    from backend.demo.mode import enabled as demo_enabled
    if demo_enabled():
        raise HTTPException(403, "Passwords cannot be reset in the demo.")
    if not conn.execute("SELECT 1 FROM faculty WHERE emp_id = ?", (emp_id,)).fetchone():
        raise HTTPException(404, "Faculty not found")
    pw = _temp_password()
    set_staff_password(conn, emp_id, pw)
    audit(conn, admin.id, "RESET_PASSWORD", "faculty", emp_id)
    return pw


def upload_faculty(conn, admin: User, content: bytes) -> Dict[str, Any]:
    added = updated = 0
    errors, credentials = [], []
    for n, rec in enumerate((_row(r) for r in read_xlsx(content)), 2):
        d = {"emp_id": _pick(rec, "Employee ID", "Emp ID"), "full_name": _pick(rec, "Full Name", "Name"), "email": _pick(rec, "Email"),
             "phone": _pick(rec, "Phone"), "designation": _pick(rec, "Designation"), "qualification": _pick(rec, "Qualification"),
             "date_of_joining": _pick(rec, "Date of Joining")[:10]}
        conn.execute("SAVEPOINT s")
        try:
            if conn.execute("SELECT 1 FROM faculty WHERE upper(emp_id) = upper(?)", (d["emp_id"],)).fetchone():
                update_faculty(conn, admin, d["emp_id"].upper(), {k: v for k, v in d.items() if k != "emp_id"})
                updated += 1
            else:
                credentials.append(add_faculty(conn, admin, d))
                added += 1
            conn.execute("RELEASE s")
        except HTTPException as e:
            conn.execute("ROLLBACK TO s")
            conn.execute("RELEASE s")
            errors.append({"row": n, "emp_id": d["emp_id"], "message": e.detail})
    return {"added": added, "updated": updated, "errors": errors, "credentials": credentials}


def form_choices(conn) -> str:
    rows = conn.execute("SELECT emp_id, full_name FROM faculty WHERE status = 'Active' AND emp_id != 'ADMIN' ORDER BY full_name").fetchall()
    body = "".join(f'  "{r["emp_id"]} - {r["full_name"]}",\n' for r in rows)
    return f"const FACULTY_CHOICES = [\n{body}];\n"
