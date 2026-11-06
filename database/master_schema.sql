-- IT Chronicles MASTER DATABASE - schema v1.0 (SQLite, WAL mode)
-- Primary keys: students.roll_no, faculty.emp_id. Classes are FIXED SLOTS (10 rows); students move between them.
-- Kept in its own file (master_system.db) so credentials / student data never mix with the newsletter DB.

-- =====================================================================
-- 1. ORGANISATION & PEOPLE
-- =====================================================================
CREATE TABLE IF NOT EXISTS academic_years (
    ay_id       TEXT PRIMARY KEY,                 -- '2025-26'
    start_date  DATE NOT NULL,
    end_date    DATE NOT NULL,
    is_current  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS faculty (
    emp_id          TEXT PRIMARY KEY,
    full_name       TEXT NOT NULL,
    email           TEXT NOT NULL UNIQUE,
    phone           TEXT,
    designation     TEXT,
    department      TEXT NOT NULL DEFAULT 'IT',
    qualification   TEXT,
    date_of_joining DATE,
    status          TEXT NOT NULL DEFAULT 'Active' CHECK (status IN ('Active','OnLeave','Relieved')),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- A class is a cohort identified by its tutor and semester. The year is worked out from the semester (2 per year;
-- UG 8 semesters, PG 4) and class_code follows it, so setting the semester is all a tutor does: nobody is promoted.
-- Two classes can be in the same year at the same time. Admin changes the tutor and adds classes.
CREATE TABLE IF NOT EXISTS classes (
    class_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    class_code       TEXT NOT NULL UNIQUE,        -- 'UG-G1-3', 'PG-1'
    programme        TEXT NOT NULL CHECK (programme IN ('UG','PG')),
    grp              TEXT CHECK (grp IN ('G1','G2')),
    year_no          INTEGER NOT NULL CHECK (year_no BETWEEN 1 AND 4),
    current_semester INTEGER NOT NULL CHECK (current_semester BETWEEN 1 AND 8),
    ay_id            TEXT NOT NULL REFERENCES academic_years(ay_id),
    tutor_id         TEXT REFERENCES faculty(emp_id),
    status           TEXT NOT NULL DEFAULT 'Active' CHECK (status IN ('Active','Completed')),
    CHECK ((programme = 'UG' AND grp IS NOT NULL) OR (programme = 'PG' AND grp IS NULL AND year_no <= 2))
);

CREATE TABLE IF NOT EXISTS class_term_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id    INTEGER NOT NULL REFERENCES classes(class_id),
    ay_id       TEXT NOT NULL,
    semester_no INTEGER NOT NULL,
    changed_by  TEXT,
    changed_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS class_tutor_history (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id  INTEGER NOT NULL REFERENCES classes(class_id),
    tutor_id  TEXT,
    from_date DATE NOT NULL,
    to_date   DATE
);

-- Only what achievements, participations and placements need to be linked to a person. Everything academic
-- (CGPA, attendance, gender, residence, contact details...) stays in the college main database and is not copied here.
CREATE TABLE IF NOT EXISTS students (
    roll_no          TEXT PRIMARY KEY,
    full_name        TEXT NOT NULL,
    programme        TEXT NOT NULL CHECK (programme IN ('UG','PG')),
    class_id         INTEGER REFERENCES classes(class_id),   -- NULL once graduated / removed
    status           TEXT NOT NULL DEFAULT 'Active' CHECK (status IN ('Active','Graduated','Discontinued','Removed')),
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_students_class ON students(class_id, status);

-- Every move (added / removed / transferred / graduated); lets analytics find the class a student was in on any date.
CREATE TABLE IF NOT EXISTS student_class_history (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    roll_no   TEXT NOT NULL REFERENCES students(roll_no),
    class_id  INTEGER REFERENCES classes(class_id),
    from_date DATE NOT NULL,
    to_date   DATE,
    action    TEXT NOT NULL,
    done_by   TEXT
);
CREATE INDEX IF NOT EXISTS idx_sch_roll ON student_class_history(roll_no, from_date);

-- Login accounts. user_id = faculty.emp_id (STAFF) or students.roll_no (STUDENT).
CREATE TABLE IF NOT EXISTS users (
    user_id         TEXT PRIMARY KEY,
    user_type       TEXT NOT NULL CHECK (user_type IN ('STAFF','STUDENT')),
    password_hash   TEXT NOT NULL,
    must_change     INTEGER NOT NULL DEFAULT 1,
    last_login      TIMESTAMP
);

-- Roles beyond Tutor (which is derived from classes.tutor_id). PC scope = programme + grp (UG/G1, UG/G2, PG/NULL).
CREATE TABLE IF NOT EXISTS role_assignments (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    emp_id    TEXT NOT NULL REFERENCES faculty(emp_id),
    role      TEXT NOT NULL CHECK (role IN ('ADMIN','HOD','PC')),
    programme TEXT CHECK (programme IN ('UG','PG')),
    grp       TEXT CHECK (grp IN ('G1','G2'))
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_role ON role_assignments(emp_id, role, ifnull(programme,''), ifnull(grp,''));

CREATE TABLE IF NOT EXISTS organizations (
    org_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name     TEXT NOT NULL,
    name_key TEXT NOT NULL UNIQUE,                 -- lower-cased, punctuation stripped: "TCS" = "tcs." = "T.C.S"
    org_type TEXT,
    sector   TEXT,
    website  TEXT
);

-- =====================================================================
-- 2. FORM SUBMISSIONS (5 forms): common header + one typed table per form
-- =====================================================================
CREATE TABLE IF NOT EXISTS form_submissions (
    submission_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    form_type        TEXT NOT NULL CHECK (form_type IN ('STUDENT','RESEARCH','FACULTY','DEPARTMENT','OUTREACH')),
    ay_id            TEXT REFERENCES academic_years(ay_id),
    submitted_at     TIMESTAMP,
    submitter_email  TEXT,
    submitter_emp_id TEXT REFERENCES faculty(emp_id),
    event_date       DATE,
    category         TEXT,
    title            TEXT,
    evidence_url     TEXT,
    media_url        TEXT,
    photo_caption    TEXT,
    badge_tag        TEXT,
    is_landmark      INTEGER NOT NULL DEFAULT 0,
    publish_permission INTEGER,
    authorization_confirmed INTEGER,
    newsletter_entry_id TEXT,
    source_row_hash  TEXT NOT NULL UNIQUE,         -- same Excel row imported twice = one record
    raw_json         TEXT NOT NULL,                -- original row, never lost
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_sub_type_ay ON form_submissions(form_type, ay_id);
CREATE INDEX IF NOT EXISTS idx_sub_date    ON form_submissions(event_date);
CREATE INDEX IF NOT EXISTS idx_sub_emp     ON form_submissions(submitter_emp_id);

CREATE TABLE IF NOT EXISTS student_achievements (
    submission_id     INTEGER PRIMARY KEY REFERENCES form_submissions(submission_id) ON DELETE CASCADE,
    entry_kind        TEXT NOT NULL DEFAULT 'ACHIEVEMENT' CHECK (entry_kind IN ('ACHIEVEMENT','PARTICIPATION')),
    is_team           INTEGER NOT NULL DEFAULT 0,
    result_date       DATE,
    event_start       DATE,
    event_end         DATE,
    organizer         TEXT,
    level             TEXT,
    position          TEXT,
    prize_amount      REAL,
    domain            TEXT,
    mentor_emp_id     TEXT REFERENCES faculty(emp_id),
    project_statement TEXT,
    abstract          TEXT,
    tools_used        TEXT,
    measurable_impact TEXT,
    demo_url          TEXT,
    learning_outcomes TEXT,
    previously_reported INTEGER,
    related_awards    TEXT
);

-- Who took part. Unresolved roll numbers keep roll_no NULL + raw_text so they can be fixed, never silently dropped.
CREATE TABLE IF NOT EXISTS student_achievement_participants (
    submission_id INTEGER NOT NULL REFERENCES student_achievements(submission_id) ON DELETE CASCADE,
    line_no       INTEGER NOT NULL,
    roll_no       TEXT REFERENCES students(roll_no),
    raw_text      TEXT,
    name          TEXT,
    role          TEXT,
    is_lead       INTEGER NOT NULL DEFAULT 0,
    class_id_snapshot INTEGER REFERENCES classes(class_id),
    year_snapshot     INTEGER,
    semester_snapshot INTEGER,
    PRIMARY KEY (submission_id, line_no)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_sap_roll  ON student_achievement_participants(roll_no);
CREATE INDEX IF NOT EXISTS idx_sap_class ON student_achievement_participants(class_id_snapshot);

CREATE TABLE IF NOT EXISTS research_outputs (
    submission_id    INTEGER PRIMARY KEY REFERENCES form_submissions(submission_id) ON DELETE CASCADE,
    current_status   TEXT,
    output_date      DATE,
    project_start    DATE,
    venue_publisher  TEXT,
    venue_url        TEXT,
    identifier       TEXT,
    indexing         TEXT,
    quartile         TEXT,
    impact_factor    REAL,
    conference_level TEXT,
    review_status    TEXT,
    funding_status   TEXT,
    funding_amount   REAL,
    collaborators    TEXT,
    contribution_statement TEXT,
    problem          TEXT,
    abstract         TEXT,
    methodology      TEXT,
    key_findings     TEXT,
    impact           TEXT,
    ip_status        TEXT,
    dataset_url      TEXT,
    related_refs     TEXT
);

CREATE TABLE IF NOT EXISTS research_contributors (
    submission_id INTEGER NOT NULL REFERENCES research_outputs(submission_id) ON DELETE CASCADE,
    author_order  INTEGER NOT NULL,
    person_type   TEXT NOT NULL CHECK (person_type IN ('FACULTY','STUDENT','EXTERNAL')),
    emp_id        TEXT REFERENCES faculty(emp_id),
    roll_no       TEXT REFERENCES students(roll_no),
    name          TEXT,
    affiliation   TEXT,
    PRIMARY KEY (submission_id, author_order)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_rc_emp  ON research_contributors(emp_id);
CREATE INDEX IF NOT EXISTS idx_rc_roll ON research_contributors(roll_no);

CREATE TABLE IF NOT EXISTS faculty_achievements (
    submission_id      INTEGER PRIMARY KEY REFERENCES form_submissions(submission_id) ON DELETE CASCADE,
    emp_id             TEXT REFERENCES faculty(emp_id),
    recognition_type   TEXT,
    host_org           TEXT,
    level              TEXT,
    start_date         DATE,
    end_date           DATE,
    city_venue         TEXT,
    designation_at_time TEXT,
    credential_no      TEXT,
    duration_hours     REAL,
    role_contribution  TEXT,
    selection_criteria TEXT,
    description        TEXT,
    outcome_impact     TEXT,
    is_team            INTEGER,
    other_contributors TEXT,
    organizer_url      TEXT,
    previously_reported INTEGER,
    extra_notes        TEXT
);
CREATE INDEX IF NOT EXISTS idx_fa_emp ON faculty_achievements(emp_id);

CREATE TABLE IF NOT EXISTS department_highlights (
    submission_id      INTEGER PRIMARY KEY REFERENCES form_submissions(submission_id) ON DELETE CASCADE,
    convener_emp_id    TEXT REFERENCES faculty(emp_id),
    highlight_type     TEXT,
    units_involved     TEXT,
    start_date         DATE,
    end_date           DATE,
    impl_status        TEXT,
    venue              TEXT,
    partner_bodies     TEXT,
    target_audience    TEXT,
    participant_count  INTEGER,
    overview           TEXT,
    objectives         TEXT,
    outputs            TEXT,
    success_indicators TEXT,
    infra_upgrade      TEXT,
    budget_amount      REAL,
    funding_source     TEXT,
    accreditation_link TEXT,
    challenges         TEXT,
    sustainability     TEXT,
    recognition        TEXT,
    related_initiatives TEXT,
    report_url         TEXT
);

CREATE TABLE IF NOT EXISTS outreach_activities (
    submission_id   INTEGER PRIMARY KEY REFERENCES form_submissions(submission_id) ON DELETE CASCADE,
    lead_emp_id     TEXT REFERENCES faculty(emp_id),
    activity_format TEXT,
    units_involved  TEXT,
    partner_org_id  INTEGER REFERENCES organizations(org_id),
    partner_type    TEXT,
    start_date      DATE,
    end_date        DATE,
    venue           TEXT,
    target_audience TEXT,
    expected_count  INTEGER,
    actual_count    INTEGER,
    objective       TEXT,
    summary_outcomes TEXT,
    agenda          TEXT,
    speakers        TEXT,
    mou_scope       TEXT,
    agreement_effective DATE,
    agreement_expiry    DATE,
    follow_up       TEXT,
    measurable_outcomes TEXT,
    budget_amount   REAL,
    feedback_summary TEXT,
    report_url      TEXT
);
CREATE INDEX IF NOT EXISTS idx_oa_partner ON outreach_activities(partner_org_id);

-- Faculty involved in an event/activity beyond the submitter (convener, coordinators, speakers...).
CREATE TABLE IF NOT EXISTS submission_faculty (
    submission_id INTEGER NOT NULL REFERENCES form_submissions(submission_id) ON DELETE CASCADE,
    emp_id        TEXT NOT NULL REFERENCES faculty(emp_id),
    role          TEXT NOT NULL,
    PRIMARY KEY (submission_id, emp_id, role)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_sf_emp ON submission_faculty(emp_id);

-- Students who attended a department / outreach event (optional roster on those forms).
CREATE TABLE IF NOT EXISTS event_participants (
    submission_id     INTEGER NOT NULL REFERENCES form_submissions(submission_id) ON DELETE CASCADE,
    roll_no           TEXT NOT NULL REFERENCES students(roll_no),
    class_id_snapshot INTEGER REFERENCES classes(class_id),
    PRIMARY KEY (submission_id, roll_no)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_ep_roll ON event_participants(roll_no);

-- =====================================================================
-- 3. PLACEMENTS  (uploads REPLACE a student's earlier rows for that academic year)
-- =====================================================================
CREATE TABLE IF NOT EXISTS placement_profiles (
    roll_no        TEXT NOT NULL REFERENCES students(roll_no),
    ay_id          TEXT NOT NULL REFERENCES academic_years(ay_id),
    opt_status     TEXT NOT NULL CHECK (opt_status IN ('OPTED_IN','OPTED_OUT')),
    opt_out_reason TEXT,
    updated_by     TEXT,
    updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (roll_no, ay_id)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS placement_offers (
    offer_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    roll_no       TEXT NOT NULL REFERENCES students(roll_no),
    ay_id         TEXT NOT NULL REFERENCES academic_years(ay_id),
    org_id        INTEGER NOT NULL REFERENCES organizations(org_id),
    offer_type    TEXT NOT NULL CHECK (offer_type IN ('FTE','INTERN','FTE+INTERN','INTERN_CONVERTED_FTE')),
    package_lpa   REAL,
    stipend_per_month REAL,
    job_role      TEXT,
    work_location TEXT,
    offer_date    DATE,
    offer_status  TEXT NOT NULL DEFAULT 'Accepted' CHECK (offer_status IN ('Accepted','Declined','Revoked','Pending')),
    is_on_campus  INTEGER,
    updated_by    TEXT,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_po_roll ON placement_offers(roll_no, ay_id);
CREATE INDEX IF NOT EXISTS idx_po_org  ON placement_offers(org_id, ay_id);

CREATE TABLE IF NOT EXISTS interview_experiences (
    exp_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    roll_no         TEXT NOT NULL REFERENCES students(roll_no),
    ay_id           TEXT NOT NULL REFERENCES academic_years(ay_id),
    org_id          INTEGER NOT NULL REFERENCES organizations(org_id),
    rounds_count    INTEGER,
    round_details   TEXT,
    difficulty      TEXT,
    questions_asked TEXT,
    result          TEXT,
    experience      TEXT,
    tips            TEXT,
    is_shareable    INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_ie_org ON interview_experiences(org_id, ay_id);
CREATE INDEX IF NOT EXISTS idx_ie_roll ON interview_experiences(roll_no, ay_id);

CREATE TABLE IF NOT EXISTS internship_experiences (
    exp_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    roll_no       TEXT NOT NULL REFERENCES students(roll_no),
    ay_id         TEXT NOT NULL REFERENCES academic_years(ay_id),
    org_id        INTEGER NOT NULL REFERENCES organizations(org_id),
    duration      TEXT,
    mode          TEXT,
    role          TEXT,
    tech_stack    TEXT,
    work_summary  TEXT,
    learnings     TEXT,
    rating        INTEGER CHECK (rating BETWEEN 1 AND 5),
    experience    TEXT,
    is_shareable  INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_ine_org ON internship_experiences(org_id, ay_id);
CREATE INDEX IF NOT EXISTS idx_ine_roll ON internship_experiences(roll_no, ay_id);

-- =====================================================================
-- 4. AUDIT
-- =====================================================================
CREATE TABLE IF NOT EXISTS master_audit_log (
    log_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    actor        TEXT,
    action       TEXT NOT NULL,
    entity       TEXT NOT NULL,
    entity_key   TEXT,
    details      TEXT,
    at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================================
-- 5. VIEWS
-- =====================================================================
-- Student Diary reads ONLY these three views: they carry no roll number, name, photo or any other identifier.
DROP VIEW IF EXISTS v_diary_offers;
CREATE VIEW v_diary_offers AS
SELECT o.org_id, g.name AS company, g.sector, o.ay_id, o.offer_type, o.package_lpa, o.stipend_per_month, o.job_role
FROM placement_offers o JOIN organizations g ON g.org_id = o.org_id
WHERE o.offer_status = 'Accepted';

DROP VIEW IF EXISTS v_diary_interviews;
CREATE VIEW v_diary_interviews AS
SELECT e.org_id, e.ay_id, e.rounds_count, e.round_details, e.difficulty, e.questions_asked, e.result, e.experience, e.tips
FROM interview_experiences e WHERE e.is_shareable = 1;

DROP VIEW IF EXISTS v_diary_internships;
CREATE VIEW v_diary_internships AS
SELECT e.org_id, e.ay_id, e.duration, e.mode, e.role, e.tech_stack, e.work_summary, e.learnings, e.rating, e.experience
FROM internship_experiences e WHERE e.is_shareable = 1;

-- One flat row per (student, achievement): drives every student filter and chart.
DROP VIEW IF EXISTS v_student_achievements;
CREATE VIEW v_student_achievements AS
SELECT p.roll_no, p.name AS student_name, p.is_lead, p.class_id_snapshot AS class_id, p.year_snapshot AS year_no,
       p.semester_snapshot AS semester_no, c.class_code, c.programme, c.grp,
       fs.submission_id, fs.ay_id, fs.event_date, fs.category, fs.title,
       a.level, a.position, a.prize_amount, a.domain, a.is_team, a.mentor_emp_id
FROM student_achievement_participants p
JOIN student_achievements a ON a.submission_id = p.submission_id
JOIN form_submissions fs    ON fs.submission_id = a.submission_id
LEFT JOIN classes c         ON c.class_id = p.class_id_snapshot
WHERE p.roll_no IS NOT NULL;
