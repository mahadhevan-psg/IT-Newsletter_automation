"""/api/review/* (the approval queue) and /api/sync/* (Google Sheet pulls and their schedule)."""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from backend.master.auth import User, admin_user, staff_user
from backend.review import schedule, service, sheets
from database.master_db import db

router = APIRouter()


# ================================================================ the approval queue
@router.get("/api/review/summary")
def api_summary(user: User = Depends(staff_user)):
    with db() as conn:
        return service.summary(conn, user)


@router.get("/api/review/items")
def api_items(request: Request, scope: str = "review", form_id: Optional[str] = None, q: Optional[str] = None, flagged: bool = False,
              status: Optional[str] = None, limit: int = 100, offset: int = 0, user: User = Depends(staff_user)):
    with db() as conn:
        return service.list_items(conn, user, scope, {"form_id": form_id, "q": q, "flagged": flagged, "status": status}, min(max(limit, 1), 500), max(offset, 0))


@router.get("/api/review/items/{item_id}")
def api_item(item_id: int, user: User = Depends(staff_user)):
    with db() as conn:
        return service.get_item(conn, user, item_id)


@router.post("/api/review/preview")
def api_preview(payload: Dict[str, Any] = Body(...), user: User = Depends(staff_user)):
    """Problems and resolved names for answers as they are being edited. Nothing is saved."""
    with db() as conn:
        return service.preview_answers(conn, payload.get("form_id", ""), payload.get("answers") or [])


@router.post("/api/review/items/{item_id}/approve")
def api_approve(item_id: int, payload: Dict[str, Any] = Body(default={}), user: User = Depends(staff_user)):
    with db() as conn:
        return service.approve(conn, user, item_id, payload.get("answers"), payload.get("note"))


@router.post("/api/review/items/{item_id}/reject")
def api_reject(item_id: int, payload: Dict[str, Any] = Body(default={}), user: User = Depends(staff_user)):
    with db() as conn:
        return service.reject(conn, user, item_id, payload.get("reason"), payload.get("send_to"))


@router.post("/api/review/items/{item_id}/resubmit")
def api_resubmit(item_id: int, payload: Dict[str, Any] = Body(default={}), user: User = Depends(staff_user)):
    with db() as conn:
        return service.resubmit(conn, user, item_id, payload.get("answers"), payload.get("note"))


@router.post("/api/review/items/{item_id}/revoke")
def api_revoke(item_id: int, user: User = Depends(staff_user)):
    with db() as conn:
        return service.revoke(conn, user, item_id)


@router.post("/api/review/items/{item_id}/reopen")
def api_reopen(item_id: int, user: User = Depends(staff_user)):
    with db() as conn:
        return service.reopen(conn, user, item_id)


@router.post("/api/review/bulk-approve")
def api_bulk(payload: Dict[str, Any] = Body(default={}), user: User = Depends(staff_user)):
    with db() as conn:
        return service.bulk_approve(conn, user, payload.get("ids"), bool(payload.get("all_clean")), payload.get("form_id"))


# ================================================================ Google Sheet pulls
def _may_pull(user: User) -> bool:
    return user.is_admin or "HOD" in user.roles or bool(user.tutor_class_ids)


@router.get("/api/sync/overview")
def api_sync_overview(user: User = Depends(staff_user)):
    if not _may_pull(user):
        raise HTTPException(403, "Only the Admin, the HoD and class tutors can see this")
    with db() as conn:
        out = schedule.overview(conn)
    out["can_configure"] = user.is_admin
    out["can_pull_forms"] = user.is_admin or "HOD" in user.roles
    out["can_pull_placements"] = _may_pull(user)
    if not user.is_admin:                                               # the links are not secret, but only the Admin edits them
        out["sources"] = [s for s in out["sources"] if out["can_pull_forms"] or s["form_id"] == service.PLACEMENT]
    return out


@router.put("/api/sync/settings")
def api_sync_settings(payload: Dict[str, Any] = Body(...), user: User = Depends(admin_user)):
    with db() as conn:
        s = schedule.save_settings(conn, user, payload)
        return schedule.overview(conn)["settings"]


@router.put("/api/sync/sources/{form_id}")
def api_sync_source(form_id: str, payload: Dict[str, Any] = Body(...), user: User = Depends(admin_user)):
    with db() as conn:
        schedule.set_source(conn, user, form_id, payload.get("sheet_url", ""))
    return {"success": True}


@router.post("/api/sync/test")
def api_sync_test(payload: Dict[str, Any] = Body(...), user: User = Depends(admin_user)):
    """'Test this link': read it and compare its columns with the form's questions. Nothing is stored."""
    if payload.get("form_id") not in schedule.SOURCES:
        raise HTTPException(400, "Unknown form")
    try:
        return sheets.check_source(payload["form_id"], (payload.get("sheet_url") or "").strip())
    except sheets.SheetError as e:
        raise HTTPException(400, str(e))


@router.post("/api/sync/run")
def api_sync_run(payload: Dict[str, Any] = Body(default={}), user: User = Depends(staff_user)):
    """Pull now. Admin and HoD: any sheet. A class tutor: only the placement sheet."""
    only = payload.get("only") or None
    if not (user.is_admin or "HOD" in user.roles):
        if not user.tutor_class_ids:
            raise HTTPException(403, "Only the Admin, the HoD and class tutors can pull")
        only = [service.PLACEMENT]
    return schedule.run_sync("manual", user.id, only)
