"""IT Department Placements Diary - what students see.

Reads ONLY the PII-free views (v_diary_offers / v_diary_interviews / v_diary_internships) and the organizations table.
No roll number, name, photo, class or date of birth can reach this module's output.
"""
import statistics
from typing import Any, Dict, List

from fastapi import HTTPException

FTE = ("FTE", "FTE+INTERN", "INTERN_CONVERTED_FTE")
INTERN = ("INTERN", "FTE+INTERN")


def window(conn, years: int = 3) -> List[str]:
    """The most recent academic years that have placement offers (default: past three)."""
    return [r[0] for r in conn.execute("SELECT DISTINCT ay_id FROM v_diary_offers ORDER BY ay_id DESC LIMIT ?", (years,))]


def _pk(rows) -> Dict[str, Any]:
    pk = [r["package_lpa"] for r in rows if r["offer_type"] in FTE and r["package_lpa"] is not None]
    return {"min_lpa": min(pk) if pk else None, "avg_lpa": round(sum(pk) / len(pk), 2) if pk else None,
            "median_lpa": round(statistics.median(pk), 2) if pk else None, "max_lpa": max(pk) if pk else None}


def _offers(conn, org_id, ays):
    if not ays:
        return []
    return [dict(r) for r in conn.execute(
        f"SELECT * FROM v_diary_offers WHERE org_id = ? AND ay_id IN ({','.join('?' * len(ays))})", [org_id, *ays])]


def overview(conn) -> Dict[str, Any]:
    ays = window(conn)
    if not ays:
        return {"years": [], "placed": 0, "recruiters": 0, "top_recruiters": []}
    marks = ",".join("?" * len(ays))
    placed = conn.execute(f"SELECT COUNT(*) FROM v_diary_offers WHERE offer_type IN ('FTE','FTE+INTERN','INTERN_CONVERTED_FTE') AND ay_id IN ({marks})", ays).fetchone()[0]
    top = [dict(r) for r in conn.execute(
        f"SELECT org_id, company, COUNT(*) AS placed FROM v_diary_offers WHERE offer_type IN ('FTE','FTE+INTERN','INTERN_CONVERTED_FTE') AND ay_id IN ({marks}) "
        f"GROUP BY org_id ORDER BY 3 DESC LIMIT 8", ays)]
    pk = [r[0] for r in conn.execute(f"SELECT package_lpa FROM v_diary_offers WHERE offer_type IN ('FTE','FTE+INTERN','INTERN_CONVERTED_FTE') AND package_lpa IS NOT NULL AND ay_id IN ({marks})", ays)]
    return {"years": ays, "placed": placed, "recruiters": conn.execute(f"SELECT COUNT(DISTINCT org_id) FROM v_diary_offers WHERE ay_id IN ({marks})", ays).fetchone()[0],
            "highest_lpa": max(pk) if pk else None, "average_lpa": round(sum(pk) / len(pk), 2) if pk else None, "top_recruiters": top}


def companies(conn, q: str = "") -> Dict[str, Any]:
    ays = window(conn)
    marks = ",".join("?" * len(ays)) or "''"
    rows = conn.execute(
        f"""SELECT g.org_id, g.name, g.sector,
                   (SELECT COUNT(*) FROM v_diary_interviews i WHERE i.org_id = g.org_id) AS interview_count,
                   (SELECT COUNT(*) FROM v_diary_internships n WHERE n.org_id = g.org_id) AS internship_count
            FROM organizations g WHERE g.name LIKE ? ORDER BY g.name""", (f"%{q}%",)).fetchall()
    out = []
    for r in rows:
        offers = _offers(conn, r["org_id"], ays)
        if not offers and not r["interview_count"] and not r["internship_count"]:
            continue
        out.append({"org_id": r["org_id"], "name": r["name"], "sector": r["sector"],
                    "placed": sum(1 for o in offers if o["offer_type"] in FTE), "interns": sum(1 for o in offers if o["offer_type"] in INTERN),
                    **_pk(offers), "interview_experiences": r["interview_count"], "internship_experiences": r["internship_count"]})
    out.sort(key=lambda c: (-c["placed"], c["name"].lower()))
    return {"years": ays, "companies": out}


def company(conn, org_id: int) -> Dict[str, Any]:
    org = conn.execute("SELECT org_id, name, sector, website FROM organizations WHERE org_id = ?", (org_id,)).fetchone()
    if not org:
        raise HTTPException(404, "Company not found")
    ays = window(conn)
    offers = _offers(conn, org_id, ays)
    by_year = []
    for ay in sorted(ays, reverse=True):
        yo = [o for o in offers if o["ay_id"] == ay]
        by_year.append({"ay_id": ay, "placed": sum(1 for o in yo if o["offer_type"] in FTE), "interns": sum(1 for o in yo if o["offer_type"] in INTERN), **_pk(yo),
                        "avg_stipend": (lambda s: round(sum(s) / len(s)) if s else None)([o["stipend_per_month"] for o in yo if o["stipend_per_month"]])})
    types: Dict[str, int] = {}
    roles: Dict[str, int] = {}
    for o in offers:
        types[o["offer_type"]] = types.get(o["offer_type"], 0) + 1
        if o["job_role"]:
            roles[o["job_role"]] = roles.get(o["job_role"], 0) + 1
    d = lambda sql: [dict(r) for r in conn.execute(sql, (org_id,))]
    return {
        "org_id": org["org_id"], "name": org["name"], "sector": org["sector"], "website": org["website"], "years": ays,
        "placed": sum(y["placed"] for y in by_year), "interns": sum(y["interns"] for y in by_year), **_pk(offers),
        "by_year": by_year, "offer_types": [{"label": k, "value": v} for k, v in sorted(types.items(), key=lambda x: -x[1])],
        "roles": [{"label": k, "value": v} for k, v in sorted(roles.items(), key=lambda x: -x[1])],
        "interviews": d("SELECT ay_id, rounds_count, round_details, difficulty, questions_asked, result, experience, tips FROM v_diary_interviews WHERE org_id = ? ORDER BY ay_id DESC"),
        "internships": d("SELECT ay_id, duration, mode, role, tech_stack, work_summary, learnings, rating, experience FROM v_diary_internships WHERE org_id = ? ORDER BY ay_id DESC"),
    }
