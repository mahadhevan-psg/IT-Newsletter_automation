"""HTTP API for the master database: /api/auth, /api/master/*, /api/diary/*."""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Request, Response, UploadFile

from backend.master import analytics, diary, excel_templates, ingest, people, placements, profiles, submissions, works
from backend.master.auth import User, admin_user, change_password, current_user, editor_user, login, mark_tour_seen, staff_user
from backend.master.common import make_xlsx
from database.master_db import db

router = APIRouter()
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _xlsx(name: str, headers: List[str], example: Optional[List[str]] = None) -> Response:
    return Response(make_xlsx(headers, example), media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{name}"'})


def _filters(loc: Dict[str, Any]) -> Dict[str, Any]:
    """Query parameters that were actually supplied (pass locals() from the endpoint)."""
    return {k: v for k, v in loc.items() if k not in ("user", "limit", "offset") and v not in (None, "", False)}


async def _file(file: UploadFile) -> bytes:
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(400, "Please upload an .xlsx file (in Google Sheets: File > Download > Microsoft Excel)")
    data = await file.read()
    if len(data) > 15_000_000:
        raise HTTPException(413, "File is larger than 15 MB")
    return data


# ================================================================ auth
@router.post("/api/auth/login")
def api_login(payload: Dict[str, str] = Body(...)):
    return login(payload.get("id", ""), payload.get("password", ""))


@router.get("/api/auth/me")
def api_me(user: User = Depends(current_user)):
    return user.public()


@router.post("/api/auth/change-password")
def api_change_password(payload: Dict[str, str] = Body(...), user: User = Depends(current_user)):
    change_password(user, payload.get("old_password", ""), payload.get("new_password", ""))
    return {"success": True}


@router.post("/api/auth/tour-seen")
def api_tour_seen(payload: Dict[str, str] = Body(...), user: User = Depends(current_user)):
    return {"tours_seen": sorted(mark_tour_seen(user, payload.get("tour", "")))}


# ================================================================ reference data
@router.get("/api/master/meta")
def api_meta(user: User = Depends(staff_user)):
    with db() as conn:
        return {
            "classes": people.list_classes(conn, user),
            "academic_years": [r[0] for r in conn.execute("SELECT ay_id FROM academic_years ORDER BY ay_id DESC")],
            "current_ay": (conn.execute("SELECT ay_id FROM academic_years WHERE is_current = 1").fetchone() or [None])[0],
            "forms": [{"form_id": fid, "title": s["title"], "form_type": s["form_type"]} for fid, s in ingest.specs()["forms"].items()],
            "categories": {fid: next((q["choices"] for q in s["questions"] if q.get("key") == "category"), []) for fid, s in ingest.specs()["forms"].items()},
            "organizations": [dict(r) for r in conn.execute("SELECT org_id, name FROM organizations ORDER BY name")],
            "faculty": [dict(r) for r in conn.execute("SELECT emp_id, full_name FROM faculty WHERE status != 'Relieved' AND emp_id != 'ADMIN' ORDER BY full_name")],
        }


# ================================================================ classes
@router.get("/api/master/classes")
def api_classes(include_completed: bool = False, user: User = Depends(staff_user)):
    with db() as conn:
        return people.list_classes(conn, user, include_completed)


@router.put("/api/master/classes/{class_id}/term")
def api_class_term(class_id: int, payload: Dict[str, Any] = Body(...), user: User = Depends(staff_user)):
    with db() as conn:
        return people.set_term(conn, user, class_id, int(payload.get("semester") or 0), payload.get("ay_id"))


@router.post("/api/master/classes")
def api_add_class(payload: Dict[str, Any] = Body(...), user: User = Depends(admin_user)):
    with db() as conn:
        return people.add_class(conn, user, payload)


@router.post("/api/master/classes/{class_id}/graduate")
def api_class_graduate(class_id: int, user: User = Depends(staff_user)):
    with db() as conn:
        return people.graduate_class(conn, user, class_id)


@router.put("/api/master/classes/{class_id}/tutor")
def api_class_tutor(class_id: int, payload: Dict[str, Any] = Body(...), user: User = Depends(admin_user)):
    with db() as conn:
        people.set_tutor(conn, user, class_id, payload.get("emp_id"))
    return {"success": True}


# ================================================================ students
@router.get("/api/master/students")
def api_students(class_id: Optional[int] = None, programme: Optional[str] = None, grp: Optional[str] = None, year_no: Optional[int] = None,
                 status: Optional[str] = "Active",
                 q: Optional[str] = None, limit: int = 100, offset: int = 0, user: User = Depends(staff_user)):
    f = {"class_id": class_id, "programme": programme, "grp": grp, "year_no": year_no, "status": status, "q": q}
    with db() as conn:
        return people.list_students(conn, user, f, min(limit, 500), offset)


@router.post("/api/master/students")
def api_add_student(payload: Dict[str, Any] = Body(...), user: User = Depends(editor_user)):
    with db() as conn:
        return {"roll_no": people.add_student(conn, user, payload)}


@router.put("/api/master/students/{roll_no}")
def api_update_student(roll_no: str, payload: Dict[str, Any] = Body(...), user: User = Depends(editor_user)):
    with db() as conn:
        people.update_student(conn, user, roll_no.upper(), payload)
    return {"success": True}


@router.post("/api/master/students/{roll_no}/remove")
def api_remove_student(roll_no: str, user: User = Depends(editor_user)):
    with db() as conn:
        people.remove_student(conn, user, roll_no.upper())
    return {"success": True}


@router.post("/api/master/students/{roll_no}/transfer")
def api_transfer_student(roll_no: str, payload: Dict[str, Any] = Body(...), user: User = Depends(editor_user)):
    with db() as conn:
        people.transfer_student(conn, user, roll_no.upper(), int(payload.get("class_id") or 0))
    return {"success": True}


@router.get("/api/master/students/template")
def api_students_template(user: User = Depends(editor_user)):
    return Response(excel_templates.students_workbook(), media_type=XLSX, headers={"Content-Disposition": 'attachment; filename="students_template.xlsx"'})


@router.post("/api/master/students/upload")
async def api_students_upload(file: UploadFile = File(...), class_id: Optional[int] = Form(None), user: User = Depends(editor_user)):
    data = await _file(file)
    with db() as conn:
        return people.upload_students(conn, user, data, class_id)


# ================================================================ faculty (Admin)
@router.get("/api/master/faculty")
def api_faculty(q: str = "", status: str = "", user: User = Depends(staff_user)):
    with db() as conn:
        return people.list_faculty(conn, user, q, status)


@router.post("/api/master/faculty")
def api_add_faculty(payload: Dict[str, Any] = Body(...), user: User = Depends(admin_user)):
    with db() as conn:
        return people.add_faculty(conn, user, payload)


@router.put("/api/master/faculty/{emp_id}")
def api_update_faculty(emp_id: str, payload: Dict[str, Any] = Body(...), user: User = Depends(admin_user)):
    with db() as conn:
        people.update_faculty(conn, user, emp_id.upper(), payload)
    return {"success": True}


@router.put("/api/master/faculty/{emp_id}/roles")
def api_faculty_roles(emp_id: str, payload: Dict[str, Any] = Body(...), user: User = Depends(admin_user)):
    with db() as conn:
        people.set_roles(conn, user, emp_id.upper(), payload.get("roles", []))
    return {"success": True}


@router.post("/api/master/faculty/{emp_id}/reset-password")
def api_faculty_reset(emp_id: str, user: User = Depends(admin_user)):
    with db() as conn:
        return {"emp_id": emp_id.upper(), "temp_password": people.reset_password(conn, user, emp_id.upper())}


@router.get("/api/master/faculty-template")
def api_faculty_template(user: User = Depends(admin_user)):
    return Response(excel_templates.faculty_workbook(), media_type=XLSX, headers={"Content-Disposition": 'attachment; filename="faculty_template.xlsx"'})


@router.post("/api/master/faculty/upload")
async def api_faculty_upload(file: UploadFile = File(...), user: User = Depends(admin_user)):
    data = await _file(file)
    with db() as conn:
        return people.upload_faculty(conn, user, data)


@router.get("/api/master/faculty-form-choices")
def api_faculty_choices(user: User = Depends(admin_user)):
    with db() as conn:
        return Response(people.form_choices(conn), media_type="text/plain; charset=utf-8")


# ================================================================ person pages (everything one person has entered, segregated)
@router.get("/api/master/faculty/{emp_id}/profile")
def api_faculty_profile(emp_id: str, ay_id: Optional[str] = None, user: User = Depends(staff_user)):
    with db() as conn:
        return profiles.faculty_profile(conn, user, emp_id, ay_id or None)


@router.get("/api/master/students/{roll_no}/profile")
def api_student_profile(roll_no: str, ay_id: Optional[str] = None, user: User = Depends(staff_user)):
    with db() as conn:
        return profiles.student_profile(conn, user, roll_no, ay_id or None)


# ================================================================ Reports (Admin, HoD, programme coordinators): one kind of work across the department
@router.get("/api/master/works/catalog")
def api_works_catalog(ay_id: Optional[str] = None, user: User = Depends(staff_user)):
    with db() as conn:
        return works.catalog(conn, user, ay_id or None)


@router.get("/api/master/works")
def api_works(request: Request, user: User = Depends(staff_user)):
    q = dict(request.query_params)                  # the filters differ per kind of work; works.py accepts only its own list
    try:
        limit, offset = min(max(int(q.pop("limit", 50)), 1), 2000), max(int(q.pop("offset", 0)), 0)
    except ValueError:
        raise HTTPException(400, "limit and offset must be numbers")
    with db() as conn:
        return works.list_works(conn, user, q.pop("group", ""), q.pop("category", ""), q, limit, offset)


@router.get("/api/master/works/export")
def api_works_export(request: Request, user: User = Depends(staff_user)):
    q = dict(request.query_params)
    group, category = q.pop("group", ""), q.pop("category", "")
    columns = [c for c in q.pop("columns", "").split(",") if c]
    for k in ("limit", "offset"):
        q.pop(k, None)
    with db() as conn:
        data = works.export_csv(conn, user, group, category, q, columns)
    return Response(data, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="work.csv"'})


# ================================================================ form submissions
@router.get("/api/master/submissions")
def api_submissions(form_type: Optional[str] = None, ay_id: Optional[str] = None, category: Optional[str] = None, submitter: Optional[str] = None,
                    date_from: Optional[str] = None, date_to: Optional[str] = None, q: Optional[str] = None, roll_no: Optional[str] = None,
                    class_id: Optional[int] = None, level: Optional[str] = None, landmark: bool = False, has_media: bool = False,
                    limit: int = 100, offset: int = 0, user: User = Depends(staff_user)):
    f = _filters(locals())
    with db() as conn:
        return submissions.list_submissions(conn, user, f, min(limit, 500), offset)


@router.get("/api/master/submissions/unmatched")
def api_unmatched(user: User = Depends(admin_user)):
    with db() as conn:
        return submissions.unmatched(conn, user)


@router.get("/api/master/submissions/{sid}")
def api_submission(sid: int, user: User = Depends(staff_user)):
    with db() as conn:
        return submissions.get_submission(conn, user, sid)


@router.get("/api/master/forms/{form_id}/template")
def api_form_template(form_id: str, user: User = Depends(admin_user)):
    if form_id not in ingest.specs()["forms"]:
        raise HTTPException(404, "Unknown form")
    return _xlsx(f"{form_id}_template.xlsx", ["Timestamp", "Email Address"] + ingest.template_headers(form_id))


@router.post("/api/master/forms/{form_id}/upload")
async def api_form_upload(form_id: str, file: UploadFile = File(...), user: User = Depends(admin_user)):
    if form_id not in ingest.specs()["forms"]:
        raise HTTPException(404, "Unknown form")
    return ingest.upload_excel(form_id, await _file(file))


# ================================================================ placements (uploaded by the Admin; everyone else only reads, within their scope)
@router.get("/api/master/placements/template")
def api_placement_template(user: User = Depends(admin_user)):
    return _xlsx("placements_template.xlsx", placements.template_headers(), placements.EXAMPLE)


@router.post("/api/master/placements/upload")
async def api_placement_upload(file: UploadFile = File(...), ay_id: Optional[str] = Form(None), user: User = Depends(admin_user)):
    data = await _file(file)
    with db() as conn:
        return placements.upload_placements(conn, user, data, ay_id)


@router.get("/api/master/placements/offers")
def api_placement_offers(ay_id: Optional[str] = None, org_id: Optional[int] = None, offer_type: Optional[str] = None, offer_status: Optional[str] = None,
                         class_id: Optional[int] = None, programme: Optional[str] = None, grp: Optional[str] = None, min_package: Optional[float] = None,
                         max_package: Optional[float] = None, q: Optional[str] = None, limit: int = 200, offset: int = 0, user: User = Depends(staff_user)):
    f = _filters(locals())
    with db() as conn:
        return placements.list_offers(conn, user, f, min(limit, 500), offset)


@router.get("/api/master/placements/profiles")
def api_placement_profiles(ay_id: Optional[str] = None, opt_status: Optional[str] = None, class_id: Optional[int] = None,
                           programme: Optional[str] = None, grp: Optional[str] = None, limit: int = 200, offset: int = 0, user: User = Depends(staff_user)):
    f = _filters(locals())
    with db() as conn:
        return placements.list_profiles(conn, user, f, min(limit, 500), offset)


@router.get("/api/master/placements/student/{roll_no}")
def api_placement_student(roll_no: str, user: User = Depends(staff_user)):
    with db() as conn:
        return placements.student_detail(conn, user, roll_no.upper())


# ================================================================ analytics
@router.get("/api/master/analytics")
def api_analytics(ay_id: Optional[str] = None, class_id: Optional[int] = None, programme: Optional[str] = None, user: User = Depends(staff_user)):
    with db() as conn:
        return analytics.overview(conn, user, ay_id, class_id, programme)


# ================================================================ student diary (any signed-in user; carries no PII)
@router.get("/api/diary/overview")
def api_diary_overview(user: User = Depends(current_user)):
    with db() as conn:
        return diary.overview(conn)


@router.get("/api/diary/companies")
def api_diary_companies(q: str = "", user: User = Depends(current_user)):
    with db() as conn:
        return diary.companies(conn, q)


@router.get("/api/diary/companies/{org_id}")
def api_diary_company(org_id: int, user: User = Depends(current_user)):
    with db() as conn:
        return diary.company(conn, org_id)
