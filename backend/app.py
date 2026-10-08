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
    get_entries, update_entry_status, get_audit_logs, save_generation_record
)
from backend.services.ingestion_service import IngestionService
from backend.services.docx_generator import DOCXGenerator
from backend.services.newsletter_builder import NewsletterBuilder
from backend.services.template_engine import TemplateEngine

app = FastAPI(
    title="IT Chronicles - Newsletter Automation System API",
    version="1.0.0",
    description="API for Form Ingestion, Canonical Content Repository, Editorial Workflow, DOCX Template Engine, and Master Newsletter Builder."
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
    csv_text = content.decode("utf-8", errors="ignore")
    results = ingestion_service.process_csv_upload(form_id, csv_text, issue_id=issue_id)
    return {"total_ingested": len(results), "results": results}

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

    gen_path = docx_generator.generate_section_docx(
        section=sec_info,
        subcategories=sec_info.get("subcategories", []),
        approved_entries=approved,
        output_path=out_file
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
        "total_entries": len(approved)
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
