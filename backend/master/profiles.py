"""Person profile pages: everything one faculty member or one student has entered / taken part in, segregated.

SEGREGATION PLAN (derived from the five forms)

Faculty page                      form it comes from                              how a row is linked to the person            groups (the form's own categories)
  Research & Innovation           Research & Innovation                           listed as author (research_contributors)       Journal / Conference / Books / Patents / Funded /
                                                                                  or the one who submitted it                    Consultancy / Innovations
  Professional achievements       Faculty Achievements                            faculty_achievements.emp_id                    Awards / Certifications / Invited talks / Resource
                                                                                                                                 person / FDP attended / Professional bodies
  Events organised                Departmental Highlights                         convener, listed as involved, or submitter     Workshops & FDPs / Conferences / Infra / Clubs / Milestones
  Industry, alumni & outreach     Industry, Alumni & Outreach                     lead, listed as involved, or submitter         Visits / Expert talks / MoUs / Alumni / Community
  Students mentored               Student Achievements                            student_achievements.mentor_emp_id             the student form's categories

Student page
  Achievements                    Student Achievements, entry_kind = ACHIEVEMENT  listed participant                             Academic / Hackathons / Higher ed & placements /
  Participations                  Student Achievements, entry_kind = PARTICIPATION listed participant                            Projects / Sports & cultural
  Research & Innovation           Research & Innovation                           listed as author (by roll number)              as above
  Events attended                 Departmental + Outreach rosters                 event_participants                             Department events / Industry & outreach
  Placement                       placement tables                                the student's own rows                         Status / Offers / Internships / Interviews

Every item has one shape (title, date, badges, facts, notes, links) so the page renders them all the same way.
"""
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from backend.master.auth import User
from backend.master.ingest import specs


def inr(n) -> Optional[str]:
    """Indian digit grouping: 1200000 -> ₹12,00,000."""
    if n is None:
        return None
    s = str(int(round(abs(n))))
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ("-" if n < 0 else "") + "₹" + ",".join(parts + [tail])


def _num(n) -> str:
    return f"{n:g}" if isinstance(n, (int, float)) else str(n)


def badge(text, tone=None):
    return {"text": text, "tone": tone} if text else None


def item(sid, cat, title, date, ay, role=None, badges=(), facts=(), notes=(), links=(), landmark=False) -> Dict[str, Any]:
    return {
        "id": sid, "category": cat, "title": title, "date": date, "ay_id": ay, "role": role, "landmark": bool(landmark),
        "badges": [b for b in badges if b],
        "facts": [[k, v] for k, v in facts if v not in (None, "")],
        "notes": [[k, v] for k, v in notes if v not in (None, "")],
        "links": [{"label": k, "url": v} for k, v in links if v and str(v).startswith(("http://", "https://"))],
    }


def _categories(form_id: str) -> List[str]:
    return next((q["choices"] for q in specs()["forms"][form_id]["questions"] if q.get("key") == "category"), [])


LABELS = {  # shorter headings than the form's wording; anything not listed keeps the form's own wording
    "Journal Publications": "Journal papers", "Conference Publications": "Conference papers", "Book / Book Chapters": "Books & chapters",
    "Patents & Intellectual Property": "Patents & IP", "Funded Research Projects": "Funded projects", "Consultancy Projects": "Consultancy projects",
    "Key Research Innovations & Technical Accomplishments": "Innovations & accomplishments",
    "Awards & Honors Received": "Awards & honours", "Certifications & Upskilling Completed": "Certifications",
    "Invited Keynote / Expert Lectures Delivered": "Invited talks & keynotes", "Resource Person / Session Chair Roles": "Resource person & session chair",
    "FDP / Workshops Attended": "FDPs & workshops attended", "Professional Body & Editorial Board Roles": "Professional bodies & editorial boards",
    "Workshops & FDPs Organized": "Workshops & FDPs organised", "Conferences & Symposia Organized": "Conferences & symposia organised",
    "Infrastructure & Lab Upgrades": "Infrastructure & lab upgrades", "Student Club & Society Activities": "Club & society activities",
    "Department Statistics & Major Milestones": "Department milestones",
    "Industrial Visits & Field Tours": "Industrial visits", "Industry Expert Lectures & Technical Talks": "Industry expert talks",
    "MoUs Signed & Industrial Collaborations": "MoUs & collaborations", "Alumni Interactions & Mentorship Sessions": "Alumni interactions",
    "Community & Social Outreach Initiatives": "Community outreach",
    "Academic Excellence & Ranks": "Academic excellence & ranks", "Hackathons & Coding Competitions": "Hackathons & coding competitions",
    "Higher Education & Top Placements": "Higher education & placements", "Technical Projects & Innovations": "Technical projects & innovations",
    "Sports, Cultural & Co-Curricular Accomplishments": "Sports, cultural & co-curricular",
}


def _section(sid: str, title: str, items: List[Dict[str, Any]], order: List[str], note: str = "") -> Dict[str, Any]:
    """Split a section's items into groups: the form's categories first (in form order), then any other category."""
    cats = list(order) + [c for c in dict.fromkeys(i["category"] for i in items) if c not in order]
    groups = []
    for c in cats:
        mine = [i for i in items if i["category"] == c]
        if mine:
            groups.append({"title": LABELS.get(c, c or "Other"), "count": len(mine), "items": mine})
    return {"id": sid, "title": title, "note": note, "count": len(items), "groups": groups}


def _rows(conn, sql, args=()):
    return [dict(r) for r in conn.execute(sql, args)]


def _names(conn, ids: List[int], sql: str) -> Dict[int, List[str]]:
    """{submission_id: [names...]} for a batch of submissions."""
    out: Dict[int, List[str]] = {}
    if ids:
        for r in conn.execute(sql.replace("{IDS}", ",".join("?" * len(ids))), ids):
            out.setdefault(r[0], []).append(r[1])
    return out


# ---------------------------------------------------------------- shared item builders
def _research_items(conn, where: str, args: list, who: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = _rows(conn, f"""
        SELECT fs.submission_id, fs.ay_id, fs.event_date, fs.category, fs.title, fs.evidence_url, fs.media_url, fs.badge_tag, fs.is_landmark, fs.submitter_emp_id,
               r.current_status, r.venue_publisher, r.venue_url, r.identifier, r.indexing, r.quartile, r.impact_factor, r.conference_level, r.review_status,
               r.funding_status, r.funding_amount, r.collaborators, r.contribution_statement, r.abstract, r.key_findings, r.impact, r.ip_status, r.dataset_url, r.project_start,
               (SELECT author_order FROM research_contributors c WHERE c.submission_id = fs.submission_id AND {who['match']}) AS my_order
        FROM form_submissions fs JOIN research_outputs r USING (submission_id) WHERE ({where}) ORDER BY fs.event_date DESC""", args)
    authors = _names(conn, [r["submission_id"] for r in rows],
                     "SELECT c.submission_id, COALESCE(f.full_name, s.full_name, c.name) || CASE c.person_type WHEN 'EXTERNAL' THEN ' (ext.)' ELSE '' END "
                     "FROM research_contributors c LEFT JOIN faculty f ON f.emp_id = c.emp_id LEFT JOIN students s ON s.roll_no = c.roll_no "
                     "WHERE c.submission_id IN ({IDS}) ORDER BY c.author_order")
    out = []
    for r in rows:
        role = None
        if r["my_order"] is not None:
            role = "Lead author" if r["my_order"] == 1 else f"Co-author (#{r['my_order']})"
        elif who.get("submitter") and r["submitter_emp_id"] == who["submitter"]:
            role = "Submitted by"
        ident = r["identifier"] or ""
        out.append(item(
            r["submission_id"], r["category"], r["title"], r["event_date"], r["ay_id"], role,
            [badge(r["current_status"], "ok"), badge(r["indexing"]), badge(r["quartile"], "ok"), badge(f"IF {_num(r['impact_factor'])}" if r["impact_factor"] else None),
             badge(r["conference_level"]), badge(r["review_status"]), badge(r["badge_tag"], "warn")],
            [("Authors", ", ".join(authors.get(r["submission_id"], []))), ("Venue / publisher", r["venue_publisher"]),
             ("Identifier", None if ident.startswith(("http://", "https://")) else ident),
             ("Funding", " · ".join(x for x in (r["funding_status"], inr(r["funding_amount"])) if x) if (r["funding_amount"] or r["funding_status"] not in (None, "Not funded")) else None),
             ("Collaborators", r["collaborators"]), ("Project started", r["project_start"]), ("IP / licensing", r["ip_status"]),
             ("Contribution", r["contribution_statement"])],
            [("Abstract", r["abstract"]), ("Key findings", r["key_findings"]), ("Impact", r["impact"])],
            [("Identifier link", ident if ident.startswith(("http://", "https://")) else None), ("Venue website", r["venue_url"]), ("Dataset / code", r["dataset_url"]),
             ("Evidence", r["evidence_url"]), ("Photo", r["media_url"])], r["is_landmark"]))
        out[-1]["amount"] = r["funding_amount"]
    return out


def _outcome_badges(row) -> list:
    return [badge("Participation" if row["entry_kind"] == "PARTICIPATION" else "Achievement", "warn" if row["entry_kind"] == "PARTICIPATION" else "ok"),
            badge(row["position"], "ok" if row["entry_kind"] != "PARTICIPATION" else None), badge(row["level"]), badge(row["badge_tag"], "warn")]


def _student_rows(conn, where: str, args: list, roll: Optional[str] = None) -> List[Dict[str, Any]]:
    rows = _rows(conn, f"""
        SELECT fs.submission_id, fs.ay_id, fs.event_date, fs.category, fs.title, fs.evidence_url, fs.media_url, fs.is_landmark, fs.badge_tag,
               sa.entry_kind, sa.is_team, sa.organizer, sa.level, sa.position, sa.prize_amount, sa.domain, sa.mentor_emp_id, sa.project_statement, sa.abstract,
               sa.tools_used, sa.measurable_impact, sa.demo_url, sa.learning_outcomes, f.full_name AS mentor,
               {"(SELECT role FROM student_achievement_participants p WHERE p.submission_id = fs.submission_id AND p.roll_no = ?) AS my_role, (SELECT is_lead FROM student_achievement_participants p WHERE p.submission_id = fs.submission_id AND p.roll_no = ?) AS my_lead," if roll else "NULL AS my_role, NULL AS my_lead,"}
               NULL AS pad
        FROM form_submissions fs JOIN student_achievements sa USING (submission_id) LEFT JOIN faculty f ON f.emp_id = sa.mentor_emp_id
        WHERE ({where}) ORDER BY fs.event_date DESC""", ([roll, roll] if roll else []) + args)
    team = _names(conn, [r["submission_id"] for r in rows],
                  "SELECT p.submission_id, COALESCE(s.full_name, p.name, p.raw_text) || ' (' || COALESCE(p.roll_no, '?') || ')' FROM student_achievement_participants p "
                  "LEFT JOIN students s ON s.roll_no = p.roll_no WHERE p.submission_id IN ({IDS}) ORDER BY p.line_no")
    for r in rows:
        r["team"] = team.get(r["submission_id"], [])
    return rows


def _student_item(r, show_team_as="Team", role=None) -> Dict[str, Any]:
    return item(
        r["submission_id"], r["category"], r["title"], r["event_date"], r["ay_id"], role, _outcome_badges(r),
        [(show_team_as, ", ".join(r["team"]) if (r["is_team"] or len(r["team"]) > 1) else None), ("Organiser", r["organizer"]), ("Domain", r["domain"]),
         ("Prize / scholarship", inr(r["prize_amount"]) if r["prize_amount"] else None), ("Mentor", r["mentor"]), ("Tools", r["tools_used"])],
        [("Objective", r["project_statement"]), ("Details", r["abstract"]), ("Result / impact", r["measurable_impact"]), ("Learning outcomes", r["learning_outcomes"])],
        [("Demo / repository", r["demo_url"]), ("Evidence", r["evidence_url"]), ("Photo", r["media_url"])], r["is_landmark"])


# ---------------------------------------------------------------- builders shared by the person pages and the by-work view
def _span(start, end):
    return start if not end or end == start else f"{start} to {end}"


def _faculty_ach_items(conn, where: str, args: list, people: bool = False) -> List[Dict[str, Any]]:
    """Faculty achievements. people=True (by-work view) names the faculty member, which a person's own page does not need."""
    out = []
    for r in _rows(conn, f"""SELECT fs.submission_id, fs.ay_id, fa.start_date, fs.category, fs.title, fs.evidence_url, fs.media_url, fs.badge_tag, fs.is_landmark,
                                   fa.recognition_type, fa.host_org, fa.level, fa.end_date, fa.city_venue, fa.credential_no, fa.duration_hours, fa.role_contribution,
                                   fa.selection_criteria, fa.description, fa.outcome_impact, fa.is_team, fa.other_contributors, fa.organizer_url, u.full_name AS person
                            FROM form_submissions fs JOIN faculty_achievements fa USING (submission_id) LEFT JOIN faculty u ON u.emp_id = fa.emp_id
                            WHERE ({where}) ORDER BY fa.start_date DESC""", args):
        out.append(item(r["submission_id"], r["category"], r["title"], r["start_date"], r["ay_id"], r["recognition_type"],
                        [badge(r["level"]), badge(f"{_num(r['duration_hours'])} hrs" if r["duration_hours"] else None), badge(r["badge_tag"], "warn")],
                        [("Faculty", r["person"] if people else None), ("Awarding body / host", r["host_org"]), ("Dates", _span(r["start_date"], r["end_date"]) if r["end_date"] else None),
                         ("Place", r["city_venue"]), ("Credential no.", r["credential_no"]), ("Other contributors", r["other_contributors"] if r["is_team"] else None)],
                        [("Description", r["description"]), ("Your role", r["role_contribution"]), ("Selection criteria", r["selection_criteria"]), ("Outcome & impact", r["outcome_impact"])],
                        [("Organiser website", r["organizer_url"]), ("Evidence", r["evidence_url"]), ("Photo", r["media_url"])], r["is_landmark"]))
    return out


_INVOLVED = ("(SELECT group_concat(f2.full_name, ', ') FROM submission_faculty sf2 JOIN faculty f2 ON f2.emp_id = sf2.emp_id "
             "WHERE sf2.submission_id = fs.submission_id AND sf2.role = 'Involved')")


def _event_items(conn, where: str, args: list, emp: Optional[str] = None) -> List[Dict[str, Any]]:
    """Departmental highlights. With emp: the person's role in each. Without: the convener and the faculty involved."""
    mine = "(SELECT group_concat(role) FROM submission_faculty sf WHERE sf.submission_id = fs.submission_id AND sf.emp_id = ?) AS my_roles" if emp else "NULL AS my_roles"
    out = []
    for r in _rows(conn, f"""SELECT fs.submission_id, fs.ay_id, fs.event_date, fs.category, fs.title, fs.evidence_url, fs.media_url, fs.badge_tag, fs.is_landmark, fs.submitter_emp_id,
                                   d.convener_emp_id, d.highlight_type, d.units_involved, d.start_date, d.end_date, d.impl_status, d.venue, d.partner_bodies, d.participant_count,
                                   d.overview, d.objectives, d.outputs, d.success_indicators, d.budget_amount, d.funding_source, d.recognition, d.report_url,
                                   cf.full_name AS convener, {_INVOLVED} AS involved, {mine}
                            FROM form_submissions fs JOIN department_highlights d USING (submission_id) LEFT JOIN faculty cf ON cf.emp_id = d.convener_emp_id
                            WHERE ({where}) ORDER BY fs.event_date DESC""", ([emp] if emp else []) + args):
        role = ("Convener" if r["convener_emp_id"] == emp else "Involved" if r["my_roles"] else "Submitted by") if emp else None
        out.append(item(r["submission_id"], r["category"], r["title"], r["event_date"], r["ay_id"], role,
                        [badge(r["impl_status"], "ok" if r["impl_status"] == "Completed" else None), badge(r["highlight_type"]), badge(r["badge_tag"], "warn")],
                        [("Convener", None if emp else r["convener"]), ("Faculty involved", None if emp else r["involved"]),
                         ("Dates", _span(r["start_date"], r["end_date"])), ("Venue", r["venue"]), ("Participants", r["participant_count"]),
                         ("Partners / funding bodies", r["partner_bodies"]), ("Budget", inr(r["budget_amount"])), ("Funding source", r["funding_source"]), ("Recognition", r["recognition"])],
                        [("Overview", r["overview"]), ("Objectives", r["objectives"]), ("Key outputs", r["outputs"]), ("Success indicators", r["success_indicators"])],
                        [("Event report", r["report_url"]), ("Evidence", r["evidence_url"]), ("Photo", r["media_url"])], r["is_landmark"]))
    return out


def _outreach_items(conn, where: str, args: list, emp: Optional[str] = None) -> List[Dict[str, Any]]:
    mine = "(SELECT group_concat(role) FROM submission_faculty sf WHERE sf.submission_id = fs.submission_id AND sf.emp_id = ?) AS my_roles" if emp else "NULL AS my_roles"
    out = []
    for r in _rows(conn, f"""SELECT fs.submission_id, fs.ay_id, fs.event_date, fs.category, fs.title, fs.evidence_url, fs.media_url, fs.badge_tag, fs.is_landmark,
                                   o.lead_emp_id, o.activity_format, g.name AS partner, o.partner_type, o.start_date, o.end_date, o.venue, o.target_audience, o.expected_count, o.actual_count,
                                   o.objective, o.summary_outcomes, o.speakers, o.mou_scope, o.agreement_effective, o.agreement_expiry, o.follow_up, o.measurable_outcomes, o.report_url,
                                   lf.full_name AS lead, {_INVOLVED} AS involved, {mine}
                            FROM form_submissions fs JOIN outreach_activities o USING (submission_id) LEFT JOIN organizations g ON g.org_id = o.partner_org_id
                            LEFT JOIN faculty lf ON lf.emp_id = o.lead_emp_id WHERE ({where}) ORDER BY fs.event_date DESC""", ([emp] if emp else []) + args):
        role = ("Lead" if r["lead_emp_id"] == emp else "Involved" if r["my_roles"] else "Submitted by") if emp else None
        out.append(item(r["submission_id"], r["category"], r["title"], r["event_date"], r["ay_id"], role,
                        [badge(r["activity_format"]), badge(r["partner_type"]), badge(r["badge_tag"], "warn")],
                        [("Lead", None if emp else r["lead"]), ("Faculty involved", None if emp else r["involved"]), ("Partner", r["partner"]),
                         ("Dates", _span(r["start_date"], r["end_date"])), ("Venue", r["venue"]), ("Audience", r["target_audience"]),
                         ("Attendance", f"{r['actual_count']} (expected {r['expected_count']})" if r["actual_count"] and r["expected_count"] else r["actual_count"]),
                         ("Speakers", r["speakers"]), ("Agreement", f"{r['agreement_effective'] or '?'} to {r['agreement_expiry'] or '?'}" if r["agreement_expiry"] or r["agreement_effective"] else None)],
                        [("Summary", r["summary_outcomes"]), ("Objective", r["objective"]), ("MoU scope", r["mou_scope"]), ("Measurable outcomes", r["measurable_outcomes"]), ("Follow-up", r["follow_up"])],
                        [("Report", r["report_url"]), ("Evidence", r["evidence_url"]), ("Photo", r["media_url"])], r["is_landmark"]))
    return out


# ---------------------------------------------------------------- faculty
def faculty_profile(conn, user: User, emp_id: str, ay: Optional[str] = None) -> Dict[str, Any]:
    emp_id = emp_id.upper()
    if not (user.all_access or user.id == emp_id):
        raise HTTPException(403, "You can open your own page; the Admin and HoD can open anyone's")
    f = conn.execute("SELECT * FROM faculty WHERE emp_id = ?", (emp_id,)).fetchone()
    if not f:
        raise HTTPException(404, "Faculty not found")
    tags = [f"Tutor · {r['class_code']} (Sem {r['current_semester']})" for r in conn.execute("SELECT class_code, current_semester FROM classes WHERE tutor_id = ?", (emp_id,))]
    for r in conn.execute("SELECT role, programme, grp FROM role_assignments WHERE emp_id = ?", (emp_id,)):
        tags.append({"ADMIN": "Admin", "HOD": "Head of Department"}.get(r["role"]) or f"Programme Coordinator · {r['programme']}{(' ' + r['grp']) if r['grp'] else ''}")

    # Research & Innovation: author, or the person who submitted it
    research = _research_items_for(conn, "emp_id", emp_id, True)

    prof = _faculty_ach_items(conn, "fa.emp_id = ?", [emp_id])
    mine = "{c}.%s = ? OR fs.submission_id IN (SELECT submission_id FROM submission_faculty WHERE emp_id = ?) OR fs.submitter_emp_id = ?"
    events = _event_items(conn, mine.format(c="d") % "convener_emp_id", [emp_id] * 3, emp_id)
    outreach = _outreach_items(conn, mine.format(c="o") % "lead_emp_id", [emp_id] * 3, emp_id)

    mentored = [_student_item(r, "Students", "Mentor") for r in _student_rows(conn, "sa.mentor_emp_id = ?", [emp_id])]

    sections = [
        _section("research", "Research & Innovation", research, _categories("form_research")),
        _section("achievements", "Professional achievements", prof, _categories("form_faculty")),
        _section("events", "Events organised", events, _categories("form_departmental")),
        _section("outreach", "Industry, alumni & outreach", outreach, _categories("form_industry")),
        _section("mentoring", "Students mentored", mentored, _categories("form_student"), "Student achievements and participations where this faculty member is the mentor / guide."),
    ]
    head = {"kind": "faculty", "id": emp_id, "name": f["full_name"], "subtitle": f["designation"] or "Faculty", "status": f["status"], "tags": tags,
            "contact": [x for x in (f["email"], f["phone"], f["qualification"]) if x]}
    count = lambda cat: sum(1 for i in research if i["category"] == cat)
    fund = sum(i.get("amount") or 0 for i in research if i["category"] == "Funded Research Projects")
    summary = [("Journal papers", count("Journal Publications")), ("Conference papers", count("Conference Publications")), ("Patents", count("Patents & Intellectual Property")),
               ("Funded projects", count("Funded Research Projects")), ("Awards & honours", sum(1 for i in prof if i["category"] == "Awards & Honors Received")),
               ("Talks & sessions", sum(1 for i in prof if i["category"] in ("Invited Keynote / Expert Lectures Delivered", "Resource Person / Session Chair Roles"))),
               ("Events organised", len(events)), ("Students mentored", len(mentored))]
    return _finish(head, sections, summary, ay, extra=[("Research funding", inr(fund))] if fund else [])


def _research_items_for(conn, col: str, ident: str, with_submitter: bool) -> List[Dict[str, Any]]:
    where = f"fs.submission_id IN (SELECT submission_id FROM research_contributors WHERE {col} = ?)" + (" OR fs.submitter_emp_id = ?" if with_submitter else "")
    args = [ident, ident] + ([ident] if with_submitter else [])
    # the first ? belongs to the my_order sub-select, the rest to WHERE
    return _research_items(conn, where, args, {"match": f"c.{col} = ?", "submitter": ident if with_submitter else None})


# ---------------------------------------------------------------- student
def student_profile(conn, user: User, roll_no: str, ay: Optional[str] = None) -> Dict[str, Any]:
    from backend.master.people import student_in_scope
    roll_no = roll_no.upper()
    s = student_in_scope(conn, user, roll_no)
    cls = conn.execute("SELECT class_code, year_no, current_semester FROM classes WHERE class_id = ?", (s["class_id"],)).fetchone() if s["class_id"] else None
    journey = [f"{r['class_code'] or '—'} · {r['action']} {r['from_date']}" for r in conn.execute(
        "SELECT c.class_code, h.action, h.from_date FROM student_class_history h LEFT JOIN classes c ON c.class_id = h.class_id WHERE h.roll_no = ? ORDER BY h.from_date, h.id", (roll_no,))]

    rows = _student_rows(conn, "fs.submission_id IN (SELECT submission_id FROM student_achievement_participants WHERE roll_no = ?)", [roll_no], roll_no)
    mine = lambda kind: [_student_item(r, "Team", ("Team lead" if r["my_lead"] else r["my_role"]) if r["my_lead"] or r["my_role"] else None) for r in rows if r["entry_kind"] == kind]
    achievements, participations = mine("ACHIEVEMENT"), mine("PARTICIPATION")
    research = _research_items_for(conn, "roll_no", roll_no, False)

    attended = []
    for r in _rows(conn, """SELECT fs.submission_id, fs.ay_id, fs.event_date, fs.form_type, fs.category, fs.title, fs.evidence_url, fs.media_url, fs.badge_tag,
                                   d.venue AS d_venue, d.overview, d.highlight_type, o.venue AS o_venue, o.summary_outcomes, o.activity_format, g.name AS partner
                            FROM event_participants e JOIN form_submissions fs USING (submission_id)
                            LEFT JOIN department_highlights d ON d.submission_id = fs.submission_id LEFT JOIN outreach_activities o ON o.submission_id = fs.submission_id
                            LEFT JOIN organizations g ON g.org_id = o.partner_org_id WHERE e.roll_no = ? ORDER BY fs.event_date DESC""", (roll_no,)):
        dept = r["form_type"] == "DEPARTMENT"
        a = item(r["submission_id"], "Department events" if dept else "Industry & outreach", r["title"], r["event_date"], r["ay_id"], None,
                 [badge(r["category"]), badge(r["highlight_type"] if dept else r["activity_format"]), badge(r["badge_tag"], "warn")],
                 [("Venue", r["d_venue"] if dept else r["o_venue"]), ("Partner", r["partner"])], [("About", r["overview"] if dept else r["summary_outcomes"])],
                 [("Evidence", r["evidence_url"]), ("Photo", r["media_url"])])
        attended.append(a)

    # placement: grouped by what a student wants to look at
    pl_items = {"Status": [], "Offers": [], "Internship experience": [], "Interview experience": []}
    for p in _rows(conn, "SELECT ay_id, opt_status, opt_out_reason FROM placement_profiles WHERE roll_no = ? ORDER BY ay_id DESC", (roll_no,)):
        pl_items["Status"].append(item(None, "Status", "Opted in to placements" if p["opt_status"] == "OPTED_IN" else "Opted out of placements", None, p["ay_id"],
                                       None, [badge("Opted in" if p["opt_status"] == "OPTED_IN" else "Opted out", "ok" if p["opt_status"] == "OPTED_IN" else "warn")], [("Reason", p["opt_out_reason"])]))
    for o in _rows(conn, "SELECT o.*, g.name AS company, g.sector FROM placement_offers o JOIN organizations g ON g.org_id = o.org_id WHERE o.roll_no = ? ORDER BY o.ay_id DESC", (roll_no,)):
        pl_items["Offers"].append(item(None, "Offers", o["company"], o["offer_date"], o["ay_id"], o["job_role"],
                                       [badge(o["offer_type"].replace("_", " "), "ok"), badge(f"{_num(o['package_lpa'])} LPA" if o["package_lpa"] else None, "ok"), badge(o["offer_status"], None if o["offer_status"] == "Accepted" else "warn")],
                                       [("Sector", o["sector"]), ("Stipend / month", inr(o["stipend_per_month"])), ("Location", o["work_location"]),
                                        ("Recruitment", None if o["is_on_campus"] is None else "On-campus" if o["is_on_campus"] else "Off-campus")]))
    for e in _rows(conn, "SELECT e.*, g.name AS company FROM internship_experiences e JOIN organizations g ON g.org_id = e.org_id WHERE e.roll_no = ? ORDER BY e.ay_id DESC", (roll_no,)):
        pl_items["Internship experience"].append(item(None, "Internship experience", e["company"], None, e["ay_id"], e["role"],
                                                      [badge(e["mode"]), badge(f"{e['rating']}/5" if e["rating"] else None)], [("Duration", e["duration"]), ("Technologies", e["tech_stack"])],
                                                      [("Work done", e["work_summary"]), ("Learnings", e["learnings"]), ("Experience", e["experience"])]))
    for e in _rows(conn, "SELECT e.*, g.name AS company FROM interview_experiences e JOIN organizations g ON g.org_id = e.org_id WHERE e.roll_no = ? ORDER BY e.ay_id DESC", (roll_no,)):
        pl_items["Interview experience"].append(item(None, "Interview experience", e["company"], None, e["ay_id"], None,
                                                     [badge(e["result"], "ok" if e["result"] == "Selected" else None), badge(e["difficulty"])],
                                                     [("Rounds", f"{e['rounds_count']}: {e['round_details']}" if e["rounds_count"] and e["round_details"] else e["rounds_count"] or e["round_details"])],
                                                     [("Questions asked", e["questions_asked"]), ("Experience", e["experience"]), ("Tips", e["tips"])]))
    placement_all = [i for v in pl_items.values() for i in v]

    sections = [
        _section("achievements", "Achievements", achievements, _categories("form_student"), "Won, ranked or awarded."),
        _section("participations", "Participations", participations, _categories("form_student"), "Took part without a prize or rank."),
        _section("research", "Research & Innovation", research, _categories("form_research")),
        _section("events", "Events attended", attended, ["Department events", "Industry & outreach"]),
        _section("placement", "Placement", placement_all, list(pl_items)),
    ]
    prize = sum(r["prize_amount"] or 0 for r in rows if r["entry_kind"] == "ACHIEVEMENT")
    head = {"kind": "student", "id": roll_no, "name": s["full_name"], "status": s["status"], "journey": journey, "tags": [],
            "subtitle": f"{cls['class_code']} · Year {cls['year_no']} · Semester {cls['current_semester']}" if cls else s["status"]}
    summary = [("Achievements", len(achievements)), ("Participations", len(participations)), ("Research outputs", len(research)), ("Events attended", len(attended)),
               ("Offers", len(pl_items["Offers"])), ("Prize money", inr(prize) if prize else None)]
    return _finish(head, sections, [x for x in summary if x[1] is not None], ay)


# ---------------------------------------------------------------- shared tail
def _finish(head, sections, summary, ay, extra=()) -> Dict[str, Any]:
    """Offer the academic years that actually have items, then apply the year filter (done last so the list stays complete)."""
    years = sorted({i["ay_id"] for s in sections for g in s["groups"] for i in g["items"] if i["ay_id"]}, reverse=True)
    if ay:
        for s in sections:
            for g in s["groups"]:
                g["items"] = [i for i in g["items"] if i["ay_id"] == ay]
                g["count"] = len(g["items"])
            s["groups"] = [g for g in s["groups"] if g["items"]]
            s["count"] = sum(g["count"] for g in s["groups"])
    return {"person": head, "summary": [{"label": k, "value": v} for k, v in [*summary, *extra]], "academic_years": years,
            "ay_id": ay or "", "sections": [s for s in sections if s["count"]], "total": sum(s["count"] for s in sections)}
