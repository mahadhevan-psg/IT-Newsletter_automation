import sqlite3
import json
import os
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "newsletter_system.db")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        cursor.executescript(f.read())
    conn.commit()
    
    # Load default configs into DB if empty
    _seed_initial_configs(conn)
    conn.close()
    print("Database initialized successfully at:", DB_PATH)

def _seed_initial_configs(conn):
    cursor = conn.cursor()
    # Check if sections exist
    cursor.execute("SELECT COUNT(*) FROM sections")
    if cursor.fetchone()[0] == 0:
        sec_path = os.path.join(os.path.dirname(__file__), "..", "config", "section_categories.json")
        if os.path.exists(sec_path):
            with open(sec_path, "r", encoding="utf-8") as f:
                sec_data = json.load(f)
                for sec in sec_data.get("sections", []):
                    cursor.execute(
                        "INSERT INTO sections (section_id, name, display_order, enabled, template_file) VALUES (?, ?, ?, ?, ?)",
                        (sec["section_id"], sec["name"], sec["display_order"], sec["enabled"], sec.get("template_file", ""))
                    )
                    for cat in sec.get("subcategories", []):
                        cursor.execute(
                            "INSERT INTO categories (category_id, section_id, name, display_order) VALUES (?, ?, ?, ?)",
                            (cat["category_id"], sec["section_id"], cat["name"], cat.get("display_order", 10))
                        )

    # Check if default issue exists
    cursor.execute("SELECT COUNT(*) FROM issues")
    if cursor.fetchone()[0] == 0:
        meta_path = os.path.join(os.path.dirname(__file__), "..", "config", "issue_metadata_schema.json")
        if os.path.exists(meta_path):
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f).get("issue_metadata", {})
                cursor.execute(
                    """INSERT INTO issues (issue_id, academic_year, volume, issue, semester, publication_period, department_name, cover_title, status, metadata_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        meta["issue_id"], meta["academic_year"], meta["volume"], meta["issue"],
                        meta["semester"], meta["publication_period"], meta["department_name"],
                        meta["cover_title"], "Draft", json.dumps(meta)
                    )
                )
    conn.commit()

# --- Raw Responses Operations ---
def save_raw_response(form_id: str, issue_id: str, submitter_email: str, raw_json_data: dict) -> str:
    conn = get_connection()
    cursor = conn.cursor()
    response_id = f"RESP_{uuid.uuid4().hex[:8].upper()}"
    cursor.execute(
        "INSERT INTO raw_responses (response_id, form_id, issue_id, submitter_email, raw_json) VALUES (?, ?, ?, ?, ?)",
        (response_id, form_id, issue_id, submitter_email, json.dumps(raw_json_data))
    )
    conn.commit()
    conn.close()
    log_audit("raw_responses", response_id, "INGEST_RAW", details=f"Form {form_id} raw response ingested")
    return response_id

# --- Canonical Entries Operations ---
def create_canonical_entry(entry_data: dict) -> str:
    conn = get_connection()
    cursor = conn.cursor()
    entry_id = entry_data.get("entry_id") or f"ENTRY_{uuid.uuid4().hex[:8].upper()}"
    cursor.execute(
        """INSERT INTO canonical_entries (
            entry_id, response_id, issue_id, section_id, category_id, title, author_or_person,
            organization_or_venue, event_date, impact_or_indexing, grant_or_prize_amount,
            description, photo_url, evidence_url, featured_flag, display_order, approval_status,
            submitter_email
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            entry_id,
            entry_data.get("response_id"),
            entry_data.get("issue_id", "ISSUE_2026_V1I1"),
            entry_data.get("section_id"),
            entry_data.get("category_id"),
            entry_data.get("title", "Untitled"),
            entry_data.get("author_or_person", "N/A"),
            entry_data.get("organization_or_venue", ""),
            entry_data.get("event_date", ""),
            entry_data.get("impact_or_indexing", ""),
            entry_data.get("grant_or_prize_amount", ""),
            entry_data.get("description", ""),
            entry_data.get("photo_url", ""),
            entry_data.get("evidence_url", ""),
            1 if entry_data.get("featured_flag") else 0,
            entry_data.get("display_order", 100),
            entry_data.get("approval_status", "Draft"),
            entry_data.get("submitter_email", "")
        )
    )
    conn.commit()
    conn.close()
    log_audit("canonical_entries", entry_id, "CREATE_ENTRY", details=f"Canonical entry {entry_id} created")
    return entry_id

def get_entries(issue_id: Optional[str] = None, section_id: Optional[str] = None, approval_status: Optional[str] = None) -> List[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM canonical_entries WHERE 1=1"
    params = []
    if issue_id:
        query += " AND issue_id = ?"
        params.append(issue_id)
    if section_id:
        query += " AND section_id = ?"
        params.append(section_id)
    if approval_status:
        query += " AND approval_status = ?"
        params.append(approval_status)
    query += " ORDER BY display_order ASC, created_at DESC"
    
    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def update_entry_status(entry_id: str, status: str, rejection_reason: Optional[str] = None, featured_flag: Optional[bool] = None, display_order: Optional[int] = None, performer: str = "Editor") -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    
    updates = ["approval_status = ?", "updated_at = CURRENT_TIMESTAMP"]
    params = [status]
    
    if rejection_reason is not None:
        updates.append("rejection_reason = ?")
        params.append(rejection_reason)
    if featured_flag is not None:
        updates.append("featured_flag = ?")
        params.append(1 if featured_flag else 0)
    if display_order is not None:
        updates.append("display_order = ?")
        params.append(display_order)
        
    params.append(entry_id)
    query = f"UPDATE canonical_entries SET {', '.join(updates)} WHERE entry_id = ?"
    cursor.execute(query, params)
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    
    if affected > 0:
        log_audit("canonical_entries", entry_id, "UPDATE_STATUS", performer=performer, details=f"Status set to {status}, featured={featured_flag}, order={display_order}")
    return affected > 0

# --- Issues & Config Operations ---
def get_all_issues() -> List[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM issues ORDER BY created_at DESC")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_issue(issue_id: str) -> Optional[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM issues WHERE issue_id = ?", (issue_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_sections_and_categories() -> List[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sections ORDER BY display_order ASC")
    sections = [dict(r) for r in cursor.fetchall()]
    
    for sec in sections:
        cursor.execute("SELECT * FROM categories WHERE section_id = ? ORDER BY display_order ASC", (sec["section_id"],))
        sec["subcategories"] = [dict(c) for c in cursor.fetchall()]
        
    conn.close()
    return sections

def log_audit(entity_type: str, entity_id: str, action: str, performer: str = "System", details: str = ""):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO audit_logs (entity_type, entity_id, action, performer, details) VALUES (?, ?, ?, ?, ?)",
        (entity_type, entity_id, action, performer, details)
    )
    conn.commit()
    conn.close()

def get_audit_logs(limit: int = 100) -> List[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def save_generation_record(issue_id: str, generation_type: str, section_id: Optional[str], output_file: str, fmt: str, entry_ids: list, template_version: str = "1.0"):
    conn = get_connection()
    cursor = conn.cursor()
    gen_id = f"GEN_{uuid.uuid4().hex[:8].upper()}"
    cursor.execute(
        """INSERT INTO generations (generation_id, issue_id, generation_type, section_id, output_file, format, entry_ids_json, template_version)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (gen_id, issue_id, generation_type, section_id, output_file, fmt, json.dumps(entry_ids), template_version)
    )
    conn.commit()
    conn.close()
    log_audit("generations", gen_id, "GENERATE_DOC", details=f"Generated {generation_type} document: {output_file}")
    return gen_id

if __name__ == "__main__":
    init_db()
