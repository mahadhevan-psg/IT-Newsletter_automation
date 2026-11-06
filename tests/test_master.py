"""End-to-end test of the master database, portal API and student diary on a throw-away database."""
import io
import json
import os
import sys
import tempfile

import openpyxl
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

_tmp = tempfile.mkdtemp()
os.environ["MASTER_DB_PATH"] = os.path.join(_tmp, "master.db")
os.environ["MASTER_ADMIN_PASSWORD"] = "AdminPass1!"
os.environ["MASTER_SECRET"] = "test-secret"

from fastapi.testclient import TestClient  # noqa: E402

from backend.app import app  # noqa: E402
from backend.master import ingest  # noqa: E402
from database.master_db import init_master_db  # noqa: E402

client = TestClient(app)


def xlsx(headers, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def upload(url, headers, rows, token, **form):
    files = {"file": ("data.xlsx", xlsx(headers, rows), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    return client.post(url, files=files, data=form, headers=auth(token))


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def signin(uid, pw):
    r = client.post("/api/auth/login", json={"id": uid, "password": pw})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def world():
    init_master_db()
    admin = signin("ADMIN", "AdminPass1!")
    r = upload("/api/master/faculty/upload", ["Employee ID", "Full Name", "Email", "Designation"],
               [["EMP001", "Dr. Tutor One", "t1@x.edu", "Professor"], ["EMP002", "Dr. Coordinator", "pc@x.edu", "Professor"],
                ["EMP003", "Dr. Plain Faculty", "f3@x.edu", "Asst Prof"], ["EMP004", "Dr. Tutor Two", "t2@x.edu", "Asst Prof"]], admin)
    assert r.json()["added"] == 4, r.text
    creds = {c["emp_id"]: c["temp_password"] for c in r.json()["credentials"]}
    classes = {c["class_code"]: c["class_id"] for c in client.get("/api/master/classes", headers=auth(admin)).json()}
    assert len(classes) == 10
    for code, emp in (("UG-G1-3", "EMP001"), ("UG-G2-3", "EMP004")):
        assert client.put(f"/api/master/classes/{classes[code]}/tutor", json={"emp_id": emp}, headers=auth(admin)).status_code == 200
    assert client.put("/api/master/faculty/EMP002/roles", json={"roles": [{"role": "PC", "programme": "UG", "grp": "G1"}]}, headers=auth(admin)).status_code == 200
    t1 = signin("EMP001", creds["EMP001"])
    t2 = signin("EMP004", creds["EMP004"])
    r = upload("/api/master/students/upload", ["Roll No", "Full Name"],
               [["21IT001", "Asha Kumar"], ["21IT002", "Ravi Shankar"], ["21IT003", "Meena Devi"]], t1, class_id=classes["UG-G1-3"])
    assert r.json()["added"] == 3, r.text
    r = upload("/api/master/students/upload", ["Roll No", "Full Name"], [["21IT101", "Other Class Student"]], t2, class_id=classes["UG-G2-3"])
    assert r.json()["added"] == 1, r.text
    return {"admin": admin, "t1": t1, "t2": t2, "classes": classes, "creds": creds}


def test_tutor_cannot_touch_other_class(world):
    r = upload("/api/master/students/upload", ["Roll No", "Full Name"], [["21IT101", "Hijack"]], world["t1"], class_id=world["classes"]["UG-G1-3"])
    assert r.json()["added"] == 0 and r.json()["errors"], r.text
    rows = client.get("/api/master/students", headers=auth(world["t1"])).json()
    assert rows["total"] == 3
    assert client.put(f"/api/master/classes/{world['classes']['UG-G2-3']}/term", json={"semester": 6}, headers=auth(world["t1"])).status_code == 403
    assert client.put(f"/api/master/classes/{world['classes']['UG-G1-3']}/term", json={"semester": 6}, headers=auth(world["t1"])).status_code == 200
    assert client.put("/api/master/faculty/EMP003/roles", json={"roles": []}, headers=auth(world["t1"])).status_code == 403


STUDENT_FORM = ["Timestamp", "Email Address", "Participants (one per line: ROLLNO - Student Name)", "Lead Student Roll Number",
                "Individual or Team Achievement", "Student Achievement Category", "Name of Competition / Award / Project / Event",
                "Organizing Institute / Company / Awarding Body", "Achievement Level", "Position / Rank / Prize / Scholarship",
                "Prize / Scholarship Amount in Rupees (numbers only, 0 if none)", "Date of Achievement / Result", "Achievement Domain",
                "Faculty Mentor / Project Guide", "Project Abstract / Achievement Details", "Is this a Landmark / Milestone Achievement?",
                "Permission to Publish this Submission"]


def test_student_form_upload_links_people_and_dedupes(world):
    row = ["2026-10-01 10:00:00", "t1@x.edu", "21IT001 - Asha Kumar\n21IT002 - Ravi Shankar - Backend lead\n99XX999 - Ghost Student", "21IT001", "Team",
           "Hackathons & Coding Competitions", "Smart India Hackathon", "AICTE", "National", "1st Prize", "₹50,000", "2026-09-20",
           "AI / Machine Learning", "EMP003 - Dr. Plain Faculty", "Built a triage bot", "Yes (Nominate for Spotlight Feature)", "Yes - may be published"]
    r = upload("/api/master/forms/form_student/upload", STUDENT_FORM, [row], world["admin"])
    res = r.json()
    assert res["inserted"] == 1, res
    assert any("Ghost" in m for p in res["needs_attention"] for m in p["messages"])          # unknown roll flagged, not dropped
    again = upload("/api/master/forms/form_student/upload", STUDENT_FORM, [row], world["admin"]).json()
    assert again["inserted"] == 0 and again["duplicates_skipped"] == 1
    sub = client.get("/api/master/submissions", headers=auth(world["t1"])).json()
    assert sub["total"] == 1
    d = client.get(f"/api/master/submissions/{sub['rows'][0]['submission_id']}", headers=auth(world["t1"])).json()
    assert d["detail"]["prize_amount"] == 50000 and d["detail"]["mentor_emp_id"] == "EMP003" and d["header"]["is_landmark"] == 1
    by_roll = {p["roll_no"]: p for p in d["participants"]}
    assert by_roll["21IT001"]["is_lead"] == 1 and by_roll["21IT002"]["role"] == "Backend lead" and by_roll["21IT001"]["class_code"] == "UG-G1-3"
    # the other tutor (different class) must not see it; the faculty mentor does not either (not the submitter)
    assert client.get("/api/master/submissions", headers=auth(world["t2"])).json()["total"] == 0
    # filter by student
    assert client.get("/api/master/submissions?roll_no=21IT002", headers=auth(world["admin"])).json()["total"] == 1
    assert client.get("/api/master/submissions/unmatched", headers=auth(world["t1"])).json()


def test_research_and_other_forms(world):
    headers = ["Timestamp", "Email Address", "Submitting Faculty (select your name)", "Research Subcategory",
               "Title of Publication / Patent / Project / Innovation", "Current Status",
               "Authors / Investigators (one per line: ID - Name)", "Venue / Journal / Publisher / Funding Agency / Organization",
               "Date of Publication / Filing / Award / Grant", "Indexing", "Quartile", "Impact Factor (number, leave blank if none)",
               "Funding Amount in Rupees (numbers only)", "Abstract / Executive Summary"]
    row = ["2026-10-02 09:00:00", "f3@x.edu", "EMP003 - Dr. Plain Faculty", "Journal Publications", "Quantum Newsletters", "Published",
           "EMP003 - Dr. Plain Faculty\n21IT001 - Asha Kumar\nEXT - Dr. J. Smith - Anna University", "IEEE Access", "2026-08-15", "Scopus", "Q1", "4.2",
           "12 lakhs", "A paper."]
    res = upload("/api/master/forms/form_research/upload", headers, [row], world["admin"]).json()
    assert res["inserted"] == 1 and not res["needs_attention"], res
    sid = client.get("/api/master/submissions?form_type=RESEARCH", headers=auth(world["admin"])).json()["rows"][0]["submission_id"]
    d = client.get(f"/api/master/submissions/{sid}", headers=auth(world["admin"])).json()
    assert [c["person_type"] for c in d["contributors"]] == ["FACULTY", "STUDENT", "EXTERNAL"]
    assert d["detail"]["funding_amount"] == 1200000 and d["detail"]["quartile"] == "Q1"
    # a plain faculty member sees only what they submitted
    fac = signin("EMP003", world["creds"]["EMP003"])
    assert client.get("/api/master/submissions", headers=auth(fac)).json()["total"] == 1
    assert client.get("/api/master/students", headers=auth(fac)).json()["total"] == 0
    assert client.get("/api/master/analytics", headers=auth(fac)).json().get("department") is None


PLACE = ["Roll Number", "Full Name", "Placement Academic Year", "Placement Preference", "Reason for Opting Out (only if Opted Out)", "Company Name",
         "Company Sector", "Offer Type", "Package in LPA (numbers only, for FTE offers)", "Internship Stipend in Rupees per Month (numbers only)",
         "Job Role", "Offer Status", "Interview Difficulty", "Your Interview Experience", "Tips for Juniors", "Your Internship Experience",
         "Consent to Share Experience Anonymously"]


def test_placement_upload_replaces_and_diary_hides_pii(world):
    rows = [["21IT001", "Asha Kumar", "2025-26", "Opted In", "", "Acme Technologies", "Product", "FTE", "8.5", "", "SDE", "Accepted", "Medium",
             "Three rounds, friendly panel", "Practise SQL", "", "Yes - share anonymously with juniors"],
            ["21IT001", "Asha Kumar", "2025-26", "Opted In", "", "Acme Technologies", "Product", "Intern", "", "25000", "Intern", "Accepted", "", "", "",
             "Great mentors, learned Docker", "Yes - share anonymously with juniors"],
            ["21IT002", "Ravi Shankar", "2025-26", "Opted Out", "Higher studies", "", "", "", "", "", "", "", "", "", "", "", ""],
            ["21IT003", "Meena Devi", "2025-26", "Opted In", "", "Beta Soft", "IT Services", "FTE+Intern", "4.5", "15000", "Analyst", "Accepted", "Easy",
             "Secret experience", "", "", "No - keep private"]]
    r = upload("/api/master/placements/upload", PLACE, rows, world["admin"]).json()
    assert r["students"] == 3 and r["offers"] == 3 and not r["errors"], r
    # replace: same student, new package -> old rows gone, not merged
    rows2 = [["21IT001", "Asha Kumar", "2025-26", "Opted In", "", "Acme Technologies", "Product", "FTE", "9.5", "", "SDE", "Accepted", "", "", "", "", ""]]
    r = upload("/api/master/placements/upload", PLACE, rows2, world["admin"]).json()
    assert r["replaced_students"] == 1, r
    offers = client.get("/api/master/placements/offers?q=21IT001", headers=auth(world["t1"])).json()
    assert offers["total"] == 1 and offers["rows"][0]["package_lpa"] == 9.5
    # form responses and placement sheets are the Admin's job: a tutor is refused outright
    assert upload("/api/master/placements/upload", PLACE, rows, world["t1"]).status_code == 403
    assert upload("/api/master/forms/form_student/upload", STUDENT_FORM, [], world["t1"]).status_code == 403
    assert client.get("/api/master/placements/template", headers=auth(world["t1"])).status_code == 403
    assert client.get("/api/master/forms/form_student/template", headers=auth(world["t1"])).status_code == 403
    # restore the richer rows for the diary checks
    upload("/api/master/placements/upload", PLACE, rows, world["admin"])

    token = signin("21IT002", "21IT002")           # a student's first password is their roll number
    assert client.get("/api/master/students", headers=auth(token)).status_code == 403     # students never reach staff data
    comps = client.get("/api/diary/companies", headers=auth(token)).json()
    names = {c["name"]: c for c in comps["companies"]}
    assert names["Acme Technologies"]["placed"] == 1 and names["Acme Technologies"]["max_lpa"] == 8.5
    detail = client.get(f"/api/diary/companies/{names['Acme Technologies']['org_id']}", headers=auth(token)).json()
    blob = json.dumps([comps, detail, client.get("/api/diary/overview", headers=auth(token)).json()]).lower()
    for secret in ("21it001", "21it002", "21it003", "asha", "ravi", "meena", "kumar"):
        assert secret not in blob, f"PII leaked: {secret}"
    assert detail["interviews"] and detail["internships"]
    # experiences without consent stay private
    beta = client.get(f"/api/diary/companies/{names['Beta Soft']['org_id']}", headers=auth(token)).json()
    assert beta["interviews"] == [] and "secret experience" not in json.dumps(beta).lower()


def test_scope_and_analytics(world):
    pc = signin("EMP002", world["creds"]["EMP002"])
    cls = client.get("/api/master/classes", headers=auth(pc)).json()
    # a coordinator sees the whole programme - UG classes of BOTH groups, no PG - whatever group the role is labelled with
    assert {c["programme"] for c in cls} == {"UG"} and {c["grp"] for c in cls} == {"G1", "G2"}
    assert client.get("/api/master/students", headers=auth(pc)).json()["total"] == 4
    both = lambda q: client.get("/api/master/students" + q, headers=auth(pc)).json()
    assert both("?grp=G1")["total"] == 3 and both("?grp=G2")["total"] == 1                 # the Both / G1 / G2 filter
    assert {r["roll_no"] for r in both("?grp=G2")["rows"]} == {"21IT101"}
    assert client.post("/api/master/students", json={"roll_no": "X1", "full_name": "N", "class_id": world["classes"]["UG-G1-3"]}, headers=auth(pc)).status_code == 403
    a = client.get("/api/master/analytics", headers=auth(world["t1"])).json()
    assert a["students"]["students_with_achievements"] == 2 and a["placements"]["placed"] == 2 and "department" not in a
    assert client.get(f"/api/master/analytics?class_id={world['classes']['UG-G2-3']}", headers=auth(world["t1"])).status_code == 403
    full = client.get("/api/master/analytics", headers=auth(world["admin"])).json()
    assert full["department"]["submissions_by_form"]


def test_semester_sets_the_year_and_class_code_and_nobody_is_promoted(world):
    cid, t1 = world["classes"]["UG-G1-3"], world["t1"]                           # a semester-5/6 class = year 3
    cls = {c["class_id"]: c for c in client.get("/api/master/classes", headers=auth(world["admin"])).json()}
    sem = cls[cid]["current_semester"]
    assert cls[cid]["year_no"] == (sem + 1) // 2 == 3 and cls[cid]["label"] == f"Dr. Tutor One · Sem {sem}"
    assert client.post(f"/api/master/classes/{cid}/promote", headers=auth(t1)).status_code in (404, 405)   # no promote any more

    # semester 6 is still year 3: same class code
    assert client.put(f"/api/master/classes/{cid}/term", json={"semester": 6}, headers=auth(t1)).json()["class_code"] == "UG-G1-3"
    # semester 7 is year 4, but UG-G1-4 is taken by another class right now: both are in year 4 at once, the code tells them apart
    r = client.put(f"/api/master/classes/{cid}/term", json={"semester": 7}, headers=auth(t1)).json()
    assert r == {"class_code": "UG-G1-4-S7", "year_no": 4, "current_semester": 7}, r
    now = {c["class_id"]: c for c in client.get("/api/master/classes", headers=auth(world["admin"])).json()}
    assert now[cid]["year_no"] == now[world["classes"]["UG-G1-4"]]["year_no"] == 4
    assert client.get("/api/master/students", headers=auth(t1)).json()["total"] == 3         # the students stayed in their class
    # limits: UG has 8 semesters, PG 4
    assert client.put(f"/api/master/classes/{cid}/term", json={"semester": 9}, headers=auth(t1)).status_code == 400
    pg = world["classes"]["PG-1"]
    assert client.put(f"/api/master/classes/{pg}/term", json={"semester": 5}, headers=auth(world["admin"])).status_code == 400
    assert client.put(f"/api/master/classes/{pg}/term", json={"semester": 4}, headers=auth(world["admin"])).json()["class_code"] == "PG-2-S4"      # PG-2 is taken (semester 3)
    # back to semester 8 -> year 4 still; the final semester allows graduating, earlier ones do not
    assert client.post(f"/api/master/classes/{pg}/graduate", headers=auth(world["admin"])).status_code == 200
    assert client.post(f"/api/master/classes/{cid}/graduate", headers=auth(t1)).status_code == 400    # semester 7 of 8


def test_admin_adds_classes_and_graduates_keep_their_history(world):
    admin, t1, cid = world["admin"], world["t1"], world["classes"]["UG-G1-3"]
    assert client.post("/api/master/classes", json={"programme": "UG", "grp": "G1", "semester": 3}, headers=auth(t1)).status_code == 403
    new = client.post("/api/master/classes", json={"programme": "UG", "grp": "G1", "semester": 4, "tutor_id": "EMP003"}, headers=auth(admin)).json()
    assert new["class_code"] == "UG-G1-2-S4"                                       # year 2 already exists (semester 3): a second year-2 class
    assert client.post("/api/master/classes", json={"programme": "UG", "semester": 1}, headers=auth(admin)).status_code == 400   # UG needs a group
    # the tutor's class reaches the last semester and graduates: students become Graduated, the class closes
    assert client.put(f"/api/master/classes/{cid}/term", json={"semester": 8}, headers=auth(t1)).json()["class_code"] == "UG-G1-4-S8"
    assert client.post(f"/api/master/classes/{cid}/graduate", headers=auth(t1)).json()["graduated"] == 3
    assert client.get("/api/master/students", headers=auth(t1)).json()["total"] == 0           # no longer an active class
    assert cid not in [c["class_id"] for c in client.get("/api/master/classes", headers=auth(t1)).json()]
    assert cid in [c["class_id"] for c in client.get("/api/master/classes?include_completed=true", headers=auth(admin)).json()]
    # past achievements still show the class the student was in at the time
    assert client.get("/api/master/submissions?class_id=%d" % cid, headers=auth(admin)).json()["total"] == 1


def test_newsletter_importer_feeds_master_db(world, tmp_path):
    from database import db_manager
    db_manager.DB_PATH = str(tmp_path / "news.db")
    db_manager.init_db()
    from backend.services.ingestion_service import IngestionService
    res = IngestionService().process_single_submission(
        "form_faculty", {"Timestamp": "2026-10-05 10:00:00", "Email Address": "f3@x.edu", "Faculty Full Name (select your name)": "EMP003 - Dr. Plain Faculty",
                         "Achievement Category": "Awards & Honors Received", "Exact Title of Award / Certification / Lecture / Role": "Best Teacher",
                         "Awarding Body / Host Institution / Organizing Organization": "Rotary", "Level": "State",
                         "Date of Achievement / Start Date": "2026-10-01", "Description & Key Highlights": "Won."})
    assert res["master"]["status"] == "inserted", res["master"]
    assert res["canonical_entry"]["author_or_person"] == "Dr. Plain Faculty"            # newsletter gets the name, not 'EMP003 - ...'
    assert res["canonical_entry"]["category_id"] == "cat_fac_awards"
    again = IngestionService().process_single_submission(
        "form_faculty", {"Timestamp": "2026-10-05 10:00:00", "Email Address": "f3@x.edu", "Faculty Full Name (select your name)": "EMP003 - Dr. Plain Faculty",
                         "Achievement Category": "Awards & Honors Received", "Exact Title of Award / Certification / Lecture / Role": "Best Teacher",
                         "Awarding Body / Host Institution / Organizing Organization": "Rotary", "Level": "State",
                         "Date of Achievement / Start Date": "2026-10-01", "Description & Key Highlights": "Won."})
    assert again.get("duplicate")


def test_every_form_header_is_unique_and_mapped():
    for fid in ingest.form_ids():
        heads = ingest.template_headers(fid)
        assert len(heads) == len(set(heads)), f"duplicate question in {fid}"


def test_downloaded_templates_round_trip_and_match_the_importers(world):
    from backend.master import placements
    # students: header-only "Data" sheet (instructions on a second sheet are never imported), fill a row, upload it
    r = client.get("/api/master/students/template", headers=auth(world["t2"]))
    assert r.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ["Data", "How to fill"]
    assert [c.value for c in wb["Data"][1]] == ["Roll No", "Full Name"]
    wb["Data"].append(["21IT777", "Template Student"])
    buf = io.BytesIO()
    wb.save(buf)
    files = {"file": ("s.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    assert client.post("/api/master/students/upload", files=files, headers=auth(world["t2"])).json()["added"] == 1      # the tutor's own class, no class chosen
    # faculty template (Admin only) has the importer's columns
    r = client.get("/api/master/faculty-template", headers=auth(world["admin"]))
    assert [c.value for c in openpyxl.load_workbook(io.BytesIO(r.content))["Data"][1]] == ["Employee ID", "Full Name", "Email", "Phone", "Designation", "Qualification", "Date of Joining"]
    assert client.get("/api/master/faculty-template", headers=auth(world["t1"])).status_code == 403
    # the placement template's example row has one value per column
    assert len(placements.EXAMPLE) == len(placements.template_headers())


def test_newsletter_api_needs_a_signed_in_admin_or_hod(world):
    assert client.get("/api/entries").status_code == 401                                      # nobody signed in
    assert client.post("/api/entries/sync-master", json={}).status_code == 401
    assert client.put("/api/front-matter", json={}).status_code == 401
    assert client.get("/api/entries", headers=auth(world["t1"])).status_code == 403            # a tutor: not the studio's audience
    assert client.get("/api/audit-logs", headers=auth(world["t1"])).status_code == 403
    assert client.get("/api/entries", headers=auth(world["admin"])).status_code == 200
    assert client.get("/api/uploads/does-not-exist.jpg").status_code == 404                    # photos stay readable for <img> tags (no 401)
    assert client.get("/api/diary/overview").status_code == 401                                # the other applications keep their own rules
    # the cross-class list of roll numbers that matched nobody is the Admin's
    assert client.get("/api/master/submissions/unmatched", headers=auth(world["t1"])).status_code == 403
    assert client.get("/api/master/submissions/unmatched", headers=auth(world["admin"])).status_code == 200
