# IT Chronicles Master Database - Final Design (v1.0)

Schema: [master_schema.sql](master_schema.sql) · opened by [master_db.py](master_db.py) · file `database/master_system.db` (git-ignored: it holds logins and student data).

## Decisions

| Question | Decision |
|---|---|
| Classes | A class is a **cohort known by its tutor and its semester**. Two semesters make a year (UG 8 semesters, PG 4); the tutor sets the semester and the **year and class code follow automatically** (UG-G1-2, PG-2; a second class in the same year gets the semester added, e.g. UG-G1-2-S4). Students stay in their class as it moves up, nobody is promoted. The Admin adds classes and changes tutors; a class in its last semester can be marked graduated. |
| Roles | One person can hold several. Tutor comes from `classes.tutor_id`; Admin / HoD / Programme Coordinator from `role_assignments`. |
| Verification of submissions | None - every upload counts immediately. |
| Form responses and placement data | Uploaded by the **Admin only** (the Google Forms response sheets as Excel). Uploading a student's placement rows again **replaces** that student's rows for the academic year. |
| Database engine | **SQLite in WAL mode.** See below. |

### Why SQLite is the right engine here
Five to six years of this department is roughly 3,000 students, ~15,000 submissions (≈40,000 student/author links) and ~2,000 offers: **tens of MB, well under 100 MB** even though every original form row is kept as JSON. WAL mode lets many people read while one writes, and writes are short uploads. It needs no server to run or back up (copy one file). The schema uses plain SQL and integer/text keys, so moving to PostgreSQL later is mechanical (`AUTOINCREMENT`→`SERIAL`, `ifnull`→`COALESCE`, drop `WITHOUT ROWID`). Revisit only if many simultaneous *writers* appear.

## Tables (26) and views (4)

| Group | Tables |
|---|---|
| Organisation | `academic_years`, `faculty`, `classes`, `class_term_history`, `class_tutor_history`, `students`, `student_class_history`, `organizations` |
| Access | `users` (staff and student logins), `role_assignments` (ADMIN / HOD / PC) |
| Submissions | `form_submissions` (common header, original row, de-dup hash) + `student_achievements`, `research_outputs`, `faculty_achievements`, `department_highlights`, `outreach_activities` |
| Links to people | `student_achievement_participants`, `research_contributors` (faculty / student / external), `submission_faculty`, `event_participants` |
| Placements | `placement_profiles` (opted in / out), `placement_offers`, `interview_experiences`, `internship_experiences` |
| Audit | `master_audit_log` |
| Views | `v_student_achievements` (one row per student per achievement); `v_diary_offers`, `v_diary_interviews`, `v_diary_internships` (**no identifiers at all** - the Student Diary reads only these) |

Key behaviours
- `students.roll_no` and `faculty.emp_id` are the primary keys everywhere.
- Each participant row stores the **class, year and semester at the time** (looked up from `student_class_history`), so later promotions never rewrite history.
- A roll number that matches nobody is kept (`roll_no` NULL + original text) and listed under *Needs attention*, never dropped.
- Re-importing the same row is a no-op (`source_row_hash`), so the same Excel can be uploaded twice safely.
- A tutor still sees the placements of students they taught after those students graduate (their last class is used).

## Access matrix (enforced in the API)

| Role | Students | Submissions | Analytics | Can change |
|---|---|---|---|---|
| Admin | all | all | everything | faculty, roles, class tutors, anything |
| HoD | all | all | everything | view only |
| Programme Coordinator | every class of their programme: UG coordinators see **both groups** (filter Both / G1 / G2), the PG coordinator sees PG | those classes' students' | those classes | view only |
| Tutor | own class | own class's students' | own class | students of own class, class semester/AY, graduating a finished class (not form or placement uploads) |
| Faculty | - | only what they submitted / are named in | - | - |
| Student | - | - | - | only the anonymous **Placements Diary** |

## Filters (available in the portal and API)

- **Common:** academic year, date range, form, category, submitter, title search, landmark only, has photo
- **Student achievements:** roll no, class, level, domain, individual/team, mentor, prize amount, tools
- **Students:** class, programme, group, year, status, name/roll search. Only roll number, name, programme, class and status are stored: academic data (CGPA, gender, residence, contact details) stays in the college main database.
- **Research:** subcategory, status, indexing, quartile, impact factor, conference level, funding, venue, any faculty/student/external author
- **Faculty:** faculty, category, recognition type, level, hours, host, city
- **Department:** category, convener, status, participants, budget, accreditation link
- **Outreach:** category, format, partner, partner type, attendance, MoU active / expiring / expired
- **Placements:** year, class/programme/group, opted in/out (+reason), company, offer type, package and stipend range, offer status, on/off-campus, has interview / internship experience

## Student Placements Diary - what is exposed

For each company, over the **three most recent academic years that have offers**: students placed (full-time) and interns, lowest / average / highest package, year-by-year table, roles offered, offer types, and the interview and internship experiences students agreed to share (`Consent` column = Yes). **Never**: name, roll number, class, photo, e-mail. The API cannot leak them because the Diary only queries the three identifier-free views, and `tests/test_master.py` asserts no student name or roll number appears in any Diary response.

Caveat: where only one student was placed at a company, the package shown is necessarily that student's. Free-text experiences are shown as written; remind students not to sign them.

## Logins

- **Staff:** employee ID + a temporary password generated when the Admin adds or uploads faculty (shown once, change forced at first sign-in). The first `ADMIN` password is written to `database/INITIAL_ADMIN_PASSWORD.txt` (or set `MASTER_ADMIN_PASSWORD`).
- **Students:** roll number; the first password is the roll number and must be changed. Roll numbers are not secret, so this protects only anonymised data - which is why the Diary exposes nothing personal.
- Sessions are signed tokens valid 8 hours; 5 wrong passwords lock that ID for 5 minutes. Set `MASTER_SECRET` in production.

## Running it

```bash
pip install -r requirements.txt
python run_server.py                     # http://127.0.0.1:8000
```
- Newsletter studio: `/`  ·  Staff portal: `/portal/`  ·  Student Placements Diary: `/diary/`
- Demo data: `python seed_master_demo.py <admin-password>` (never on real data)
- Tests: `python -m pytest tests/test_master.py`

Not yet protected: the newsletter studio (`/`) and its `/api/*` endpoints keep their previous open behaviour; put it behind the same login or a network boundary before exposing the server beyond the department.
