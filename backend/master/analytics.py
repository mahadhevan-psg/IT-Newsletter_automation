"""Charts data. Student-related series respect the caller's class scope; department-wide series are Admin / HoD only."""
import re
import statistics
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from backend.master.auth import User
from backend.master.common import EFF_CLASS

FTE_TYPES = "('FTE','FTE+INTERN','INTERN_CONVERTED_FTE')"


def _series(conn, sql: str, args=()) -> List[Dict[str, Any]]:
    return [{"label": r[0] if r[0] is not None else "Not given", "value": r[1]} for r in conn.execute(sql, args)]


def _scope(user: User, col: str, class_id: Optional[int], programme: Optional[str]):
    """SQL fragment + args limiting rows to the caller's classes (and the optional class / programme filter)."""
    where, args = [], []
    if class_id:
        if not user.sees_class(class_id):
            raise HTTPException(403, "That class is outside your scope")
        where.append(f"{col} = ?")
        args.append(class_id)
    elif not user.all_access:
        ids = sorted(user.class_ids) or [-1]
        where.append(f"{col} IN ({','.join('?' * len(ids))})")
        args += ids
    if programme:
        where.append(f"{col} IN (SELECT class_id FROM classes WHERE programme = ?)")
        args.append(programme)
    return (" AND " + " AND ".join(where)) if where else "", args


def student_section(conn, user: User, ay: Optional[str], class_id, programme) -> Dict[str, Any]:
    sc, sa = _scope(user, "class_id", class_id, programme)
    ayc, aya = (" AND ay_id = ?", [ay]) if ay else ("", [])
    base = f"FROM v_student_achievements WHERE 1=1{sc}{ayc}"
    args = sa + aya
    scs, sas = _scope(user, "s.class_id", class_id, programme)
    active = conn.execute(f"SELECT COUNT(*) FROM students s WHERE s.status = 'Active'{scs}", sas).fetchone()[0]
    achievers = conn.execute(f"SELECT COUNT(DISTINCT roll_no) {base}", args).fetchone()[0]
    per_class = [dict(r) for r in conn.execute(
        f"""SELECT c.class_code || ' · Sem ' || c.current_semester AS label,
                   (SELECT COUNT(*) FROM students s WHERE s.class_id = c.class_id AND s.status = 'Active') AS students,
                   (SELECT COUNT(DISTINCT v.roll_no) FROM v_student_achievements v WHERE v.class_id = c.class_id{ayc.replace('ay_id', 'v.ay_id')}) AS achievers,
                   (SELECT COUNT(*) FROM v_student_achievements v WHERE v.class_id = c.class_id{ayc.replace('ay_id', 'v.ay_id')}) AS achievements
            FROM classes c WHERE 1=1{_scope(user, 'c.class_id', class_id, programme)[0]} ORDER BY c.programme DESC, c.grp, c.year_no, c.current_semester""",
        aya + aya + _scope(user, "c.class_id", class_id, programme)[1])]
    return {
        "active_students": active,
        "students_with_achievements": achievers,
        "participation_rate": round(100 * achievers / active, 1) if active else 0,
        "by_category": _series(conn, f"SELECT category, COUNT(DISTINCT submission_id) {base} GROUP BY category ORDER BY 2 DESC", args),
        "by_level": _series(conn, f"SELECT level, COUNT(DISTINCT submission_id) {base} GROUP BY level ORDER BY 2 DESC", args),
        "by_kind": _series(conn, f"SELECT CASE (SELECT k.entry_kind FROM student_achievements k WHERE k.submission_id = v_student_achievements.submission_id) WHEN 'PARTICIPATION' THEN 'Participation' ELSE 'Achievement' END, COUNT(DISTINCT submission_id) {base} GROUP BY 1 ORDER BY 2 DESC", args),
        "by_year": _series(conn, f"SELECT ay_id, COUNT(DISTINCT submission_id) {base} GROUP BY ay_id ORDER BY 1", args),
        "per_class": per_class,
        "top_students": [dict(r) for r in conn.execute(
            f"SELECT roll_no, student_name AS name, class_code, COUNT(DISTINCT submission_id) AS achievements {base} GROUP BY roll_no ORDER BY 4 DESC LIMIT 10", args)],
    }


def department_section(conn, ay: Optional[str]) -> Dict[str, Any]:
    ayc, aya = (" AND fs.ay_id = ?", [ay]) if ay else ("", [])
    q = lambda sql: _series(conn, sql.replace("{AY}", ayc), aya)
    return {
        "submissions_by_form": q("SELECT form_type, COUNT(*) FROM form_submissions fs WHERE 1=1{AY} GROUP BY form_type ORDER BY 2 DESC"),
        "submissions_by_year": _series(conn, "SELECT ay_id, COUNT(*) FROM form_submissions GROUP BY ay_id ORDER BY 1"),
        "research_by_category": q("SELECT category, COUNT(*) FROM form_submissions fs WHERE form_type='RESEARCH'{AY} GROUP BY category ORDER BY 2 DESC"),
        "research_by_indexing": q("SELECT r.indexing, COUNT(*) FROM research_outputs r JOIN form_submissions fs USING(submission_id) WHERE 1=1{AY} GROUP BY r.indexing ORDER BY 2 DESC"),
        "research_by_quartile": q("SELECT r.quartile, COUNT(*) FROM research_outputs r JOIN form_submissions fs USING(submission_id) WHERE r.quartile IS NOT NULL{AY} GROUP BY r.quartile ORDER BY 1"),
        "funding_total_inr": conn.execute(f"SELECT COALESCE(SUM(r.funding_amount),0) FROM research_outputs r JOIN form_submissions fs USING(submission_id) WHERE 1=1{ayc}", aya).fetchone()[0],
        "faculty_by_category": q("SELECT category, COUNT(*) FROM form_submissions fs WHERE form_type='FACULTY'{AY} GROUP BY category ORDER BY 2 DESC"),
        "faculty_by_level": q("SELECT a.level, COUNT(*) FROM faculty_achievements a JOIN form_submissions fs USING(submission_id) WHERE 1=1{AY} GROUP BY a.level ORDER BY 2 DESC"),
        "top_faculty": [dict(r) for r in conn.execute(
            f"SELECT f.emp_id, f.full_name AS name, COUNT(*) AS submissions FROM form_submissions fs JOIN faculty f ON f.emp_id = fs.submitter_emp_id WHERE 1=1{ayc} GROUP BY f.emp_id ORDER BY 3 DESC LIMIT 10", aya)],
        "department_by_category": q("SELECT category, COUNT(*) FROM form_submissions fs WHERE form_type='DEPARTMENT'{AY} GROUP BY category ORDER BY 2 DESC"),
        "department_participants": conn.execute(f"SELECT COALESCE(SUM(d.participant_count),0) FROM department_highlights d JOIN form_submissions fs USING(submission_id) WHERE 1=1{ayc}", aya).fetchone()[0],
        "outreach_by_category": q("SELECT category, COUNT(*) FROM form_submissions fs WHERE form_type='OUTREACH'{AY} GROUP BY category ORDER BY 2 DESC"),
        "outreach_attendance": conn.execute(f"SELECT COALESCE(SUM(o.actual_count),0) FROM outreach_activities o JOIN form_submissions fs USING(submission_id) WHERE 1=1{ayc}", aya).fetchone()[0],
        "top_partners": q("SELECT g.name, COUNT(*) FROM outreach_activities o JOIN organizations g ON g.org_id = o.partner_org_id JOIN form_submissions fs USING(submission_id) WHERE 1=1{AY} GROUP BY g.org_id ORDER BY 2 DESC LIMIT 10"),
        "mou_status": _mou_status(conn),
    }


def _mou_status(conn):
    """Every agreement with an expiry date, soonest first: the department's MoU entries, and MoUs recorded as outreach."""
    return [dict(r) for r in conn.execute(
        "SELECT partner, expiry, CASE WHEN expiry < date('now') THEN 'Expired' WHEN expiry <= date('now','+90 day') THEN 'Expiring soon' ELSE 'Active' END AS status FROM ("
        " SELECT g.name AS partner, o.agreement_expiry AS expiry FROM outreach_activities o JOIN organizations g ON g.org_id = o.partner_org_id"
        " UNION ALL SELECT d.partner_bodies, d.agreement_expiry FROM department_highlights d"
        ") WHERE expiry IS NOT NULL ORDER BY expiry")]


def placement_section(conn, user: User, ay: Optional[str], class_id, programme) -> Dict[str, Any]:
    sc, sa = _scope(user, EFF_CLASS, class_id, programme)
    ayc, aya = (" AND {t}.ay_id = ?", [ay]) if ay else ("", [])
    offers_from = f"FROM placement_offers o JOIN students s ON s.roll_no = o.roll_no JOIN organizations g ON g.org_id = o.org_id WHERE o.offer_status = 'Accepted'{sc}{ayc.format(t='o')}"
    prof_from = f"FROM placement_profiles p JOIN students s ON s.roll_no = p.roll_no WHERE 1=1{sc}{ayc.format(t='p')}"
    a = sa + aya
    opted_in = conn.execute(f"SELECT COUNT(*) {prof_from} AND p.opt_status = 'OPTED_IN'", a).fetchone()[0]
    opted_out = conn.execute(f"SELECT COUNT(*) {prof_from} AND p.opt_status = 'OPTED_OUT'", a).fetchone()[0]
    placed = conn.execute(f"SELECT COUNT(DISTINCT o.roll_no) {offers_from} AND o.offer_type IN {FTE_TYPES}", a).fetchone()[0]
    pk = sorted(r[0] for r in conn.execute(f"SELECT o.package_lpa {offers_from} AND o.offer_type IN {FTE_TYPES} AND o.package_lpa IS NOT NULL", a))
    buckets = [("Below 4", 0, 4), ("4 - 6", 4, 6), ("6 - 10", 6, 10), ("10 - 15", 10, 15), ("15 and above", 15, 1e9)]
    return {
        "opted_in": opted_in, "opted_out": opted_out, "placed": placed,
        "unplaced_opted_in": max(opted_in - placed, 0),
        "placement_percent": round(100 * placed / opted_in, 1) if opted_in else 0,
        "highest_lpa": pk[-1] if pk else None, "average_lpa": round(sum(pk) / len(pk), 2) if pk else None,
        "median_lpa": round(statistics.median(pk), 2) if pk else None,
        "package_distribution": [{"label": n, "value": sum(1 for x in pk if lo <= x < hi)} for n, lo, hi in buckets],
        "by_company": _series(conn, f"SELECT g.name, COUNT(*) {offers_from} GROUP BY g.org_id ORDER BY 2 DESC LIMIT 15", a),
        "by_offer_type": _series(conn, f"SELECT o.offer_type, COUNT(*) {offers_from} GROUP BY o.offer_type ORDER BY 2 DESC", a),
        "by_year": _series(conn, f"SELECT o.ay_id, COUNT(DISTINCT o.roll_no) {offers_from.replace(ayc.format(t='o'), '')} AND o.offer_type IN {FTE_TYPES} GROUP BY o.ay_id ORDER BY 1", sa),
        "opt_out_reasons": _series(conn, f"SELECT p.opt_out_reason, COUNT(*) {prof_from} AND p.opt_status = 'OPTED_OUT' GROUP BY 1 ORDER BY 2 DESC", a),
    }


# ---------------------------------------------------------------- the dashboard's first sight: six categories, a headline figure and four more each
def _category_counts(conn, form_type: str, ay: Optional[str]) -> Dict[str, int]:
    ayc, aya = (" AND ay_id = ?", [ay]) if ay else ("", [])
    return {r[0] or "": r[1] for r in conn.execute(f"SELECT category, COUNT(*) FROM form_submissions WHERE form_type = ?{ayc} GROUP BY category", [form_type] + aya)}


def _matching(counts: Dict[str, int], pattern: str) -> int:
    """Entries in the categories whose name matches (by words, so a category the Admin renames slightly is still counted)."""
    return sum(n for name, n in counts.items() if re.search(pattern, name, re.I))


def _stat(label: str, value, kind: str = "count") -> Dict[str, Any]:
    return {"label": label, "value": value, "kind": kind}           # kind: count | money (rupees) | percent | lpa


def _department_cards(conn, ay: Optional[str], dept: Dict[str, Any]) -> List[Dict[str, Any]]:
    res, fac = _category_counts(conn, "RESEARCH", ay), _category_counts(conn, "FACULTY", ay)
    dep, out = _category_counts(conn, "DEPARTMENT", ay), _category_counts(conn, "OUTREACH", ay)
    ayc, aya = (" AND ay_id = ?", [ay]) if ay else ("", [])
    people = conn.execute(f"SELECT COUNT(DISTINCT submitter_emp_id) FROM form_submissions WHERE form_type = 'FACULTY'{ayc}", aya).fetchone()[0]
    top_quartiles = sum(r["value"] for r in dept["research_by_quartile"] if str(r["label"]).strip().upper() in ("Q1", "Q2"))
    return [
        {"id": "research", "title": "Research & Innovation", "total": sum(res.values()), "unit": "research contributions", "stats": [
            _stat("Journal papers", _matching(res, r"journal")), _stat("Conference papers", _matching(res, r"conference")),
            _stat("Patents & IPR", _matching(res, r"patent")), _stat("Funding & consultancy", dept["funding_total_inr"], "money")],
         "notes": [_stat("books and chapters", _matching(res, r"book")), _stat("papers in Q1 or Q2", top_quartiles)]},
        {"id": "faculty", "title": "Faculty Achievements", "total": sum(fac.values()), "unit": "faculty records", "stats": [
            _stat("Awards & honours", _matching(fac, r"award|hono")), _stat("Certifications", _matching(fac, r"certification")),
            _stat("Talks & session roles", _matching(fac, r"lecture|keynote|resource person|session chair")), _stat("FDPs & workshops", _matching(fac, r"\bfdp|workshop"))],
         "notes": [_stat("faculty have entries", people), _stat("memberships and editorial roles", _matching(fac, r"member|editorial"))]},
        {"id": "department", "title": "Department Milestones", "total": sum(dep.values()), "unit": "department milestones", "stats": [
            _stat("Awards & recognitions", _matching(dep, r"award|recognition")), _stat("Events & programmes", _matching(dep, r"events|\bfdp")),
            _stat("MoUs & partnerships", _matching(dep, r"\bmou")), _stat("Participants reached", dept["department_participants"])],
         "notes": [_stat("lab and infrastructure upgrades", _matching(dep, r"infrastructure|laboratory")), _stat("student and social initiatives", _matching(dep, r"student development|social"))]},
        {"id": "outreach", "title": "Industry, Alumni & Outreach", "total": sum(out.values()), "unit": "engagements", "stats": [
            _stat("Industrial visits", _matching(out, r"visit")), _stat("Expert talks", _matching(out, r"expert|talk")),
            _stat("MoUs signed", _matching(out, r"\bmou")), _stat("Alumni interactions", _matching(out, r"alumni"))],
         "notes": [_stat("community initiatives", _matching(out, r"community|social")), _stat("recorded attendance", dept["outreach_attendance"])]},
    ]


def _student_cards(conn, user: User, ay: Optional[str], class_id, programme, students: Dict[str, Any], placements: Dict[str, Any]) -> List[Dict[str, Any]]:
    sc, sa = _scope(user, "class_id", class_id, programme)
    ayc, aya = (" AND ay_id = ?", [ay]) if ay else ("", [])
    mine = f"SELECT DISTINCT submission_id FROM v_student_achievements WHERE 1=1{sc}{ayc}"        # each entry once, however many students took part
    kinds = {r[0]: r[1] for r in conn.execute(f"SELECT entry_kind, COUNT(*) FROM student_achievements WHERE submission_id IN ({mine}) GROUP BY entry_kind", sa + aya)}
    prize = conn.execute(f"SELECT COALESCE(SUM(prize_amount), 0) FROM student_achievements WHERE submission_id IN ({mine})", sa + aya).fetchone()[0]
    pc, pa = _scope(user, EFF_CLASS, class_id, programme)
    oy, oa = (" AND o.ay_id = ?", [ay]) if ay else ("", [])
    offers, companies = conn.execute(
        f"SELECT COUNT(*), COUNT(DISTINCT o.org_id) FROM placement_offers o JOIN students s ON s.roll_no = o.roll_no WHERE o.offer_status = 'Accepted'{pc}{oy}", pa + oa).fetchone()
    return [
        {"id": "student", "title": "Student Achievements", "total": sum(kinds.values()), "unit": "student records", "stats": [
            _stat("Achievements", kinds.get("ACHIEVEMENT", 0)), _stat("Participations", kinds.get("PARTICIPATION", 0)),
            _stat("Students involved", students["students_with_achievements"]), _stat("Participation rate", students["participation_rate"], "percent")],
         "notes": [_stat("in prize money", prize, "money"), _stat("active students", students["active_students"])]},
        {"id": "placement", "title": "Student Placements", "total": placements["placed"], "unit": "students placed", "stats": [
            _stat("Placed of opted-in", placements["placement_percent"], "percent"), _stat("Highest package", placements["highest_lpa"], "lpa"),
            _stat("Average package", placements["average_lpa"], "lpa"), _stat("Recruiting companies", companies)],
         "notes": [_stat("accepted offers", offers), _stat("students opted in", placements["opted_in"])]},
    ]


def overview(conn, user: User, ay: Optional[str] = None, class_id: Optional[int] = None, programme: Optional[str] = None) -> Dict[str, Any]:
    out = {"scope": "all" if user.all_access else "classes", "students": student_section(conn, user, ay, class_id, programme),
           "placements": placement_section(conn, user, ay, class_id, programme)}
    if user.all_access:
        out["department"] = department_section(conn, ay)
    out["highlights"] = (_department_cards(conn, ay, out["department"]) if user.all_access else []) + _student_cards(
        conn, user, ay, class_id, programme, out["students"], out["placements"])
    return out
