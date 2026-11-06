"""Charts data. Student-related series respect the caller's class scope; department-wide series are Admin / HoD only."""
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
        "by_domain": _series(conn, f"SELECT domain, COUNT(DISTINCT submission_id) {base} GROUP BY domain ORDER BY 2 DESC", args),
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
        "mou_status": [dict(r) for r in conn.execute(
            "SELECT g.name AS partner, o.agreement_expiry AS expiry, CASE WHEN o.agreement_expiry < date('now') THEN 'Expired' WHEN o.agreement_expiry <= date('now','+90 day') THEN 'Expiring soon' ELSE 'Active' END AS status "
            "FROM outreach_activities o JOIN organizations g ON g.org_id = o.partner_org_id WHERE o.agreement_expiry IS NOT NULL ORDER BY o.agreement_expiry")],
    }


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


def overview(conn, user: User, ay: Optional[str] = None, class_id: Optional[int] = None, programme: Optional[str] = None) -> Dict[str, Any]:
    out = {"scope": "all" if user.all_access else "classes", "students": student_section(conn, user, ay, class_id, programme),
           "placements": placement_section(conn, user, ay, class_id, programme)}
    if user.all_access:
        out["department"] = department_section(conn, ay)
    return out
