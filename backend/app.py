import os
import json
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Body
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
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
from backend.services.config_service import ConfigService

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

# Initialize Database on Startup
@app.on_event("startup")
def startup_event():
    init_db()

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

@app.put("/api/section-layouts/{section_id}")
def set_section_layout(section_id: str, payload: SectionLayoutPayload):
    if payload.template_id and not get_visual_template(payload.template_id):
        raise HTTPException(status_code=404, detail="Layout not found")
    config_service.set_section_layout(section_id, payload.template_id)
    return {"success": True, "section_id": section_id, "template_id": payload.template_id}

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
        issue=get_issue(req.issue_id)
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

@app.post("/api/generate/master")
def generate_master_newsletter(req: MasterGenRequest):
    res = newsletter_builder.assemble_newsletter(
        issue_id=req.issue_id,
        selected_section_ids=req.selected_section_ids,
        selected_entry_ids=req.selected_entry_ids
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

# Serve Frontend static assets
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
