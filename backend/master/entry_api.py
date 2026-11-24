"""/api/entry/* (entering data in the portal), /api/media/* (photos) and /api/defs/* (the Admin's form editor)."""
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from backend.master import definitions, entry, media
from backend.master.auth import User, admin_user, current_user, staff_user
from database.master_db import db

router = APIRouter()


# ================================================================ entering data
@router.get("/api/entry/catalog")
def api_catalog(user: User = Depends(staff_user)):
    with db() as conn:
        return {"forms": entry.catalog(conn), "drafts": entry.list_drafts(conn, user)}


@router.get("/api/entry/form")
def api_form(form_id: str, category: str, user: User = Depends(staff_user)):
    return entry.form_for(form_id, category)


@router.get("/api/entry/people")
def api_people(kind: str, q: str = "", user: User = Depends(staff_user)):
    with db() as conn:
        return entry.find_faculty(conn, q) if kind == "faculty" else entry.find_students(conn, q)


@router.get("/api/entry/rolls")
def api_rolls(text: str = "", user: User = Depends(staff_user)):
    with db() as conn:
        return entry.check_rolls(conn, text)


@router.post("/api/entry/submit")
def api_submit(payload: Dict[str, Any] = Body(...), user: User = Depends(staff_user)):
    with db() as conn:
        return entry.submit(conn, user, payload.get("form_id", ""), payload.get("category", ""), payload.get("values") or {}, payload.get("draft_id"))


@router.put("/api/entry/drafts/{draft_id}")
def api_save_draft(draft_id: str, payload: Dict[str, Any] = Body(...), user: User = Depends(staff_user)):
    with db() as conn:
        return entry.save_draft(conn, user, draft_id, payload.get("form_id", ""), payload.get("category", ""), payload.get("values") or {})


@router.get("/api/entry/drafts/{draft_id}")
def api_get_draft(draft_id: str, user: User = Depends(staff_user)):
    with db() as conn:
        return entry.get_draft(conn, user, draft_id)


@router.delete("/api/entry/drafts/{draft_id}")
def api_delete_draft(draft_id: str, user: User = Depends(staff_user)):
    with db() as conn:
        entry.delete_draft(conn, user, draft_id)
    return {"success": True}


# ================================================================ a student's placement record (entered from the Placements Diary)
def _student(user: User = Depends(current_user)) -> User:
    if user.kind != "STUDENT":
        raise HTTPException(403, "This is for students")
    return user


@router.get("/api/diary/my-record")
def api_my_record(user: User = Depends(_student)):
    with db() as conn:
        return entry.my_placement(conn, user)


@router.post("/api/diary/my-record")
def api_submit_record(payload: Dict[str, Any] = Body(...), user: User = Depends(_student)):
    with db() as conn:
        return entry.submit_placement(conn, user, payload)


@router.get("/api/entry/placement-preferences")
def api_pref_list(ay_id: str, class_id: Optional[int] = None, user: User = Depends(staff_user)):
    with db() as conn:
        return entry.class_preferences(conn, user, ay_id, class_id)


@router.put("/api/entry/placement-preferences")
def api_pref_save(payload: Dict[str, Any] = Body(...), user: User = Depends(staff_user)):
    with db() as conn:
        return entry.save_preferences(conn, user, payload.get("ay_id", ""), payload.get("rows") or [])


# ================================================================ photos
@router.post("/api/media")
async def api_upload(file: UploadFile = File(...), user: User = Depends(current_user)):
    content = await file.read(media.MAX_UPLOAD + 1)
    return media.save_upload(user.id, file.filename or "photo", content)


@router.get("/api/media/status")
def api_media_status(user: User = Depends(admin_user)):
    return media.status()


@router.post("/api/media/retry")
def api_media_retry(user: User = Depends(admin_user)):
    return {"requeued": media.retry_failed()}


@router.get("/api/media/{media_id}/{token}")
def api_media(media_id: int, token: str, thumb: int = 0):
    row = media.get(media_id)
    if not row or row["token"] != token:                      # the token is part of the file's hash: the address cannot be guessed
        raise HTTPException(404, "Not found")
    path = media.file_path(media_id, thumb=bool(thumb))
    if not path:
        raise HTTPException(404, "The file is not available")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})


# ================================================================ the Admin's form editor
@router.get("/api/defs/forms")
def api_defs_forms(user: User = Depends(admin_user)):
    with db() as conn:
        out = []
        for fid in definitions.FORM_IDS + [definitions.PLACEMENT]:
            v = definitions.editor_view(conn, fid)
            out.append({"form_id": fid, "title": entry.FORM_LABELS.get(fid) or "Student placement", "categories": len(v.get("categories", [])),
                        "fields": len([f for f in v["fields"] if not f.get("retired") and not f.get("section")]), "has_draft": v["has_draft"], "version": v["version"]})
        return out


@router.get("/api/defs/forms/{form_id}")
def api_defs_form(form_id: str, user: User = Depends(admin_user)):
    with db() as conn:
        return definitions.editor_view(conn, form_id)


@router.post("/api/defs/forms/{form_id}/ops")
def api_defs_op(form_id: str, payload: Dict[str, Any] = Body(...), user: User = Depends(admin_user)):
    with db() as conn:
        definitions.apply_op(conn, form_id, payload.get("op", ""), payload, user.id)
        return definitions.editor_view(conn, form_id)


@router.get("/api/defs/forms/{form_id}/impact")
def api_defs_impact(form_id: str, user: User = Depends(admin_user)):
    import json
    with db() as conn:
        spec = definitions.get_draft(conn, form_id, user.id) if definitions.has_draft(conn, form_id) else None
        return definitions.impact(conn, form_id, spec) if spec else {}


@router.post("/api/defs/forms/{form_id}/publish")
def api_defs_publish(form_id: str, payload: Dict[str, Any] = Body(default={}), user: User = Depends(admin_user)):
    with db() as conn:
        res = definitions.publish(conn, form_id, user.id, payload.get("note", ""))
        return {**res, "form": definitions.editor_view(conn, form_id)}


@router.post("/api/defs/forms/{form_id}/discard")
def api_defs_discard(form_id: str, user: User = Depends(admin_user)):
    with db() as conn:
        definitions.discard_draft(conn, form_id, user.id)
        return definitions.editor_view(conn, form_id)


@router.get("/api/defs/forms/{form_id}/history")
def api_defs_history(form_id: str, user: User = Depends(admin_user)):
    with db() as conn:
        return definitions.history(conn, form_id)


@router.post("/api/defs/forms/{form_id}/restore")
def api_defs_restore(form_id: str, payload: Dict[str, Any] = Body(...), user: User = Depends(admin_user)):
    with db() as conn:
        definitions.restore(conn, form_id, int(payload.get("version", 0)), user.id)
        return definitions.editor_view(conn, form_id)


@router.post("/api/defs/forms/{form_id}/reset")
def api_defs_reset(form_id: str, user: User = Depends(admin_user)):
    with db() as conn:
        definitions.reset_to_shipped(conn, form_id, user.id)
        return definitions.editor_view(conn, form_id)


@router.post("/api/defs/sections")
def api_defs_sections(payload: Dict[str, Any] = Body(...), user: User = Depends(admin_user)):
    with db() as conn:
        return definitions.sections_apply(conn, payload.get("op", ""), payload, user.id)
