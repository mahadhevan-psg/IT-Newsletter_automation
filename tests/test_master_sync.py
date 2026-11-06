"""Slim students table, roll-number-only rosters, and the newsletter reading its entries from the master database."""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.master import ingest  # noqa: E402
from backend.master.common import names_only  # noqa: E402
from backend.services import master_sync  # noqa: E402
from database.master_db import db, drop_student_columns, init_master_db  # noqa: E402


@pytest.fixture()
def master(monkeypatch, tmp_path):
    """A fresh master database per test, with two students in class 1."""
    monkeypatch.setenv("MASTER_DB_PATH", str(tmp_path / "master.db"))
    monkeypatch.setenv("MASTER_ADMIN_PASSWORD", "AdminPass1!")
    monkeypatch.setenv("MASTER_SECRET", "test-secret")
    init_master_db()
    with db() as conn:
        for roll, name in (("21IT001", "Asha Kumar"), ("21IT002", "Ravi Shankar")):
            conn.execute("INSERT INTO students (roll_no, full_name, programme, class_id) VALUES (?, ?, 'UG', 1)", (roll, name))
    return tmp_path


def student_row(participants, title, permission="Yes - may be published"):
    return {"Timestamp": "2026-10-01 10:00:00", "Email Address": "t1@x.edu", "Participants (one roll number per line)": participants,
            "Lead Student Roll Number": "21IT001", "Individual or Team Achievement": "Team",
            "Student Achievement Category": "Hackathons & Coding Competitions", "Name of Competition / Award / Project / Event": title,
            "Organizing Institute / Company / Awarding Body": "AICTE", "Achievement Level": "National", "Position / Rank / Prize / Scholarship": "1st Prize",
            "Date of Achievement / Result": "2026-09-20", "Project Abstract / Achievement Details": "Built a triage bot for hospitals.",
            "Permission to Publish this Submission": permission}


def test_students_table_keeps_only_what_links_a_person_to_records(master):
    with db() as conn:
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(students)")]
    assert cols == ["roll_no", "full_name", "programme", "class_id", "status", "created_at"]


def test_a_database_with_the_old_student_columns_is_migrated(master):
    with db() as conn:
        for col, typ in (("gender", "TEXT"), ("cgpa", "REAL"), ("residence_type", "TEXT"), ("email", "TEXT"), ("batch_start_year", "INTEGER")):
            conn.execute(f"ALTER TABLE students ADD COLUMN {col} {typ}")
        drop_student_columns(conn)
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(students)")}
        assert not cols & {"gender", "cgpa", "residence_type", "email", "batch_start_year"}
        assert conn.execute("SELECT COUNT(*) FROM students").fetchone()[0] == 2          # nobody lost


def test_roster_of_roll_numbers_only_gets_names_from_the_college_records(master):
    assert names_only("21IT001\n21IT002") == "Asha Kumar, Ravi Shankar"
    assert names_only("21IT001 - Typed Name") == "Typed Name"                              # the older "ROLLNO - Name" lines still work
    assert names_only("Dr. John Smith, Dr. Alice Johnson") == "Dr. John Smith, Dr. Alice Johnson"
    res = ingest.ingest_form_row("form_student", student_row("21IT001\n21IT002", "Hackathon"))
    assert res["status"] == "inserted", res
    with db() as conn:
        rows = conn.execute("SELECT roll_no, name FROM student_achievement_participants ORDER BY line_no").fetchall()
    assert [(r["roll_no"], r["name"]) for r in rows] == [("21IT001", "Asha Kumar"), ("21IT002", "Ravi Shankar")]


def test_newsletter_takes_entries_from_the_master_database_once(master, monkeypatch):
    created = []
    monkeypatch.setattr(master_sync, "create_canonical_entry", lambda e: created.append(e) or f"ENTRY_{len(created)}")
    monkeypatch.setattr(master_sync, "save_raw_response", lambda *a, **k: "RESP_1")
    ingest.ingest_form_row("form_student", student_row("21IT001\n21IT002", "Smart India Hackathon"))
    ingest.ingest_form_row("form_student", student_row("21IT001", "Private Project", permission="No - do not publish"))

    first = master_sync.MasterSync().sync("ISSUE_X")
    assert first["created"] == 1 and first["skipped_no_permission"] == 1 and not first["failed"], first
    entry = created[0]
    assert entry["title"] == "Smart India Hackathon"
    assert entry["author_or_person"] == "Asha Kumar, Ravi Shankar"                       # names looked up, not typed in the form
    assert entry["section_id"] == "sec_student" and entry["issue_id"] == "ISSUE_X"
    with db() as conn:
        linked = conn.execute("SELECT newsletter_entry_id FROM form_submissions WHERE title = 'Smart India Hackathon'").fetchone()[0]
    assert linked == "ENTRY_1"

    again = master_sync.MasterSync().sync("ISSUE_X")                                     # nothing new: no duplicate entries
    assert again["created"] == 0 and len(created) == 1


def test_unanswered_permission_is_not_a_no(master, monkeypatch):
    row = student_row("21IT001", "No Question Asked")
    del row["Permission to Publish this Submission"]
    ingest.ingest_form_row("form_student", row)
    with db() as conn:
        assert conn.execute("SELECT publish_permission FROM form_submissions").fetchone()[0] is None
    created = []
    monkeypatch.setattr(master_sync, "create_canonical_entry", lambda e: created.append(e) or "E1")
    monkeypatch.setattr(master_sync, "save_raw_response", lambda *a, **k: "R1")
    assert master_sync.MasterSync().sync()["created"] == 1                              # only an explicit No keeps a submission out


def test_participation_is_recorded_on_the_student_form_not_the_departmental_one(master):
    import json
    spec = json.load(open(os.path.join(os.path.dirname(__file__), "..", "config", "master_forms.json"), encoding="utf-8"))["forms"]
    assert not any(q.get("key") == "_event_participants" for q in spec["form_departmental"]["questions"])
    assert any(q.get("key") == "entry_kind" for q in spec["form_student"]["questions"])

    row = student_row("21IT001\n21IT002", "Inter-college Quiz")
    row["Achievement or Participation"] = "Participation only"
    ingest.ingest_form_row("form_student", row)
    ingest.ingest_form_row("form_student", student_row("21IT001", "Hackathon"))                 # question left blank: an achievement
    with db() as conn:
        kinds = {r["title"]: r["entry_kind"] for r in conn.execute(
            "SELECT s.title, a.entry_kind FROM form_submissions s JOIN student_achievements a ON a.submission_id = s.submission_id")}
        roster = conn.execute("SELECT COUNT(*) FROM student_achievement_participants p JOIN form_submissions s ON s.submission_id = p.submission_id "
                              "WHERE s.title = 'Inter-college Quiz'").fetchone()[0]
    assert kinds == {"Inter-college Quiz": "PARTICIPATION", "Hackathon": "ACHIEVEMENT"}
    assert roster == 2                                                                           # both students linked to the participation


def test_an_older_database_gets_the_entry_kind_column(master):
    with db() as conn:
        conn.execute("ALTER TABLE student_achievements DROP COLUMN entry_kind")
        from database.master_db import add_entry_kind
        add_entry_kind(conn)
        assert "entry_kind" in {r["name"] for r in conn.execute("PRAGMA table_info(student_achievements)")}


def test_class_years_that_drifted_from_their_semester_are_repaired(master):
    from database.master_db import repair_class_years
    with db() as conn:
        conn.execute("UPDATE classes SET current_semester = 3 WHERE class_code = 'UG-G2-1'")      # semester 3 is year 2, but the class says year 1
        repair_class_years(conn)
        rows = {r["class_id"]: (r["year_no"], r["class_code"]) for r in conn.execute("SELECT class_id, year_no, class_code FROM classes")}
        moved = conn.execute("SELECT year_no, class_code FROM classes WHERE current_semester = 3 AND grp = 'G2' ORDER BY class_id").fetchall()
    assert len(moved) == 2 and all(r["year_no"] == 2 for r in moved)                              # two classes in year 2 at once
    assert len({code for _, code in rows.values()}) == len(rows)                                  # codes stay unique
