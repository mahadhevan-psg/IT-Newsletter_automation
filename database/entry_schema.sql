-- In-application data entry: editable form definitions (with versions), drafts, and photo metadata.
-- Images themselves are NEVER stored in the database: only files on disk (and Google Drive); this table holds their metadata.

-- One row per version of a form's definition. 'draft' is what the admin is editing, 'published' is what everyone uses (one per form),
-- older published versions become 'archived' and can be restored. form_id is one of the five forms, 'placement', or '_sections'
-- (the newsletter's sections and their categories).
CREATE TABLE IF NOT EXISTS form_definitions (
    def_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    form_id      TEXT NOT NULL,
    version      INTEGER NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('draft', 'published', 'archived')),
    spec_json    TEXT NOT NULL,
    note         TEXT,
    created_by   TEXT,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMP,
    UNIQUE (form_id, version)
);
CREATE INDEX IF NOT EXISTS idx_def_status ON form_definitions(form_id, status);

CREATE TABLE IF NOT EXISTS definition_events (
    event_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    form_id     TEXT,
    action      TEXT NOT NULL,
    actor       TEXT,
    detail_json TEXT,
    at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- A person's unfinished entry (saved automatically while they type).
CREATE TABLE IF NOT EXISTS entry_drafts (
    draft_id   TEXT PRIMARY KEY,
    owner_id   TEXT NOT NULL,
    form_id    TEXT NOT NULL,
    category   TEXT,
    data_json  TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_draft_owner ON entry_drafts(owner_id);

-- Uploaded photos / files. The file lives on disk (resized and compressed) and, once uploaded, in Google Drive.
CREATE TABLE IF NOT EXISTS media_files (
    media_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id      TEXT NOT NULL,
    kind          TEXT NOT NULL DEFAULT 'PHOTO',
    original_name TEXT,
    sha256        TEXT NOT NULL,
    token         TEXT NOT NULL,
    width         INTEGER,
    height        INTEGER,
    bytes         INTEGER,
    local_path    TEXT,
    thumb_path    TEXT,
    drive_file_id TEXT,
    drive_url     TEXT,
    drive_status  TEXT NOT NULL DEFAULT 'LOCAL' CHECK (drive_status IN ('LOCAL', 'QUEUED', 'UPLOADED', 'FAILED')),
    drive_error   TEXT,
    attempts      INTEGER NOT NULL DEFAULT 0,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (owner_id, sha256)
);
