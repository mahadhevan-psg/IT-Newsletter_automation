"""The Reports view for the Admin, HoD and programme coordinators: pick a kind of work (patents, hackathons, awards, journal papers ...)
and see every one of them across the department. The filters describe the WORK (year, level, status, indexing, funding ...), never a person.

A kind of work is (form, category): the categories are the ones on the forms, so a new category added to a form appears here
by itself. Rows are formatted by the same builders the person pages use, so a card looks the same in both views.
"""
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from backend.master.auth import User
from backend.master.ingest import specs
from backend.master.profiles import (LABELS, _categories, _event_items, _faculty_ach_items, _outreach_items, _research_items, _student_item,
                                     _student_rows)

# group id (= form_type) -> (heading, form id, detail table, alias, column searched by the text box besides the title)
GROUPS = {
    "RESEARCH": ("Research & Innovation", "form_research", "research_outputs", "r", "r.venue_publisher"),
    "FACULTY": ("Faculty achievements", "form_faculty", "faculty_achievements", "fa", "fa.host_org"),
    "DEPARTMENT": ("Departmental highlights", "form_departmental", "department_highlights", "d", "d.partner_bodies"),
    "OUTREACH": ("Industry, alumni & outreach", "form_industry", "outreach_activities", "o", "g.name"),
    "STUDENT": ("Student achievements", "form_student", "student_achievements", "sa", "sa.organizer"),
}

# Work-specific filters. select = equals one of the form's own choices; min = at least this number.
FILTERS = {
    "RESEARCH": [("current_status", "r.current_status", "Status", "select"), ("indexing", "r.indexing", "Indexing", "select"), ("quartile", "r.quartile", "Quartile", "select"),
                 ("conference_level", "r.conference_level", "Conference level", "select"), ("review_status", "r.review_status", "Review status", "select"),
                 ("funding_status", "r.funding_status", "Funding", "select"), ("min_funding", "r.funding_amount", "Funding at least (₹)", "min")],
    "FACULTY": [("level", "fa.level", "Level", "select"), ("recognition_type", "fa.recognition_type", "Type of recognition", "select"),
                ("min_hours", "fa.duration_hours", "Hours at least", "min")],
    "DEPARTMENT": [("impl_status", "d.impl_status", "Status", "select"), ("highlight_type", "d.highlight_type", "Highlight type", "select"),
                   ("min_participants", "d.participant_count", "Participants at least", "min")],
    "OUTREACH": [("activity_format", "o.activity_format", "Format", "select"), ("partner_type", "o.partner_type", "Partner type", "select"),
                 ("min_attendance", "o.actual_count", "Attendance at least", "min")],
    "STUDENT": [("entry_kind", "sa.entry_kind", "Achievement or participation", "select"), ("level", "sa.level", "Level", "select"), ("domain", "sa.domain", "Domain", "select"),
                ("min_prize", "sa.prize_amount", "Prize at least (₹)", "min")],
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
    q = next((q for q in specs()["forms"][form_id]["questions"] if q.get("key") == param), None)
    return [{"value": c, "label": c} for c in (q or {}).get("choices", [])]


def _filter_defs(group: str) -> List[Dict[str, Any]]:
    form_id = GROUPS[group][1]
    return [{"param": p, "label": label, "type": kind, **({"options": _options(form_id, group, p)} if kind == "select" else {})} for p, _col, label, kind in FILTERS[group]]


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
    for gid, (title, form_id, *_rest) in GROUPS.items():
        order = _categories(form_id)
        cats = order + [c for (ft, c) in counts if ft == gid and c not in order and c]
        types = [{"category": c, "label": LABELS.get(c, c), "count": counts.get((gid, c), 0)} for c in cats]
        groups.append({"id": gid, "title": title, "count": sum(t["count"] for t in types), "types": types, "filters": _filter_defs(gid),
                       "columns": column_catalog(gid), "default_columns": DEFAULT_COLUMNS})
    return {"groups": groups, "total": sum(g["count"] for g in groups)}


def _join(group: str) -> str:
    _title, _form, table, alias, _text = GROUPS[group]
    return f"JOIN {table} {alias} USING (submission_id)" + (" LEFT JOIN organizations g ON g.org_id = o.partner_org_id" if group == "OUTREACH" else "")


def _where(group: str, category: str, f: Dict[str, Any], user: Optional[User] = None):
    """The WHERE clause (and bound values) for one kind of work plus the work filters. Shared by the list and the CSV export."""
    title, form_id, table, alias, text_col = GROUPS[group]
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
    title, form_id, table, alias, text_col = GROUPS[group]
    where, args = _where(group, category, f, user)
    base = f"FROM form_submissions fs {_join(group)} WHERE {' AND '.join(where)}"
    total = conn.execute(f"SELECT COUNT(*) {base}", args).fetchone()[0]
    ids = [r[0] for r in conn.execute(f"SELECT fs.submission_id {base} ORDER BY fs.event_date DESC, fs.submission_id DESC LIMIT ? OFFSET ?", args + [limit, offset])]
    items = _build(conn, group, ids)
    for i in items:
        i["role"] = None
    return {"group": group, "category": category, "title": LABELS.get(category, category) if category else title, "total": total, "items": items,
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
        out += [{"label": "Total funding (₹)", "value": one("COALESCE(SUM(r.funding_amount), 0)")}, {"label": "Scopus / WoS indexed", "value": one("COALESCE(SUM(r.indexing IN ('Scopus','Web of Science')), 0)")}]
    elif group == "DEPARTMENT":
        out += [{"label": "Total participants", "value": one("COALESCE(SUM(d.participant_count), 0)")}, {"label": "Total budget (₹)", "value": one("COALESCE(SUM(d.budget_amount), 0)")}]
    elif group == "OUTREACH":
        out += [{"label": "Total attendance", "value": one("COALESCE(SUM(o.actual_count), 0)")}, {"label": "Partner organisations", "value": one("COUNT(DISTINCT o.partner_org_id)")}]
    elif group == "STUDENT":
        out += [{"label": "Prize money (₹)", "value": one("COALESCE(SUM(sa.prize_amount), 0)")},
                {"label": "Students involved", "value": conn.execute(f"SELECT COUNT(DISTINCT p.roll_no) FROM student_achievement_participants p WHERE p.roll_no IS NOT NULL AND p.submission_id IN (SELECT fs.submission_id {base})", args).fetchone()[0]}]
    elif group == "FACULTY":
        out += [{"label": "Training hours", "value": one("COALESCE(SUM(fa.duration_hours), 0)")}]
    return out


# ---------------------------------------------------------------- CSV export: the user picks the columns
YN = lambda col: f"CASE WHEN {col} IS NULL THEN NULL WHEN {col} THEN 'Yes' ELSE 'No' END"
_INVOLVED_NAMES = ("(SELECT group_concat(f2.full_name, '; ') FROM submission_faculty sf2 JOIN faculty f2 ON f2.emp_id = sf2.emp_id "
                   "WHERE sf2.submission_id = fs.submission_id AND sf2.role = 'Involved')")


def _c(key, label, expr, part):
    return {"key": key, "label": label, "expr": expr, "part": part}


def _col(table_alias, column, key, label, part="Details"):
    return _c(key, label, f"{table_alias}.{column}", part)


_COMMON = [
    _c("kind", "Kind of work", "fs.category", "Basics"), _c("title", "Title", "fs.title", "Basics"), _c("date", "Date", "fs.event_date", "Basics"),
    _c("ay", "Academic year", "fs.ay_id", "Basics"), _c("badge", "Impact badge / tag", "fs.badge_tag", "Basics"),
    _c("submitted_by", "Submitted by (faculty)", "u.full_name", "Submission"), _c("submitter_email", "Submitter e-mail", "fs.submitter_email", "Submission"),
    _c("submitted_on", "Submitted on", "fs.submitted_at", "Submission"), _c("publish", "Permission to publish", YN("fs.publish_permission"), "Submission"),
    _c("evidence", "Evidence link", "fs.evidence_url", "Links"), _c("photo", "Photo link", "fs.media_url", "Links"), _c("photo_caption", "Photo caption", "fs.photo_caption", "Links"),
]

COLUMNS: Dict[str, List[Dict[str, str]]] = {
    "RESEARCH": _COMMON + [
        _c("authors", "Authors (in order)", "(SELECT group_concat(COALESCE(f.full_name, s.full_name, c.name) || CASE c.person_type WHEN 'EXTERNAL' THEN ' (ext.)' ELSE '' END, '; ') "
           "FROM research_contributors c LEFT JOIN faculty f ON f.emp_id = c.emp_id LEFT JOIN students s ON s.roll_no = c.roll_no WHERE c.submission_id = fs.submission_id)", "People"),
        _c("n_authors", "Number of authors", "(SELECT COUNT(*) FROM research_contributors c WHERE c.submission_id = fs.submission_id)", "People"),
        _c("faculty_ids", "Faculty authors (employee IDs)", "(SELECT group_concat(c.emp_id, '; ') FROM research_contributors c WHERE c.submission_id = fs.submission_id AND c.person_type = 'FACULTY')", "People"),
        _c("student_rolls", "Student authors (roll numbers)", "(SELECT group_concat(c.roll_no, '; ') FROM research_contributors c WHERE c.submission_id = fs.submission_id AND c.person_type = 'STUDENT')", "People"),
        _col("r", "current_status", "status", "Status"), _col("r", "venue_publisher", "venue", "Venue / publisher / funding agency"), _col("r", "venue_url", "venue_url", "Venue website", "Links"),
        _col("r", "identifier", "identifier", "DOI / ISBN / ISSN / patent no. / grant ref."), _col("r", "indexing", "indexing", "Indexing"), _col("r", "quartile", "quartile", "Quartile"),
        _col("r", "impact_factor", "impact_factor", "Impact factor", "Numbers"), _col("r", "conference_level", "conference_level", "Conference level"), _col("r", "review_status", "review_status", "Review status"),
        _col("r", "funding_status", "funding_status", "Funding status"), _col("r", "funding_amount", "funding_amount", "Funding amount (₹)", "Numbers"), _col("r", "project_start", "project_start", "Project start date"),
        _col("r", "collaborators", "collaborators", "Collaborating institutions"), _col("r", "contribution_statement", "contribution", "Individual contribution"), _col("r", "problem", "problem", "Research problem"),
        _col("r", "abstract", "abstract", "Abstract"), _col("r", "methodology", "methodology", "Methodology"), _col("r", "key_findings", "key_findings", "Key findings / novelty"),
        _col("r", "impact", "impact", "Impact and beneficiaries"), _col("r", "ip_status", "ip_status", "IP / licensing status"), _col("r", "dataset_url", "dataset_url", "Dataset / code link", "Links"),
        _col("r", "related_refs", "related_refs", "Related publications"),
    ],
    "FACULTY": _COMMON + [
        _c("faculty", "Faculty name", "fu.full_name", "People"), _col("fa", "emp_id", "faculty_id", "Faculty employee ID", "People"), _col("fa", "designation_at_time", "designation", "Designation at the time", "People"),
        _col("fa", "other_contributors", "other_contributors", "Other contributors", "People"), _c("team", "Individual or team", "CASE fa.is_team WHEN 1 THEN 'Team' WHEN 0 THEN 'Individual' END", "People"),
        _col("fa", "recognition_type", "recognition_type", "Type of recognition"), _col("fa", "host_org", "host_org", "Awarding body / host"), _col("fa", "level", "level", "Level"),
        _col("fa", "start_date", "start_date", "Start date"), _col("fa", "end_date", "end_date", "End date"), _col("fa", "city_venue", "city", "City / venue"), _col("fa", "credential_no", "credential", "Credential / certificate no."),
        _col("fa", "duration_hours", "hours", "Duration / training hours", "Numbers"), _col("fa", "role_contribution", "role_contribution", "Role and contribution"),
        _col("fa", "selection_criteria", "selection", "Selection criteria"), _col("fa", "description", "description", "Description"), _col("fa", "outcome_impact", "outcome", "Outcome and impact"),
        _c("prev", "Reported previously", YN("fa.previously_reported"), "Details"), _col("fa", "extra_notes", "notes", "Notes for the review team"), _col("fa", "organizer_url", "organizer_url", "Organiser website", "Links"),
    ],
    "DEPARTMENT": _COMMON + [
        _c("convener", "Convener", "cf.full_name", "People"), _col("d", "convener_emp_id", "convener_id", "Convener employee ID", "People"), _c("involved", "Other faculty involved", _INVOLVED_NAMES, "People"),
        _col("d", "units_involved", "units", "Departments / units involved", "People"), _col("d", "highlight_type", "highlight_type", "Highlight type"), _col("d", "impl_status", "status", "Implementation status"),
        _col("d", "start_date", "start_date", "Start date"), _col("d", "end_date", "end_date", "End date"), _col("d", "venue", "venue", "Venue"), _col("d", "partner_bodies", "partner_bodies", "Partner / funding bodies"),
        _col("d", "target_audience", "audience", "Target audience"), _col("d", "participant_count", "participants", "Participants", "Numbers"), _col("d", "budget_amount", "budget", "Budget (₹)", "Numbers"),
        _col("d", "funding_source", "funding_source", "Funding source"), _col("d", "overview", "overview", "Overview"), _col("d", "objectives", "objectives", "Objectives"), _col("d", "outputs", "outputs", "Key outputs"),
        _col("d", "success_indicators", "success", "Success indicators"), _col("d", "infra_upgrade", "infra", "Infrastructure upgrade details"), _col("d", "accreditation_link", "accreditation", "Accreditation linkage"),
        _col("d", "challenges", "challenges", "Challenges and mitigation"), _col("d", "sustainability", "sustainability", "Sustainability plan"), _col("d", "recognition", "recognition", "Recognition / external validation"),
        _col("d", "related_initiatives", "related", "Related initiatives"), _col("d", "report_url", "report_url", "Event report link", "Links"),
    ],
    "OUTREACH": _COMMON + [
        _c("lead", "Lead coordinator", "lf.full_name", "People"), _col("o", "lead_emp_id", "lead_id", "Lead employee ID", "People"), _c("involved", "Other faculty involved", _INVOLVED_NAMES, "People"),
        _col("o", "units_involved", "units", "Departments / units involved", "People"), _c("partner", "Partner organisation", "g.name", "Details"), _col("o", "partner_type", "partner_type", "Partner type"),
        _col("o", "activity_format", "format", "Activity format"), _col("o", "start_date", "start_date", "Start date"), _col("o", "end_date", "end_date", "End date"), _col("o", "venue", "venue", "Venue"),
        _col("o", "target_audience", "audience", "Target audience"), _col("o", "expected_count", "expected", "Expected participants", "Numbers"), _col("o", "actual_count", "attendance", "Actual attendance", "Numbers"),
        _col("o", "budget_amount", "budget", "Budget / sponsorship (₹)", "Numbers"), _col("o", "objective", "objective", "Objective"), _col("o", "summary_outcomes", "summary", "Summary and outcomes"),
        _col("o", "agenda", "agenda", "Agenda"), _col("o", "speakers", "speakers", "Speakers / representatives"), _col("o", "mou_scope", "mou_scope", "MoU scope"),
        _col("o", "agreement_effective", "agreement_from", "Agreement effective date"), _col("o", "agreement_expiry", "agreement_to", "Agreement expiry date"), _col("o", "follow_up", "follow_up", "Follow-up commitments"),
        _col("o", "measurable_outcomes", "measurable", "Measurable outcomes"), _col("o", "feedback_summary", "feedback", "Feedback summary"), _col("o", "report_url", "report_url", "Report link", "Links"),
    ],
    "STUDENT": _COMMON + [
        _c("students", "Students (name and roll no.)", "(SELECT group_concat(COALESCE(s.full_name, p.name, p.raw_text) || ' (' || COALESCE(p.roll_no, '?') || ')', '; ') FROM student_achievement_participants p "
           "LEFT JOIN students s ON s.roll_no = p.roll_no WHERE p.submission_id = fs.submission_id)", "People"),
        _c("rolls", "Roll numbers", "(SELECT group_concat(p.roll_no, '; ') FROM student_achievement_participants p WHERE p.submission_id = fs.submission_id AND p.roll_no IS NOT NULL)", "People"),
        _c("n_students", "Number of students", "(SELECT COUNT(*) FROM student_achievement_participants p WHERE p.submission_id = fs.submission_id)", "People"),
        _c("classes", "Class at the time", "(SELECT group_concat(code, '; ') FROM (SELECT DISTINCT c.class_code AS code FROM student_achievement_participants p JOIN classes c ON c.class_id = p.class_id_snapshot "
           "WHERE p.submission_id = fs.submission_id))", "People"),
        _c("mentor", "Faculty mentor", "mf.full_name", "People"), _col("sa", "mentor_emp_id", "mentor_id", "Mentor employee ID", "People"),
        _c("entry", "Achievement or participation", "CASE sa.entry_kind WHEN 'PARTICIPATION' THEN 'Participation' ELSE 'Achievement' END", "Details"),
        _c("team", "Individual or team", "CASE sa.is_team WHEN 1 THEN 'Team' ELSE 'Individual' END", "Details"), _col("sa", "organizer", "organizer", "Organiser / awarding body"), _col("sa", "level", "level", "Level"),
        _col("sa", "position", "position", "Position / rank / prize"), _col("sa", "prize_amount", "prize", "Prize / scholarship amount (₹)", "Numbers"), _col("sa", "domain", "domain", "Domain"),
        _col("sa", "event_start", "event_start", "Event start date"), _col("sa", "event_end", "event_end", "Event end date"), _col("sa", "project_statement", "statement", "Project statement"),
        _col("sa", "abstract", "abstract", "Abstract / achievement details"), _col("sa", "tools_used", "tools", "Tools / technologies"), _col("sa", "measurable_impact", "impact", "Measurable result or impact"),
        _col("sa", "learning_outcomes", "learning", "Learning outcomes"), _c("prev", "Reported previously", YN("sa.previously_reported"), "Details"), _col("sa", "related_awards", "related_awards", "Related awards"),
        _col("sa", "demo_url", "demo_url", "Demo / repository link", "Links"),
    ],
}
_EXPORT_JOINS = {"RESEARCH": "", "FACULTY": " LEFT JOIN faculty fu ON fu.emp_id = fa.emp_id", "DEPARTMENT": " LEFT JOIN faculty cf ON cf.emp_id = d.convener_emp_id",
                 "OUTREACH": " LEFT JOIN faculty lf ON lf.emp_id = o.lead_emp_id", "STUDENT": " LEFT JOIN faculty mf ON mf.emp_id = sa.mentor_emp_id"}
DEFAULT_COLUMNS = ["kind", "title", "date", "ay"]
EXPORT_LIMIT = 50000


def column_catalog(group: str) -> List[Dict[str, str]]:
    """What the pick-columns dialog shows: key, label and the part of the form it belongs to (never the SQL)."""
    return [{"key": c["key"], "label": c["label"], "part": c["part"]} for c in COLUMNS[group]]


def _safe(v):
    """Spreadsheet programs run text that starts with = + - @ as a formula, and the form answers are typed by anyone: defuse them."""
    return "'" + v if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r") else v


def export_csv(conn, user: User, group: str, category: str, f: Dict[str, Any], columns: List[str]) -> bytes:
    import csv
    import io
    if group not in GROUPS:
        raise HTTPException(400, "Unknown kind of work")
    by_key = {c["key"]: c for c in COLUMNS[group]}
    bad = [k for k in columns if k not in by_key]
    if bad or not columns:
        raise HTTPException(400, "Choose at least one column" if not columns else "Unknown column: " + ", ".join(bad))
    where, args = _where(group, category, f, user)
    chosen = list(dict.fromkeys(columns))                                  # the caller's order, no repeats
    sql = (f"SELECT {', '.join(by_key[k]['expr'] for k in chosen)} FROM form_submissions fs {_join(group)}{_EXPORT_JOINS[group]} "
           f"LEFT JOIN faculty u ON u.emp_id = fs.submitter_emp_id WHERE {' AND '.join(where)} ORDER BY fs.event_date DESC, fs.submission_id DESC LIMIT {EXPORT_LIMIT}")
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([by_key[k]["label"] for k in chosen])
    for row in conn.execute(sql, args):
        w.writerow([_safe(v) for v in row])
    return ("\ufeff" + buf.getvalue()).encode("utf-8")                    # the BOM makes Excel read ₹ and Tamil names correctly
