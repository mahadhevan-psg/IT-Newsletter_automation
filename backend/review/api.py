"""/api/review/*: the approval queue."""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from backend.master.auth import User, admin_user, staff_user
from backend.review import service
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
