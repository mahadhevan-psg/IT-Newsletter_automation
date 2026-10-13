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
    
    # Auto-migrate columns if missing
    cursor.execute("PRAGMA table_info(canonical_entries)")
    cols = [r[1] for r in cursor.fetchall()]
    if "photo_caption" not in cols:
        cursor.execute("ALTER TABLE canonical_entries ADD COLUMN photo_caption TEXT")
    if "badge_tag" not in cols:
        cursor.execute("ALTER TABLE canonical_entries ADD COLUMN badge_tag TEXT")
    if "extra_data_json" not in cols:
        cursor.execute("ALTER TABLE canonical_entries ADD COLUMN extra_data_json TEXT")
    conn.commit()

    # Create visual_templates table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS visual_templates (
        template_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        section_id TEXT,
        form_id TEXT,
        layout_json TEXT NOT NULL,
        is_default BOOLEAN DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    conn.commit()

    # Load default configs into DB if empty
    _seed_initial_configs(conn)
    _seed_default_visual_templates(conn)
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

def _seed_default_visual_templates(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM visual_templates")
    if cursor.fetchone()[0] == 0:
        default_templates = [
            {
                "template_id": "tpl_modern_spotlight",
                "name": "🌟 Modern Tech Executive Spotlight",
                "section_id": "sec_research",
                "form_id": "form_research",
                "is_default": 1,
                "layout": [
                    {
                        "id": "blk_badge_1",
                        "type": "badge",
                        "tag": "badge_tag",
                        "label": "Metric / Impact Badge",
                        "style": {"badgeColor": "navy", "textAlign": "left", "pill": True},
                        "placeholder": "Landmark Achievement"
                    },
                    {
                        "id": "blk_title_1",
                        "type": "text",
                        "tag": "title",
                        "label": "Article Headline",
                        "style": {"fontSize": "1.45rem", "fontWeight": "700", "textColor": "#1f4e78", "textAlign": "left"},
                        "placeholder": "Headline of the Achievement"
                    },
                    {
                        "id": "blk_byline_1",
                        "type": "text",
                        "tag": "author_or_person",
                        "label": "Contributor / Lead Author",
                        "style": {"fontSize": "0.95rem", "fontWeight": "600", "textColor": "#5a6b7c", "textAlign": "left"},
                        "placeholder": "Dr. Sarah Jenkins & Research Team"
                    },
                    {
                        "id": "blk_meta_1",
                        "type": "text",
                        "tag": "organization_or_venue",
                        "label": "Journal / Venue & Date",
                        "style": {"fontSize": "0.85rem", "fontWeight": "400", "textColor": "#64748b", "textAlign": "left"},
                        "placeholder": "IEEE Transactions on Cloud Computing"
                    },
                    {
                        "id": "blk_img_1",
                        "type": "image",
                        "tag": "photo_url",
                        "captionTag": "photo_caption",
                        "label": "Hero Image Box",
                        "style": {"aspectRatio": "16:9", "maxHeight": "240px", "borderRadius": "8px", "shadow": True},
                        "placeholder": "https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?w=800&auto=format&fit=crop&q=60"
                    },
                    {
                        "id": "blk_desc_1",
                        "type": "text",
                        "tag": "description",
                        "label": "Executive Summary & Highlights",
                        "style": {"fontSize": "0.95rem", "fontWeight": "400", "textColor": "#222222", "textAlign": "left", "lineHeight": "1.6"},
                        "placeholder": "Detailed description and highlights of the accomplishment..."
                    },
                    {
                        "id": "blk_link_1",
                        "type": "link",
                        "tag": "evidence_url",
                        "label": "Verification & Evidence Link",
                        "linkText": "🔗 View Publication / Certificate",
                        "style": {"buttonStyle": "solid", "bgColor": "#c65911", "textColor": "#ffffff"},
                        "placeholder": "https://doi.org/10.1109/TCC.2026.01"
                    },
                    {
                        "id": "blk_div_1",
                        "type": "divider",
                        "label": "Divider Line",
                        "style": {"borderColor": "#e2e8f0", "margin": "1rem 0"}
                    }
                ]
            },
            {
                "template_id": "tpl_academic_paper",
                "name": "📄 Academic Research & Journal Publication",
                "section_id": "sec_research",
                "form_id": "form_research",
                "is_default": 1,
                "layout": [
                    {
                        "id": "blk_badge_pub",
                        "type": "badge",
                        "tag": "impact_or_indexing",
                        "label": "Indexing Pill",
                        "style": {"badgeColor": "amber", "textAlign": "left", "pill": True},
                        "placeholder": "Scopus Indexed / Q1 Journal"
                    },
                    {
                        "id": "blk_title_pub",
                        "type": "text",
                        "tag": "title",
                        "label": "Paper Title",
                        "style": {"fontSize": "1.35rem", "fontWeight": "700", "textColor": "#1f4e78"},
                        "placeholder": "Deep Learning for Edge-Compute Anomaly Detection"
                    },
                    {
                        "id": "blk_author_pub",
                        "type": "text",
                        "tag": "author_or_person",
                        "label": "Authors List",
                        "style": {"fontSize": "0.95rem", "fontWeight": "600", "textColor": "#334155", "fontStyle": "italic"},
                        "placeholder": "K. Raman, L. Chen, S. Venkatesh"
                    },
                    {
                        "id": "blk_venue_pub",
                        "type": "text",
                        "tag": "organization_or_venue",
                        "label": "Journal / Publisher",
                        "style": {"fontSize": "0.85rem", "textColor": "#64748b"},
                        "placeholder": "Elsevier Computer Networks, Vol. 142"
                    },
                    {
                        "id": "blk_doi_badge",
                        "type": "badge",
                        "tag": "grant_or_prize_amount",
                        "label": "DOI / Grant Metric",
                        "style": {"badgeColor": "slate", "pill": False},
                        "placeholder": "DOI: 10.1016/j.comnet.2026.1098"
                    },
                    {
                        "id": "blk_desc_pub",
                        "type": "text",
                        "tag": "description",
                        "label": "Abstract / Summary",
                        "style": {"fontSize": "0.9rem", "textColor": "#333333"},
                        "placeholder": "This study introduces a latency-aware transformer model for edge devices..."
                    },
                    {
                        "id": "blk_link_pub",
                        "type": "link",
                        "tag": "evidence_url",
                        "label": "DOI Paper Link",
                        "linkText": "📄 Read Published Paper",
                        "style": {"buttonStyle": "solid", "bgColor": "#1f4e78", "textColor": "#ffffff"},
                        "placeholder": "https://doi.org"
                    }
                ]
            },
            {
                "template_id": "tpl_student_winner",
                "name": "🏆 Student Champion & Hackathon Showcase",
                "section_id": "sec_student",
                "form_id": "form_student",
                "is_default": 1,
                "layout": [
                    {
                        "id": "blk_badge_prize",
                        "type": "badge",
                        "tag": "grant_or_prize_amount",
                        "label": "Prize / Rank Pill",
                        "style": {"badgeColor": "amber", "pill": True},
                        "placeholder": "🥇 1st Place • Cash Prize ₹1,00,000"
                    },
                    {
                        "id": "blk_title_stu",
                        "type": "text",
                        "tag": "title",
                        "label": "Project / Hackathon Title",
                        "style": {"fontSize": "1.35rem", "fontWeight": "700", "textColor": "#1f4e78"},
                        "placeholder": "Autonomous Drone Fleet for Rural Medical Logistics"
                    },
                    {
                        "id": "blk_winner_stu",
                        "type": "text",
                        "tag": "author_or_person",
                        "label": "Student Name(s)",
                        "style": {"fontSize": "1rem", "fontWeight": "600", "textColor": "#0f2b48"},
                        "placeholder": "Priya Sharma (III IT), Rohan Mehta (III IT)"
                    },
                    {
                        "id": "blk_org_stu",
                        "type": "text",
                        "tag": "organization_or_venue",
                        "label": "Host Body / Hackathon",
                        "style": {"fontSize": "0.85rem", "textColor": "#64748b"},
                        "placeholder": "Smart India Hackathon 2026 - National Grand Finale"
                    },
                    {
                        "id": "blk_img_stu",
                        "type": "image",
                        "tag": "photo_url",
                        "captionTag": "photo_caption",
                        "label": "Ceremony / Trophy Photo",
                        "style": {"aspectRatio": "4:3", "maxHeight": "220px", "borderRadius": "8px"},
                        "placeholder": "https://images.unsplash.com/photo-1531482615713-2afd69097998?w=800&auto=format&fit=crop&q=60"
                    },
                    {
                        "id": "blk_desc_stu",
                        "type": "text",
                        "tag": "description",
                        "label": "Project Abstract",
                        "style": {"fontSize": "0.95rem", "textColor": "#334155"},
                        "placeholder": "Developed an end-to-end telemetry system enabling autonomous delivery routing..."
                    },
                    {
                        "id": "blk_link_stu",
                        "type": "link",
                        "tag": "evidence_url",
                        "label": "GitHub / Proof Link",
                        "linkText": "🏆 View Certificate & Project Demo",
                        "style": {"buttonStyle": "solid", "bgColor": "#1f4e78", "textColor": "#ffffff"},
                        "placeholder": "https://github.com/neuralpulse/drone-logistics"
                    }
                ]
            },
            {
                "template_id": "tpl_faculty_milestone",
                "name": "🎖️ Faculty Honors & Keynote Milestone",
                "section_id": "sec_faculty",
                "form_id": "form_faculty",
                "is_default": 1,
                "layout": [
                    {
                        "id": "blk_badge_fac",
                        "type": "badge",
                        "tag": "badge_tag",
                        "label": "Recognition Badge",
                        "style": {"badgeColor": "navy", "pill": True},
                        "placeholder": "Distinguished Faculty Award 2026"
                    },
                    {
                        "id": "blk_title_fac",
                        "type": "text",
                        "tag": "title",
                        "label": "Award / Keynote Title",
                        "style": {"fontSize": "1.35rem", "fontWeight": "700", "textColor": "#1f4e78"},
                        "placeholder": "National Excellence in AI Education Award"
                    },
                    {
                        "id": "blk_name_fac",
                        "type": "text",
                        "tag": "author_or_person",
                        "label": "Faculty Member",
                        "style": {"fontSize": "1.05rem", "fontWeight": "600", "textColor": "#0f2b48"},
                        "placeholder": "Dr. R. Arunkumar, Associate Professor"
                    },
                    {
                        "id": "blk_venue_fac",
                        "type": "text",
                        "tag": "organization_or_venue",
                        "label": "Conferred By / Institution",
                        "style": {"fontSize": "0.85rem", "textColor": "#64748b"},
                        "placeholder": "Indian Society for Technical Education (ISTE)"
                    },
                    {
                        "id": "blk_img_fac",
                        "type": "image",
                        "tag": "photo_url",
                        "captionTag": "photo_caption",
                        "label": "Faculty / Award Photo",
                        "style": {"aspectRatio": "1:1", "maxHeight": "180px", "borderRadius": "8px", "float": "left"},
                        "placeholder": "https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?w=800&auto=format&fit=crop&q=60"
                    },
                    {
                        "id": "blk_desc_fac",
                        "type": "text",
                        "tag": "description",
                        "label": "Citation & Highlights",
                        "style": {"fontSize": "0.95rem", "textColor": "#222222"},
                        "placeholder": "Conferred for pioneering high-performance pedagogical frameworks for machine learning..."
                    },
                    {
                        "id": "blk_link_fac",
                        "type": "link",
                        "tag": "evidence_url",
                        "label": "Certificate / News Link",
                        "linkText": "🎖️ View Official Citation",
                        "style": {"buttonStyle": "outline", "bgColor": "transparent", "textColor": "#1f4e78"},
                        "placeholder": "https://iste.org/awards/2026"
                    }
                ]
            }
        ]

        for tpl in default_templates:
            cursor.execute(
                """INSERT INTO visual_templates (template_id, name, section_id, form_id, layout_json, is_default)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (tpl["template_id"], tpl["name"], tpl["section_id"], tpl["form_id"], json.dumps(tpl["layout"]), tpl["is_default"])
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
    
    extra_json = entry_data.get("extra_data_json")
    if not extra_json and "extra_fields" in entry_data:
        extra_json = json.dumps(entry_data["extra_fields"])

    cursor.execute(
        """INSERT INTO canonical_entries (
            entry_id, response_id, issue_id, section_id, category_id, title, author_or_person,
            organization_or_venue, event_date, impact_or_indexing, grant_or_prize_amount,
            description, photo_url, photo_caption, evidence_url, badge_tag, featured_flag, display_order, approval_status,
            submitter_email, extra_data_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
            entry_data.get("photo_caption", ""),
            entry_data.get("evidence_url", ""),
            entry_data.get("badge_tag", ""),
            1 if entry_data.get("featured_flag") else 0,
            entry_data.get("display_order", 100),
            entry_data.get("approval_status", "Draft"),
            entry_data.get("submitter_email", ""),
            extra_json
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

# --- Visual Templates Operations ---
def get_visual_templates() -> List[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM visual_templates ORDER BY is_default DESC, name ASC")
    rows = []
    for r in cursor.fetchall():
        d = dict(r)
        try:
            d["layout"] = json.loads(d["layout_json"])
        except Exception:
            d["layout"] = []
        rows.append(d)
    conn.close()
    return rows

def get_visual_template(template_id: str) -> Optional[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM visual_templates WHERE template_id = ?", (template_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    try:
        d["layout"] = json.loads(d["layout_json"])
    except Exception:
        d["layout"] = []
    return d

def save_visual_template(template_id: str, name: str, section_id: Optional[str], form_id: Optional[str], layout_data: Any, is_default: bool = False) -> str:
    conn = get_connection()
    cursor = conn.cursor()
    
    layout_str = json.dumps(layout_data) if isinstance(layout_data, (list, dict)) else str(layout_data)
    
    cursor.execute("SELECT template_id FROM visual_templates WHERE template_id = ?", (template_id,))
    exists = cursor.fetchone()
    
    if exists:
        cursor.execute(
            """UPDATE visual_templates 
               SET name = ?, section_id = ?, form_id = ?, layout_json = ?, is_default = ?, updated_at = CURRENT_TIMESTAMP
               WHERE template_id = ?""",
            (name, section_id, form_id, layout_str, 1 if is_default else 0, template_id)
        )
    else:
        cursor.execute(
            """INSERT INTO visual_templates (template_id, name, section_id, form_id, layout_json, is_default)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (template_id, name, section_id, form_id, layout_str, 1 if is_default else 0)
        )
    conn.commit()
    conn.close()
    log_audit("visual_templates", template_id, "SAVE_TEMPLATE", details=f"Saved template: {name}")
    return template_id

def delete_visual_template(template_id: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM visual_templates WHERE template_id = ?", (template_id,))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    if affected > 0:
        log_audit("visual_templates", template_id, "DELETE_TEMPLATE", details=f"Deleted template: {template_id}")
    return affected > 0

# --- Sections and Categories Dynamic Operations ---
def add_or_update_section(section_id: str, name: str, display_order: int = 10, enabled: bool = True, template_file: str = "", subcategories: Optional[List[dict]] = None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT section_id FROM sections WHERE section_id = ?", (section_id,))
    if cursor.fetchone():
        cursor.execute(
            "UPDATE sections SET name = ?, display_order = ?, enabled = ?, template_file = ? WHERE section_id = ?",
            (name, display_order, 1 if enabled else 0, template_file, section_id)
        )
    else:
        cursor.execute(
            "INSERT INTO sections (section_id, name, display_order, enabled, template_file) VALUES (?, ?, ?, ?, ?)",
            (section_id, name, display_order, 1 if enabled else 0, template_file)
        )
    
    if subcategories:
        for cat in subcategories:
            cat_id = cat.get("category_id") or f"cat_{uuid.uuid4().hex[:6]}"
            cat_name = cat.get("name") or "Category"
            cat_order = cat.get("display_order", 10)
            cursor.execute("SELECT category_id FROM categories WHERE category_id = ?", (cat_id,))
            if cursor.fetchone():
                cursor.execute("UPDATE categories SET name = ?, display_order = ? WHERE category_id = ?", (cat_name, cat_order, cat_id))
            else:
                cursor.execute("INSERT INTO categories (category_id, section_id, name, display_order) VALUES (?, ?, ?, ?)", (cat_id, section_id, cat_name, cat_order))
                
    conn.commit()
    conn.close()

def delete_section(section_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM categories WHERE section_id = ?", (section_id,))
    cursor.execute("DELETE FROM sections WHERE section_id = ?", (section_id,))
    conn.commit()
    conn.close()

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


def get_raw_response(response_id: str) -> dict:
    """The answers exactly as submitted, keyed by question header."""
    conn = get_connection()
    row = conn.execute("SELECT raw_json FROM raw_responses WHERE response_id = ?", (response_id,)).fetchone()
    conn.close()
    try:
        return json.loads(row["raw_json"]) if row else {}
    except Exception:
        return {}
