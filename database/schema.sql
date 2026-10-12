-- IT Chronicles Newsletter Automation Database Schema (SQLite)

CREATE TABLE IF NOT EXISTS issues (
    issue_id TEXT PRIMARY KEY,
    academic_year TEXT NOT NULL,
    volume INTEGER NOT NULL,
    issue INTEGER NOT NULL,
    semester TEXT NOT NULL,
    publication_period TEXT NOT NULL,
    department_name TEXT NOT NULL,
    cover_title TEXT NOT NULL,
    status TEXT DEFAULT 'Draft', -- Draft, InReview, Assembled, Published
    metadata_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sections (
    section_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    display_order INTEGER NOT NULL,
    enabled BOOLEAN DEFAULT 1,
    template_file TEXT
);

CREATE TABLE IF NOT EXISTS categories (
    category_id TEXT PRIMARY KEY,
    section_id TEXT NOT NULL,
    name TEXT NOT NULL,
    display_order INTEGER DEFAULT 10,
    FOREIGN KEY (section_id) REFERENCES sections(section_id)
);

CREATE TABLE IF NOT EXISTS raw_responses (
    response_id TEXT PRIMARY KEY,
    form_id TEXT NOT NULL,
    issue_id TEXT NOT NULL,
    submitter_email TEXT,
    raw_json TEXT NOT NULL,
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (issue_id) REFERENCES issues(issue_id)
);

CREATE TABLE IF NOT EXISTS canonical_entries (
    entry_id TEXT PRIMARY KEY,
    response_id TEXT,
    issue_id TEXT NOT NULL,
    section_id TEXT NOT NULL,
    category_id TEXT NOT NULL,
    title TEXT NOT NULL,
    author_or_person TEXT NOT NULL,
    organization_or_venue TEXT,
    event_date TEXT NOT NULL,
    impact_or_indexing TEXT,
    grant_or_prize_amount TEXT,
    description TEXT NOT NULL,
    photo_url TEXT,
    photo_caption TEXT,
    evidence_url TEXT,
    badge_tag TEXT,
    featured_flag BOOLEAN DEFAULT 0,
    display_order INTEGER DEFAULT 100,
    approval_status TEXT DEFAULT 'Draft', -- Draft, Reviewed, Approved, Rejected
    rejection_reason TEXT,
    submitter_email TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (response_id) REFERENCES raw_responses(response_id),
    FOREIGN KEY (issue_id) REFERENCES issues(issue_id),
    FOREIGN KEY (section_id) REFERENCES sections(section_id),
    FOREIGN KEY (category_id) REFERENCES categories(category_id)
);

CREATE TABLE IF NOT EXISTS templates (
    template_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    section_id TEXT, -- NULL for Master template
    file_path TEXT NOT NULL,
    version INTEGER DEFAULT 1,
    status TEXT DEFAULT 'Published', -- Draft, Validated, Published, Archived
    placeholder_schema TEXT,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit_logs (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    action TEXT NOT NULL,
    performer TEXT DEFAULT 'System',
    details TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS generations (
    generation_id TEXT PRIMARY KEY,
    issue_id TEXT NOT NULL,
    generation_type TEXT NOT NULL, -- Section, Master
    section_id TEXT,
    output_file TEXT NOT NULL,
    format TEXT NOT NULL, -- docx, pdf
    entry_ids_json TEXT NOT NULL,
    template_version TEXT,
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (issue_id) REFERENCES issues(issue_id)
);
