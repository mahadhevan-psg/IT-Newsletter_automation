"""The Reports view for the Admin, HoD and programme coordinators: pick a kind of work (patents, hackathons, awards, journal papers ...)
and see every one of them across the department. The filters describe the WORK (year, level, status, indexing, funding ...), never a person.

A kind of work is (form, category): the categories are the ones on the forms, so a new category added to a form appears here
by itself. Rows are formatted by the same builders the person pages use, so a card looks the same in both views.
"""
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from backend.master.auth import User
from backend.master.ingest import specs
from backend.master import answers
from backend.master.profiles import (_categories, _event_items, form_title, _faculty_ach_items, _outreach_items, _research_items, _student_item,
                                     _student_rows)

# group id (= form_type) -> (form id, detail table, alias, column searched by the text box besides the title). Headings are the forms' titles.
GROUPS = {
    "RESEARCH": ("form_research", "research_outputs", "r", "r.venue_publisher"),
    "FACULTY": ("form_faculty", "faculty_achievements", "fa", "fa.host_org"),
    "DEPARTMENT": ("form_departmental", "department_highlights", "d", "d.partner_bodies"),
    "OUTREACH": ("form_industry", "outreach_activities", "o", "g.name"),
    "STUDENT": ("form_student", "student_achievements", "sa", "sa.organizer"),
}

# Work-specific filters on what the forms ask. select = one of the form's own choices; has = a "tick several" answer that includes the choice;
# min = at least this number. A select with no choices in the current form is not offered.
FILTERS = {
    "RESEARCH": [("indexing", "r.indexing", "Indexing", "has"), ("quartile", "r.quartile", "Quartile", "select"), ("conference_level", "r.conference_level", "Conference type", "select"),
                 ("current_status", "r.current_status", "Status", "select"), ("min_funding", "r.funding_amount", "Amount at least (₹)", "min")],
    "FACULTY": [("level", "fa.level", "Level", "select"), ("recognition_type", "fa.recognition_type", "Type", "select"), ("min_hours", "fa.duration_hours", "Hours at least", "min")],
    "DEPARTMENT": [("highlight_type", "d.highlight_type", "Nature of visit", "select"), ("min_participants", "d.participant_count", "Participants at least", "min")],
    "OUTREACH": [("activity_format", "o.activity_format", "Nature of the session", "select"), ("min_attendance", "o.actual_count", "Students attended at least", "min")],
    "STUDENT": [("entry_kind", "sa.entry_kind", "Achievement or participation", "select"), ("level", "sa.level", "Level", "select"), ("min_prize", "sa.prize_amount", "Award amount at least (₹)", "min")],
}
EXTRA_OPTIONS = {("STUDENT", "entry_kind"): [("ACHIEVEMENT", "Achievement (won / ranked / awarded)"), ("PARTICIPATION", "Participation only")]}
# the date column the date range applies to (the form's own main date is already copied to form_submissions.event_date)
DATE_COL = "fs.event_date"


def _scope(user: User, where: list, args: list) -> None:
    """Only the Admin, HoD and programme coordinators have this view; they see the whole department."""
    if not (user.all_access or "PC" in user.roles):
        raise HTTPException(403, "Reports are for the Admin, the HoD and programme coordinators")


def _options(form_id: str, group: str, param: str) -> List[Dict[str, str]]:
    if (group, param) in EXTRA_OPTIONS:
        return [{"value": v, "label": l} for v, l in EXTRA_OPTIONS[(group, param)]]
    qs = [q for q in specs()["forms"][form_id]["questions"] if q.get("key") == param]
    current = [q for q in qs if not q.get("legacy")] or qs                      # the filter lists what the current form offers (a question can recur in several categories)
    choices = list(dict.fromkeys(c for q in current for c in q.get("choices", [])))
    return [{"value": c, "label": c} for c in choices]


def _filter_defs(group: str) -> List[Dict[str, Any]]:
    form_id = GROUPS[group][0]
    out = []
    for param, _col, label, kind in FILTERS[group]:
        if kind == "min":
            out.append({"param": param, "label": label, "type": "min"})
            continue
        options = _options(form_id, group, param)
        if options:
            out.append({"param": param, "label": label, "type": "select", "options": options})
    return out


def catalog(conn, user: User, ay: Optional[str] = None) -> Dict[str, Any]:
    """Every kind of work with how many there are (for the chosen academic year, or all), plus each group's filters."""
    counts: Dict[tuple, int] = {}
    where, args = ["1=1"], []
    if ay:
        where.append("fs.ay_id = ?")
        args.append(ay)
    _scope(user, where, args)
    sql = f"SELECT fs.form_type, fs.category, COUNT(*) FROM form_submissions fs WHERE {' AND '.join(where)} GROUP BY fs.form_type, fs.category"
    for ft, cat, n in conn.execute(sql, args):
        counts[(ft, cat)] = n
    groups = []
    for gid, (form_id, *_rest) in GROUPS.items():
        title = form_title(form_id)
        order = _categories(form_id)
        cats = order + [c for (ft, c) in counts if ft == gid and c not in order and c]
        types = [{"category": c, "label": c, "count": counts.get((gid, c), 0)} for c in cats]
        groups.append({"id": gid, "title": title, "count": sum(t["count"] for t in types), "types": types, "filters": _filter_defs(gid),
                       "columns": column_catalog(gid), "default_columns": DEFAULT_COLUMNS})
    return {"groups": groups, "total": sum(g["count"] for g in groups)}


def _join(group: str) -> str:
    _form, table, alias, _text = GROUPS[group]
    return f"JOIN {table} {alias} USING (submission_id)" + (" LEFT JOIN organizations g ON g.org_id = o.partner_org_id" if group == "OUTREACH" else "")


def _where(group: str, category: str, f: Dict[str, Any], user: Optional[User] = None):
    """The WHERE clause (and bound values) for one kind of work plus the work filters. Shared by the list and the CSV export."""
    text_col = GROUPS[group][3]
    where, args = ["fs.form_type = ?"], [group]
    if category:
        where.append("fs.category = ?")
        args.append(category)
    if f.get("ay_id"):
        where.append("fs.ay_id = ?")
        args.append(f["ay_id"])
    if f.get("date_from"):
        where.append(f"{DATE_COL} >= ?")
        args.append(f["date_from"])
    if f.get("date_to"):
        where.append(f"{DATE_COL} <= ?")
        args.append(f["date_to"])
    if f.get("q"):
        where.append(f"(fs.title LIKE ? OR {text_col} LIKE ?)")
        args += [f"%{f['q']}%"] * 2
    if f.get("has_media"):
        where.append("fs.media_url IS NOT NULL AND fs.media_url != ''")
    for param, col, _label, kind in FILTERS[group]:                       # columns come from this table only, values are always bound
        v = f.get(param)
        if v in (None, ""):
            continue
        if kind == "min":
            try:
                num = float(v)
            except ValueError:
                raise HTTPException(400, f"'{v}' is not a number")
            where.append(f"{col} >= ?")
            args.append(num)
        elif kind == "has":                                              # "Scopus, Web of Science": matched as a whole item of the list
            where.append(f"instr(', ' || {col} || ', ', ?) > 0")
            args.append(f", {v}, ")
        else:
            where.append(f"{col} = ?")
            args.append(v)
    if user is not None:
        _scope(user, where, args)
    if group == "STUDENT" and f.get("class_id"):                          # the class the students were in when it happened
        if user is not None and not user.sees_class(int(f["class_id"])) and not (user.all_access or "PC" in user.roles):
            raise HTTPException(403, "That class is outside your scope")
        where.append("fs.submission_id IN (SELECT submission_id FROM student_achievement_participants WHERE class_id_snapshot = ?)")
        args.append(int(f["class_id"]))

    return where, args


def list_works(conn, user: User, group: str, category: str, f: Dict[str, Any], limit: int = 50, offset: int = 0) -> Dict[str, Any]:
    if group not in GROUPS:
        raise HTTPException(400, "Unknown kind of work")
    title = form_title(GROUPS[group][0])
    where, args = _where(group, category, f, user)
    base = f"FROM form_submissions fs {_join(group)} WHERE {' AND '.join(where)}"
    total = conn.execute(f"SELECT COUNT(*) {base}", args).fetchone()[0]
    ids = [r[0] for r in conn.execute(f"SELECT fs.submission_id {base} ORDER BY fs.event_date DESC, fs.submission_id DESC LIMIT ? OFFSET ?", args + [limit, offset])]
    items = _build(conn, group, ids)
    for i in items:
        i["role"] = None
    return {"group": group, "category": category, "title": category or title, "total": total, "items": items,
            "stats": _stats(conn, group, base, args)}


def _build(conn, group: str, ids: List[int]) -> List[Dict[str, Any]]:
    if not ids:
        return []
    where, args = f"fs.submission_id IN ({','.join('?' * len(ids))})", list(ids)
    if group == "RESEARCH":
        items = _research_items(conn, where, args, {"match": "1 = 0", "submitter": None})
    elif group == "FACULTY":
        items = _faculty_ach_items(conn, where, args, people=True)
    elif group == "DEPARTMENT":
        items = _event_items(conn, where, args)
    elif group == "OUTREACH":
        items = _outreach_items(conn, where, args)
    else:
        items = [_student_item(r, "Team") for r in _student_rows(conn, where, args)]
    order = {sid: n for n, sid in enumerate(ids)}
    return sorted(items, key=lambda i: order[i["id"]])                    # the builders sort by date only; keep the listing order


def _stats(conn, group: str, base: str, args: list) -> List[Dict[str, Any]]:
    """A couple of totals over the WHOLE filtered set (not just the page shown)."""
    one = lambda expr: conn.execute(f"SELECT {expr} {base}", args).fetchone()[0]
    out = []
    if group == "RESEARCH":
        out += [{"label": "Total funding (₹)", "value": one("COALESCE(SUM(r.funding_amount), 0)")}, {"label": "Scopus / WoS indexed", "value": one("COALESCE(SUM(r.indexing LIKE '%Scopus%' OR r.indexing LIKE '%Web of Science%'), 0)")}]
    elif group == "DEPARTMENT":
        out += [{"label": "Total participants", "value": one("COALESCE(SUM(d.participant_count), 0)")}, {"label": "Total budget (₹)", "value": one("COALESCE(SUM(d.budget_amount), 0)")}]
    elif group == "OUTREACH":
        out += [{"label": "Students attended", "value": one("COALESCE(SUM(o.actual_count), 0)")}, {"label": "Partner organisations", "value": one("COUNT(DISTINCT o.partner_org_id)")}]
    elif group == "STUDENT":
        out += [{"label": "Prize money (₹)", "value": one("COALESCE(SUM(sa.prize_amount), 0)")},
                {"label": "Students involved", "value": conn.execute(f"SELECT COUNT(DISTINCT p.roll_no) FROM student_achievement_participants p WHERE p.roll_no IS NOT NULL AND p.submission_id IN (SELECT fs.submission_id {base})", args).fetchone()[0]}]
    elif group == "FACULTY":
        out += [{"label": "Lecture hours", "value": one("COALESCE(SUM(fa.duration_hours), 0)")}]
    return out


# ---------------------------------------------------------------- CSV export: the user picks the columns
_INVOLVED_NAMES = ("(SELECT group_concat(f2.full_name, '; ') FROM submission_faculty sf2 JOIN faculty f2 ON f2.emp_id = sf2.emp_id "
                   "WHERE sf2.submission_id = fs.submission_id AND sf2.role = 'Involved')")


def _c(key, label, expr, part):
    return {"key": key, "label": label, "expr": expr, "part": part}


_COMMON = [
    _c("kind", "Category", "fs.category", "Basics"), _c("title", "Title", "fs.title", "Basics"), _c("date", "Date", "fs.event_date", "Basics"),
    _c("ay", "Academic year", "fs.ay_id", "Basics"),
    _c("submitted_by", "Entered by (faculty)", "u.full_name", "Submission"), _c("submitter_email", "Faculty e-mail", "fs.submitter_email", "Submission"),
    _c("submitted_on", "Entered on", "fs.submitted_at", "Submission"),
]
_PARTICIPANTS = "FROM student_achievement_participants p WHERE p.submission_id = fs.submission_id"
# people are looked up in the records (names and classes), not copied from what was typed
PEOPLE_COLUMNS: Dict[str, List[Dict[str, str]]] = {
    "RESEARCH": [
        _c("authors", "Authors (in order)", "(SELECT group_concat(COALESCE(f.full_name, s.full_name, c.name) || CASE c.person_type WHEN 'EXTERNAL' THEN ' (ext.)' ELSE '' END, '; ') "
           "FROM research_contributors c LEFT JOIN faculty f ON f.emp_id = c.emp_id LEFT JOIN students s ON s.roll_no = c.roll_no WHERE c.submission_id = fs.submission_id)", "People"),
        _c("n_authors", "Number of authors", "(SELECT COUNT(*) FROM research_contributors c WHERE c.submission_id = fs.submission_id)", "People"),
        _c("faculty_ids", "Faculty authors (employee IDs)", "(SELECT group_concat(c.emp_id, '; ') FROM research_contributors c WHERE c.submission_id = fs.submission_id AND c.person_type = 'FACULTY')", "People"),
        _c("student_rolls", "Student authors (roll numbers)", "(SELECT group_concat(c.roll_no, '; ') FROM research_contributors c WHERE c.submission_id = fs.submission_id AND c.person_type = 'STUDENT')", "People"),
    ],
    "FACULTY": [_c("faculty", "Faculty name", "fu.full_name", "People"), _c("faculty_id", "Faculty employee ID", "fa.emp_id", "People"),
                _c("designation", "Designation at the time", "fa.designation_at_time", "People")],
    "DEPARTMENT": [_c("convener", "Faculty who entered it", "cf.full_name", "People"), _c("convener_id", "Their employee ID", "d.convener_emp_id", "People")],
    "OUTREACH": [_c("lead", "Faculty who entered it", "lf.full_name", "People"), _c("lead_id", "Their employee ID", "o.lead_emp_id", "People")],
    "STUDENT": [
        _c("students", "Students (name and roll no.)", "(SELECT group_concat(COALESCE(s.full_name, p.name, p.raw_text) || ' (' || COALESCE(p.roll_no, '?') || ')', '; ') FROM student_achievement_participants p "
           "LEFT JOIN students s ON s.roll_no = p.roll_no WHERE p.submission_id = fs.submission_id)", "People"),
        _c("rolls", "Roll numbers", f"(SELECT group_concat(p.roll_no, '; ') {_PARTICIPANTS} AND p.roll_no IS NOT NULL)", "People"),
        _c("n_students", "Number of students", f"(SELECT COUNT(*) {_PARTICIPANTS})", "People"),
        _c("classes", "Class at the time", "(SELECT group_concat(code, '; ') FROM (SELECT DISTINCT c.class_code AS code FROM student_achievement_participants p JOIN classes c ON c.class_id = p.class_id_snapshot "
           "WHERE p.submission_id = fs.submission_id))", "People"),
        _c("mentor", "Faculty mentor", "mf.full_name", "People"),
    ],
}
_EXPORT_JOINS = {"RESEARCH": "", "FACULTY": " LEFT JOIN faculty fu ON fu.emp_id = fa.emp_id", "DEPARTMENT": " LEFT JOIN faculty cf ON cf.emp_id = d.convener_emp_id",
                 "OUTREACH": " LEFT JOIN faculty lf ON lf.emp_id = o.lead_emp_id", "STUDENT": " LEFT JOIN faculty mf ON mf.emp_id = sa.mentor_emp_id"}


def columns_for(group: str) -> List[Dict[str, Any]]:
    """Every column of a group's download: the fixed ones, then one per field of the published form."""
    return _COMMON + PEOPLE_COLUMNS[group] + answers.report_columns(GROUPS[group][0])


DEFAULT_COLUMNS = ["kind", "title", "date", "ay"]
EXPORT_LIMIT = 50000


def column_catalog(group: str) -> List[Dict[str, str]]:
    """What the pick-columns dialog shows: key, label and the part of the form it belongs to (never the SQL)."""
    return [{"key": c["key"], "label": c["label"], "part": c["part"]} for c in columns_for(group)]


def _safe(v):
    """Spreadsheet programs run text that starts with = + - @ as a formula, and the form answers are typed by anyone: defuse them."""
    return "'" + v if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r") else v


def export_csv(conn, user: User, group: str, category: str, f: Dict[str, Any], columns: List[str]) -> bytes:
    import csv
    import io
    if group not in GROUPS:
        raise HTTPException(400, "Unknown kind of work")
    by_key = {c["key"]: c for c in columns_for(group)}
    bad = [k for k in columns if k not in by_key]
    if bad or not columns:
        raise HTTPException(400, "Choose at least one column" if not columns else "Unknown column: " + ", ".join(bad))
    where, args = _where(group, category, f, user)
    chosen = list(dict.fromkeys(columns))                                  # the caller's order, no repeats
    stored = [k for k in chosen if "expr" in by_key[k]]
    select = ", ".join(["fs.submission_id", *(by_key[k]["expr"] for k in stored)])
    sql = (f"SELECT {select} FROM form_submissions fs {_join(group)}{_EXPORT_JOINS[group]} "
           f"LEFT JOIN faculty u ON u.emp_id = fs.submitter_emp_id WHERE {' AND '.join(where)} ORDER BY fs.event_date DESC, fs.submission_id DESC LIMIT {EXPORT_LIMIT}")
    rows = conn.execute(sql, args).fetchall()
    entered = answers.raw_of(conn, [r[0] for r in rows]) if len(stored) < len(chosen) else {}        # the form fields come from the stored answers
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([by_key[k]["label"] for k in chosen])
    for row in rows:
        values = dict(zip(stored, row[1:]))
        _type, category_of_row, raw = entered.get(row[0], (None, None, {}))
        w.writerow([_safe(values[k] if k in values else answers.value_for(by_key[k], category_of_row, raw)) for k in chosen])
    return ("\ufeff" + buf.getvalue()).encode("utf-8")                    # the BOM makes Excel read ₹ and Tamil names correctly
