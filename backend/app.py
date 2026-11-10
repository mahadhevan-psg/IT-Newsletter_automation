import os
import json
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Body, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from database.db_manager import (
    init_db, get_all_issues, get_issue, get_sections_and_categories,
    get_entries, update_entry_status, get_audit_logs, save_generation_record,
    get_visual_templates, get_visual_template, save_visual_template, delete_visual_template
)
from backend.services.ingestion_service import IngestionService
from backend.services.docx_generator import DOCXGenerator
from backend.services.newsletter_builder import NewsletterBuilder
from backend.services.template_engine import TemplateEngine
from backend.services.config_service import ConfigService, BUILTIN_LAYOUTS
from backend.services.front_matter_service import FrontMatterService, UPLOAD_DIR
from backend.services.master_sync import MasterSync
from backend.master.api import router as master_router
from backend.demo import mode as demo_mode
from backend.demo.api import router as demo_router
from backend.review.api import router as review_router
from backend.review import schedule as sheet_schedule
from database.master_db import init_master_db

app = FastAPI(
    title="IT Chronicles - Newsletter Automation System API",
    version="2.0.0",
    description="API for Form Schema Management, Visual Newsletter Template Designer, Form Ingestion, Canonical Repository, and Document Assembly."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ingestion_service = IngestionService()
docx_generator = DOCXGenerator()
newsletter_builder = NewsletterBuilder()
template_engine = TemplateEngine()
config_service = ConfigService(normalizer=ingestion_service.normalizer)
front_matter_service = FrontMatterService()
master_sync = MasterSync(normalizer=ingestion_service.normalizer)

# Initialize Databases on Startup
@app.on_event("startup")
def startup_event():
    init_db()
    if demo_mode.enabled():
        from backend.demo import seed as demo_seed      # DEMO_MODE=true: build the sample department, then reset it on a timer
        demo_seed.start()
    else:
        init_master_db()
    sheet_schedule.start()                       # the timer that pulls the Google Sheets (when the Admin has switched it on)

app.include_router(master_router)
app.include_router(demo_router)
app.include_router(review_router)


@app.get("/healthz", include_in_schema=False)
def healthz():
    """The hosting platform calls this to know the service is up: answers only if both databases can be read."""
    import sqlite3
    from database.db_manager import get_connection
    from database.master_db import db
    try:
        get_connection().execute("SELECT 1").fetchone()
        with db() as conn:
            conn.execute("SELECT 1").fetchone()
    except sqlite3.Error as e:
        return JSONResponse({"status": "unavailable", "detail": str(e)}, status_code=503)
    return {"status": "ok"}

# --- The newsletter API is for the Admin and the HoD ---
# Everything under /api/ that is not the portal, the diary or the sign-in has its own rules elsewhere; the rest (entries,
# forms, layouts, front pages, generated documents) needs a signed-in Admin or HoD. Uploaded photos stay readable so <img> tags work.
_OWN_AUTH = ("/api/auth/", "/api/master/", "/api/diary/", "/api/demo/", "/api/review/", "/api/sync/")


def _newsletter_denied(authorization):
    """None when the caller may use the newsletter API, else (status, message)."""
    from backend.master.auth import load_user, parse_token
    from database.master_db import db
    if not authorization or not authorization.startswith("Bearer "):
        return 401, "Please sign in"
    try:
        data = parse_token(authorization[7:])
    except HTTPException as e:
        return e.status_code, e.detail
    with db() as conn:
        user = load_user(conn, data["sub"], data["typ"])
    if not user or user.kind != "STAFF":
        return 401, "Please sign in"
    if not user.roles & {"ADMIN", "HOD"}:
        return 403, "The newsletter studio is for the Admin and the HoD"
    return None


@app.middleware("http")
async def newsletter_needs_login(request, call_next):
    path = request.url.path
    guarded = path.startswith("/api/") and not path.startswith(_OWN_AUTH) and request.method != "OPTIONS" \
        and not (path.startswith("/api/uploads/") and request.method == "GET")
    if guarded:
        denied = _newsletter_denied(request.headers.get("authorization"))
        if denied:
            return JSONResponse({"detail": denied[1]}, status_code=denied[0])
    return await call_next(request)


# --- Issue Endpoints ---
@app.get("/api/issues")
def list_issues():
    return get_all_issues()

@app.get("/api/issues/{issue_id}")
def get_issue_details(issue_id: str):
    iss = get_issue(issue_id)
    if not iss:
        raise HTTPException(status_code=404, detail="Issue not found")
    return iss

# --- Config & Taxonomy Endpoints ---
@app.get("/api/sections")
def list_sections():
    return get_sections_and_categories()

@app.get("/api/config/mappings")
def get_form_mappings():
    path = os.path.join(os.path.dirname(__file__), "..", "config", "form_mappings.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

# --- Dynamic Forms & Schema Management Endpoints ---
@app.get("/api/forms/canonical-tags")
def get_canonical_tags():
    return config_service.get_canonical_field_options()

@app.get("/api/forms")
def list_forms():
    return config_service.get_all_forms()

class ScriptPayload(BaseModel):
    script: str

@app.post("/api/forms/parse-script")
def parse_form_script_endpoint(payload: ScriptPayload):
    """Read a Google Apps Script that creates forms and return the questions it contains (nothing is saved)."""
    forms = config_service.analyze_script(payload.script)
    if not forms:
        raise HTTPException(status_code=400, detail="No form questions found. Paste the Apps Script that calls FormApp.create(...).")
    return forms

@app.get("/api/forms/{form_id}")
def get_form_details(form_id: str):
    form = config_service.get_form(form_id)
    if not form:
        raise HTTPException(status_code=404, detail=f"Form '{form_id}' not found")
    return form

@app.post("/api/forms")
def create_new_form(payload: Dict[str, Any] = Body(...)):
    try:
        new_form = config_service.create_form(payload)
        return {"success": True, "form": new_form}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.put("/api/forms/{form_id}")
def update_form_definition(form_id: str, payload: Dict[str, Any] = Body(...)):
    try:
        updated_form = config_service.update_form(form_id, payload)
        return {"success": True, "form": updated_form}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/api/forms/{form_id}")
def remove_form(form_id: str):
    success = config_service.delete_form(form_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Form '{form_id}' not found")
    return {"success": True, "deleted_form_id": form_id}

@app.post("/api/forms/{form_id}/columns")
def add_or_update_column_endpoint(form_id: str, payload: Dict[str, Any] = Body(...)):
    try:
        res = config_service.add_or_update_column(form_id, payload)
        return {"success": True, "form": res}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/api/forms/{form_id}/columns/{column_name}")
def delete_column_endpoint(form_id: str, column_name: str):
    try:
        res = config_service.delete_column(form_id, column_name)
        return {"success": True, "form": res}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class BulkHeadersPayload(BaseModel):
    headers_text: str

@app.post("/api/forms/{form_id}/columns/bulk")
def bulk_import_headers(form_id: str, payload: BulkHeadersPayload):
    try:
        res = config_service.bulk_import_columns(form_id, payload.headers_text)
        return {"success": True, "form": res}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# --- Visual Template Designer Endpoints ---
@app.get("/api/visual-templates")
def list_visual_templates():
    return get_visual_templates()

@app.get("/api/visual-templates/{template_id}")
def get_visual_template_details(template_id: str):
    tpl = get_visual_template(template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="Visual template not found")
    return tpl

class VisualTemplateSavePayload(BaseModel):
    template_id: str
    name: str
    section_id: Optional[str] = None
    form_id: Optional[str] = None
    layout: List[Dict[str, Any]]
    is_default: Optional[bool] = False

@app.post("/api/visual-templates")
def save_visual_template_endpoint(payload: VisualTemplateSavePayload):
    try:
        saved_id = save_visual_template(
            template_id=payload.template_id,
            name=payload.name,
            section_id=payload.section_id,
            form_id=payload.form_id,
            layout_data=payload.layout,
            is_default=payload.is_default or False
        )
        return {"success": True, "template_id": saved_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/api/visual-templates/{template_id}")
def delete_visual_template_endpoint(template_id: str):
    success = delete_visual_template(template_id)
    if not success:
        raise HTTPException(status_code=404, detail="Template not found")
    config_service.clear_layout_assignments(template_id)
    return {"success": True, "deleted_template_id": template_id}

# --- Which layout each section's Word documents use (layouts are shared by all sections) ---
@app.get("/api/section-layouts")
def get_section_layouts():
    return config_service.get_section_layouts()

class SectionLayoutPayload(BaseModel):
    template_id: Optional[str] = None   # null/empty = standard built-in style

@app.get("/api/builtin-layouts")
def list_builtin_layouts():
    return [{"template_id": k, "name": v["name"], "description": v["description"]} for k, v in BUILTIN_LAYOUTS.items()]

@app.put("/api/section-layouts/{section_id}")
def set_section_layout(section_id: str, payload: SectionLayoutPayload):
    if payload.template_id and payload.template_id not in BUILTIN_LAYOUTS and not get_visual_template(payload.template_id):
        raise HTTPException(status_code=404, detail="Layout not found")
    config_service.set_section_layout(section_id, payload.template_id)
    return {"success": True, "section_id": section_id, "template_id": payload.template_id}

# --- Front pages: HOD's Desk, vision / mission, editorial board ---
@app.get("/api/front-matter")
def get_front_matter():
    return front_matter_service.get()

@app.put("/api/front-matter")
def save_front_matter(payload: Dict[str, Any] = Body(...)):
    return front_matter_service.save(payload)

@app.post("/api/uploads")
async def upload_photo(file: UploadFile = File(...)):
    try:
        path = front_matter_service.save_upload(file.filename, await file.read())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"path": path, "url": "/" + path.replace("output/uploads/", "api/uploads/")}

@app.get("/api/uploads/{filename}")
def get_uploaded_photo(filename: str):
    path = os.path.join(UPLOAD_DIR, os.path.basename(filename))
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path)

# --- Canonical Entries & Editorial Endpoints ---
@app.get("/api/entries")
def list_entries(
    issue_id: Optional[str] = None,
    section_id: Optional[str] = None,
    approval_status: Optional[str] = None
):
    return get_entries(issue_id=issue_id, section_id=section_id, approval_status=approval_status)

class StatusUpdateRequest(BaseModel):
    approval_status: str # Draft, Reviewed, Approved, Rejected
    rejection_reason: Optional[str] = None
    featured_flag: Optional[bool] = None
    display_order: Optional[int] = None
    performer: Optional[str] = "Editor"

@app.post("/api/entries/{entry_id}/status")
def update_status(entry_id: str, req: StatusUpdateRequest):
    success = update_entry_status(
        entry_id=entry_id,
        status=req.approval_status,
        rejection_reason=req.rejection_reason,
        featured_flag=req.featured_flag,
        display_order=req.display_order,
        performer=req.performer
    )
    if not success:
        raise HTTPException(status_code=404, detail="Entry not found or update failed")
    return {"success": True, "entry_id": entry_id, "new_status": req.approval_status}

# --- Master database -> newsletter entries ---
class MasterSyncRequest(BaseModel):
    issue_id: str = "ISSUE_2026_V1I1"
    ay_id: Optional[str] = None      # only submissions of this academic year ('2025-26'); default all

@app.post("/api/entries/sync-master")
def sync_from_master(req: MasterSyncRequest = Body(default_factory=MasterSyncRequest)):
    """Pull form submissions that have not reached the newsletter yet out of the master database."""
    return master_sync.sync(issue_id=req.issue_id, ay_id=req.ay_id)

# --- Form Ingestion Endpoints ---
class SubmissionPayload(BaseModel):
    form_id: str
    issue_id: Optional[str] = "ISSUE_2026_V1I1"
    raw_data: Dict[str, Any]

@app.post("/api/entries/ingest")
def ingest_form_submission(payload: SubmissionPayload):
    result = ingestion_service.process_single_submission(
        form_id=payload.form_id,
        raw_data=payload.raw_data,
        issue_id=payload.issue_id
    )
    return result

@app.post("/api/entries/ingest-csv")
async def ingest_csv(form_id: str = Form(...), issue_id: str = Form("ISSUE_2026_V1I1"), file: UploadFile = File(...)):
    content = await file.read()
    filename = (file.filename or "").lower()
    
    if filename.endswith(".xlsx") or filename.endswith(".xls"):
        results = ingestion_service.process_excel_upload(form_id, content, issue_id=issue_id)
    else:
        csv_text = content.decode("utf-8", errors="ignore")
        results = ingestion_service.process_csv_upload(form_id, csv_text, issue_id=issue_id)
        
    duplicates = sum(1 for r in results if r.get("duplicate"))
    return {"total_ingested": len(results) - duplicates, "duplicates_skipped": duplicates, "results": results}

# --- Document Generation Endpoints ---
class SectionGenRequest(BaseModel):
    issue_id: str = "ISSUE_2026_V1I1"
    section_id: str
    entry_ids: Optional[List[str]] = None

@app.post("/api/generate/section/{section_id}")
def generate_section_docx_endpoint(section_id: str, req: SectionGenRequest):
    sections = get_sections_and_categories()
    sec_info = next((s for s in sections if s["section_id"] == section_id), None)
    if not sec_info:
        raise HTTPException(status_code=404, detail="Section not found")

    # Fetch approved entries
    approved = get_entries(issue_id=req.issue_id, section_id=section_id, approval_status="Approved")
    if req.entry_ids:
        approved = [e for e in approved if e["entry_id"] in req.entry_ids]

    output_dir = os.path.join(os.path.dirname(__file__), "..", "output")
    out_file = os.path.join(output_dir, f"Section_{section_id}_{req.issue_id}.docx")

    active_layout = config_service.get_active_layout(section_id)
    gen_path = docx_generator.generate_section_docx(
        section=sec_info,
        subcategories=sec_info.get("subcategories", []),
        approved_entries=approved,
        output_path=out_file,
        layout=active_layout["layout"] if active_layout else None,
        issue=get_issue(req.issue_id),
        mode=active_layout.get("mode") if active_layout else None
    )

    save_generation_record(
        issue_id=req.issue_id,
        generation_type="Section",
        section_id=section_id,
        output_file=gen_path,
        fmt="docx",
        entry_ids=[e["entry_id"] for e in approved]
    )

    return {
        "success": True,
        "file_path": gen_path,
        "filename": os.path.basename(gen_path),
        "total_entries": len(approved),
        "layout_used": active_layout["name"] if active_layout else None
    }

class MasterGenRequest(BaseModel):
    issue_id: str = "ISSUE_2026_V1I1"
    selected_section_ids: Optional[List[str]] = None
    selected_entry_ids: Optional[List[str]] = None
    include_front_pages: bool = True

@app.post("/api/generate/master")
def generate_master_newsletter(req: MasterGenRequest):
    res = newsletter_builder.assemble_newsletter(
        issue_id=req.issue_id,
        selected_section_ids=req.selected_section_ids,
        selected_entry_ids=req.selected_entry_ids,
        include_front_pages=req.include_front_pages
    )
    res["filename"] = os.path.basename(res["master_docx_path"])
    return res

@app.get("/api/downloads/{filename}")
def download_generated_file(filename: str):
    out_dir = os.path.join(os.path.dirname(__file__), "..", "output")
    path = os.path.join(out_dir, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path, filename=filename, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")

# --- System & Audit Endpoints ---
@app.get("/api/audit-logs")
def list_audit_logs():
    return get_audit_logs(limit=100)

# The old sign-in address still works: /login/ -> / (keeping ?next=...)
@app.get("/login", include_in_schema=False)
@app.get("/login/", include_in_schema=False)
def old_login_address(request: Request):
    return RedirectResponse("/" + (f"?{request.url.query}" if request.url.query else ""))


# One address per application. / is the sign-in page (the first thing anyone sees); after signing in, faculty go to
# /homepage/ (the form links, then /portal/) and students to /diary/. /newsletter/ is the studio for Admin and HoD.
# The sign-in page is mounted last because it matches everything else.
_root = os.path.join(os.path.dirname(__file__), "..")
for _url, _folder in (("/portal", "portal"), ("/diary", "diary"), ("/newsletter", "frontend"), ("/homepage", "homepage"), ("/", "signin")):
    _dir = os.path.join(_root, _folder)
    if os.path.exists(_dir):
        app.mount(_url, StaticFiles(directory=_dir, html=True), name=_folder)
