"""Faculty and student profile pages: every activity lands in the right section/group, with the right role, and access is scoped."""
import os
import sys

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.master import ingest, profiles  # noqa: E402
from backend.master.auth import User  # noqa: E402
from database.master_db import db, ensure_ay, init_master_db  # noqa: E402

ADMIN = User("ADMIN", "Admin", "STAFF", {"ADMIN", "FACULTY"}, all_access=True)


def form_row(form_id, **by_key):
    """A response row for a form, written with master-DB field names and turned into the form's real column headers."""
    heads = {q["key"]: q["q"] for q in ingest.specs()["forms"][form_id]["questions"] if q.get("key")}
    row = {"Timestamp": "2025-10-01 10:00:00", "Email Address": "x@x.edu"}
    row.update({heads[k]: v for k, v in by_key.items()})
    return row


@pytest.fixture()
def world(monkeypatch, tmp_path):
    monkeypatch.setenv("MASTER_DB_PATH", str(tmp_path / "master.db"))
    monkeypatch.setenv("MASTER_ADMIN_PASSWORD", "AdminPass1!")
    monkeypatch.setenv("MASTER_SECRET", "test-secret")
    init_master_db()
    with db() as c:
        for emp, name, desig in (("EMP001", "Dr. Asha Rao", "Professor"), ("EMP002", "Dr. Bala K", "Asst Professor")):
            c.execute("INSERT INTO faculty (emp_id, full_name, email, designation) VALUES (?,?,?,?)", (emp, name, emp.lower() + "@x.edu", desig))
        c.execute("UPDATE classes SET tutor_id = 'EMP001' WHERE class_id = 1")
        for roll, name, cid in (("21IT001", "Kavin M", 1), ("21IT002", "Divya S", 1), ("21IT009", "Other Class", 2)):
            c.execute("INSERT INTO students (roll_no, full_name, programme, class_id) VALUES (?, ?, 'UG', ?)", (roll, name, cid))
            c.execute("INSERT INTO student_class_history (roll_no, class_id, from_date, action) VALUES (?, ?, '2025-06-01', 'Added')", (roll, cid))
    rows = [
        ("form_research", dict(_submitter="EMP001", category="Journal Publications", title="Paper One", current_status="Published", _contributors="EMP001\n21IT001\nEXT - Dr. X - IIT",
                               venue_publisher="IEEE Access", output_date="2025-08-15", indexing="Scopus", quartile="Q1", impact_factor="4.2", abstract="About paper one.")),
        ("form_research", dict(_submitter="EMP002", category="Patents & Intellectual Property", title="Patent One", current_status="Filed", _contributors="EMP002\nEMP001",
                               venue_publisher="Indian Patent Office", output_date="2024-09-01", abstract="A patent.")),
        ("form_research", dict(_submitter="EMP001", category="Funded Research Projects", title="DST Project", current_status="Ongoing", _contributors="EMP001",
                               venue_publisher="DST", output_date="2025-07-01", funding_status="Funded", funding_amount="12 lakhs", abstract="Funded.")),
        ("form_faculty", dict(emp_id="EMP001", category="Awards & Honors Received", title="Best Teacher", host_org="Rotary", level="State", start_date="2025-09-05", description="Award.")),
        ("form_faculty", dict(emp_id="EMP001", category="Invited Keynote / Expert Lectures Delivered", title="Keynote on AI", host_org="XYZ College", level="National",
                              start_date="2025-11-02", duration_hours="2", description="Talk.")),
        ("form_departmental", dict(_submitter="EMP001", convener_emp_id="EMP001", category="Workshops & FDPs Organized", title="AI Workshop", start_date="2025-12-01",
                                   participant_count="80", overview="Workshop.")),
        ("form_departmental", dict(_submitter="EMP002", convener_emp_id="EMP002", category="Conferences & Symposia Organized", title="Symposium", start_date="2025-12-10",
                                   _faculty_involved="EMP001", overview="Symposium.")),
        ("form_industry", dict(_submitter="EMP001", lead_emp_id="EMP002", category="MoUs Signed & Industrial Collaborations", title="MoU with Acme", _partner="Acme",
                               start_date="2025-10-10", summary_outcomes="MoU.", _event_participants="21IT001")),
        ("form_student", dict(_participants="21IT001\n21IT002", _lead_roll="21IT001", is_team="Team", entry_kind="Achievement (won, ranked or awarded)",
                              category="Hackathons & Coding Competitions", title="SIH 2025", organizer="AICTE", level="National", position="Winner", prize_amount="50000",
                              result_date="2025-09-20", domain="Other", mentor_emp_id="EMP001", abstract="Built a bot.")),
        ("form_student", dict(_participants="21IT001", _lead_roll="21IT001", is_team="Individual", entry_kind="Participation only",
                              category="Sports, Cultural & Co-Curricular Accomplishments", title="Inter-college Chess", organizer="PSG", level="Inter-college", position="Participant",
                              result_date="2025-10-05", domain="Sports", mentor_emp_id="EMP002", abstract="Played.")),
    ]
    with db() as c:
        for fid, keys in rows:
            res = ingest.ingest_row(c, fid, form_row(fid, **keys))
            assert res["status"] == "inserted", (keys["title"], res)
        ensure_ay(c, "2025-26")
        c.execute("INSERT INTO organizations (name, name_key, sector) VALUES ('Acme Technologies','acmetechnologies','Product')")
        c.execute("INSERT INTO placement_profiles (roll_no, ay_id, opt_status) VALUES ('21IT001','2025-26','OPTED_IN')")
        c.execute("INSERT INTO placement_offers (roll_no, ay_id, org_id, offer_type, package_lpa, job_role) VALUES ('21IT001','2025-26',1,'FTE',8.5,'SDE')")
        c.execute("INSERT INTO interview_experiences (roll_no, ay_id, org_id, difficulty, result, experience) VALUES ('21IT001','2025-26',1,'Medium','Selected','Friendly panel')")
        c.execute("INSERT INTO internship_experiences (roll_no, ay_id, org_id, role, rating, experience) VALUES ('21IT001','2025-26',1,'Backend intern',5,'Great mentors')")


def sections(p):
    return {s["id"]: s for s in p["sections"]}


def groups(s):
    return {g["title"]: [i["title"] for i in g["items"]] for g in s["groups"]}


def test_faculty_page_is_segregated_by_what_each_form_collects(world):
    with db() as c:
        p = profiles.faculty_profile(c, ADMIN, "EMP001")
    s = sections(p)
    assert list(s) == ["research", "achievements", "events", "outreach", "mentoring"]
    assert groups(s["research"]) == {"Journal papers": ["Paper One"], "Patents & IP": ["Patent One"], "Funded projects": ["DST Project"]}
    assert groups(s["achievements"]) == {"Awards & honours": ["Best Teacher"], "Invited talks & keynotes": ["Keynote on AI"]}
    assert groups(s["events"]) == {"Workshops & FDPs organised": ["AI Workshop"], "Conferences & symposia organised": ["Symposium"]}
    assert groups(s["outreach"]) == {"MoUs & collaborations": ["MoU with Acme"]}
    assert groups(s["mentoring"]) == {"Hackathons & coding competitions": ["SIH 2025"]}      # EMP002 mentored the chess entry, not EMP001

    roles = {i["title"]: i["role"] for sec in p["sections"] for g in sec["groups"] for i in g["items"]}
    assert roles["Paper One"] == "Lead author" and roles["Patent One"] == "Co-author (#2)"
    assert roles["AI Workshop"] == "Convener" and roles["Symposium"] == "Involved" and roles["MoU with Acme"] == "Submitted by"

    paper = s["research"]["groups"][0]["items"][0]
    assert {"text": "Q1", "tone": "ok"} in paper["badges"]
    assert ["Authors", "Dr. Asha Rao, Kavin M, Dr. X (ext.)"] in paper["facts"]            # names looked up from the roll / employee IDs
    summary = {x["label"]: x["value"] for x in p["summary"]}
    assert summary["Journal papers"] == 1 and summary["Patents"] == 1 and summary["Funded projects"] == 1 and summary["Events organised"] == 2
    assert summary["Talks & sessions"] == 1 and summary["Students mentored"] == 1 and summary["Research funding"] == "₹12,00,000"
    assert p["person"]["subtitle"] == "Professor" and any(t.startswith("Tutor · UG-") for t in p["person"]["tags"])


def test_academic_year_filter_keeps_the_year_list_complete(world):
    with db() as c:
        everything = profiles.faculty_profile(c, ADMIN, "EMP001")
        old = profiles.faculty_profile(c, ADMIN, "EMP001", "2024-25")
    assert everything["academic_years"] == ["2025-26", "2024-25"] == old["academic_years"]
    assert [i["title"] for sec in old["sections"] for g in sec["groups"] for i in g["items"]] == ["Patent One"]
    assert old["total"] == 1 and everything["total"] > 5


def test_student_page_splits_achievements_from_participations(world):
    with db() as c:
        p = profiles.student_profile(c, ADMIN, "21IT001")
    s = sections(p)
    assert list(s) == ["achievements", "participations", "research", "events", "placement"]
    assert groups(s["achievements"]) == {"Hackathons & coding competitions": ["SIH 2025"]}
    assert groups(s["participations"]) == {"Sports, cultural & co-curricular": ["Inter-college Chess"]}
    assert groups(s["research"]) == {"Journal papers": ["Paper One"]}
    assert groups(s["events"]) == {"Industry & outreach": ["MoU with Acme"]}
    assert set(groups(s["placement"])) == {"Status", "Offers", "Internship experience", "Interview experience"}
    sih = s["achievements"]["groups"][0]["items"][0]
    assert sih["role"] == "Team lead" and any(k == "Team" and "Kavin M" in v and "Divya S" in v for k, v in sih["facts"])
    assert ["Prize / scholarship", "₹50,000"] in sih["facts"] and ["Mentor", "Dr. Asha Rao"] in sih["facts"]
    summary = {x["label"]: x["value"] for x in p["summary"]}
    assert summary["Achievements"] == 1 and summary["Participations"] == 1 and summary["Offers"] == 1 and summary["Prize money"] == "₹50,000"
    with db() as c:
        other = profiles.student_profile(c, ADMIN, "21IT002")
    assert "participations" not in sections(other) and sections(other)["achievements"]["count"] == 1


def test_who_may_open_which_page(world):
    plain = User("EMP002", "Dr. Bala K", "STAFF", {"FACULTY"})
    tutor = User("EMP001", "Dr. Asha Rao", "STAFF", {"FACULTY", "TUTOR"}, class_ids={1}, tutor_class_ids={1})
    with db() as c:
        assert profiles.faculty_profile(c, plain, "EMP002")["person"]["id"] == "EMP002"          # your own page
        with pytest.raises(HTTPException) as e:
            profiles.faculty_profile(c, plain, "EMP001")                                         # someone else's page
        assert e.value.status_code == 403
        assert profiles.student_profile(c, tutor, "21IT001")["person"]["name"] == "Kavin M"
        with pytest.raises(HTTPException) as e:
            profiles.student_profile(c, tutor, "21IT009")                                        # a student of another class
        assert e.value.status_code == 403
        with pytest.raises(HTTPException) as e:
            profiles.student_profile(c, plain, "21IT001")
        assert e.value.status_code == 403
        with pytest.raises(HTTPException) as e:
            profiles.faculty_profile(c, ADMIN, "NOPE")
        assert e.value.status_code == 404


def test_empty_person_gets_an_empty_page_not_an_error(world):
    with db() as c:
        c.execute("INSERT INTO faculty (emp_id, full_name, email) VALUES ('EMP003', 'New Joiner', 'n@x.edu')")
        p = profiles.faculty_profile(c, ADMIN, "EMP003")
    assert p["sections"] == [] and p["total"] == 0 and p["person"]["subtitle"] == "Faculty"


# ---------------------------------------------------------------- by-work view (Admin / HoD) and the faculty list
from backend.master import people, works  # noqa: E402


def titles(res):
    return [i["title"] for i in res["items"]]


def test_catalog_lists_every_kind_of_work_with_counts(world):
    with db() as c:
        cat = works.catalog(c, ADMIN)
        old = works.catalog(c, ADMIN, "2024-25")
    types = {t["label"]: t["count"] for g in cat["groups"] for t in g["types"]}
    assert [g["id"] for g in cat["groups"]] == ["RESEARCH", "FACULTY", "DEPARTMENT", "OUTREACH", "STUDENT"]
    assert types["Journal papers"] == 1 and types["Patents & IP"] == 1 and types["Funded projects"] == 1 and types["Conference papers"] == 0
    assert types["Awards & honours"] == 1 and types["Invited talks & keynotes"] == 1 and types["Workshops & FDPs organised"] == 1
    assert types["Hackathons & coding competitions"] == 1 and types["Sports, cultural & co-curricular"] == 1 and types["MoUs & collaborations"] == 1
    assert cat["total"] == 10 and old["total"] == 1                         # the year filter changes the counts too
    research = next(g for g in cat["groups"] if g["id"] == "RESEARCH")
    quartile = next(f for f in research["filters"] if f["param"] == "quartile")
    assert [o["value"] for o in quartile["options"]] == ["Q1", "Q2", "Q3", "Q4", "Not applicable"]      # options come from the form itself
    assert {f["param"] for f in research["filters"]} >= {"indexing", "min_funding", "current_status"}


def test_filters_describe_the_work_not_the_people(world):
    with db() as c:
        ls = lambda group, category="", **f: works.list_works(c, ADMIN, group, category, f)
        assert titles(ls("RESEARCH", "Journal Publications")) == ["Paper One"]
        assert titles(ls("RESEARCH")) == ["Paper One", "DST Project", "Patent One"]                       # newest first
        assert titles(ls("RESEARCH", indexing="Scopus")) == ["Paper One"] and ls("RESEARCH", indexing="IEEE Xplore")["total"] == 0
        assert titles(ls("RESEARCH", quartile="Q1")) == ["Paper One"] and titles(ls("RESEARCH", min_funding="1000000")) == ["DST Project"]
        assert titles(ls("RESEARCH", q="IEEE")) == ["Paper One"]                                          # the text box also searches the venue
        assert titles(ls("RESEARCH", date_from="2025-08-01")) == ["Paper One"] and titles(ls("RESEARCH", ay_id="2024-25")) == ["Patent One"]
        assert titles(ls("FACULTY", level="State")) == ["Best Teacher"] and titles(ls("FACULTY", min_hours="1")) == ["Keynote on AI"]
        assert ls("DEPARTMENT")["total"] == 2 and titles(ls("OUTREACH", q="Acme")) == ["MoU with Acme"]
        assert titles(ls("STUDENT", entry_kind="PARTICIPATION")) == ["Inter-college Chess"] and titles(ls("STUDENT", level="National")) == ["SIH 2025"]
        assert titles(ls("STUDENT", min_prize="1000")) == ["SIH 2025"] and ls("STUDENT", class_id="1")["total"] == 2 and ls("STUDENT", class_id="2")["total"] == 0
        assert titles(ls("STUDENT", "Hackathons & Coding Competitions")) == ["SIH 2025"]
        # a hostile value is only ever a bound parameter; an unknown filter is ignored
        assert ls("RESEARCH", indexing="Scopus' OR '1'='1")["total"] == 0 and ls("RESEARCH", bogus="x")["total"] == 3
        # totals cover the whole filtered set
        stats = {s["label"]: s["value"] for s in ls("RESEARCH")["stats"]}
        assert stats["Total funding (₹)"] == 1200000 and stats["Scopus / WoS indexed"] == 1
        assert {s["label"]: s["value"] for s in ls("STUDENT")["stats"]}["Students involved"] == 2


def test_work_cards_show_who_was_involved(world):
    with db() as c:
        facts = lambda group, title: dict(next(i for i in works.list_works(c, ADMIN, group, "", {})["items"] if i["title"] == title)["facts"])
        assert facts("FACULTY", "Best Teacher")["Faculty"] == "Dr. Asha Rao"
        assert facts("DEPARTMENT", "Symposium")["Convener"] == "Dr. Bala K" and facts("DEPARTMENT", "Symposium")["Faculty involved"] == "Dr. Asha Rao"
        assert facts("OUTREACH", "MoU with Acme")["Lead"] == "Dr. Bala K"
        assert "Kavin M" in facts("STUDENT", "SIH 2025")["Team"] and "Dr. Asha Rao" == facts("STUDENT", "SIH 2025")["Mentor"]
        assert "Dr. Asha Rao" in facts("RESEARCH", "Paper One")["Authors"]
        assert all(i["role"] is None for i in works.list_works(c, ADMIN, "RESEARCH", "", {})["items"])      # a role belongs to a person's page, not here


def test_reports_are_for_admin_hod_and_coordinators_only_and_page_through(world):
    tutor = User("EMP001", "Dr. Asha Rao", "STAFF", {"FACULTY", "TUTOR"}, class_ids={1}, tutor_class_ids={1})
    hod = User("HOD1", "HoD", "STAFF", {"HOD", "FACULTY"}, all_access=True)
    with db() as c:
        for call in (lambda: works.catalog(c, tutor), lambda: works.list_works(c, tutor, "RESEARCH", "", {})):          # tutors and faculty do not get Reports
            with pytest.raises(HTTPException) as e:
                call()
            assert e.value.status_code == 403
        pc = User("EMP002", "Coordinator", "STAFF", {"PC", "FACULTY"}, class_ids={1, 2})
        assert works.catalog(c, hod)["total"] == works.catalog(c, pc)["total"] == 10                                    # the coordinator sees all of it
        with pytest.raises(HTTPException) as e:
            works.list_works(c, ADMIN, "NOPE", "", {})
        assert e.value.status_code == 400
        with pytest.raises(HTTPException) as e:
            works.list_works(c, ADMIN, "RESEARCH", "", {"min_funding": "lots"})
        assert e.value.status_code == 400
        page1, page2 = works.list_works(c, ADMIN, "RESEARCH", "", {}, 2, 0), works.list_works(c, ADMIN, "RESEARCH", "", {}, 2, 2)
        assert page1["total"] == page2["total"] == 3 and titles(page1) + titles(page2) == ["Paper One", "DST Project", "Patent One"]


def test_faculty_list_carries_activity_counts_for_the_filters(world):
    with db() as c:
        rows = {r["emp_id"]: r for r in people.list_faculty(c, ADMIN)}
        mine = lambda emp: rows[emp]["counts"]
        assert mine("EMP001") == {"research": 3, "achievements": 2, "events": 2, "outreach": 1, "mentored": 1}
        assert mine("EMP002") == {"research": 1, "achievements": 0, "events": 1, "outreach": 1, "mentored": 1}
        plain = User("EMP002", "Dr. Bala K", "STAFF", {"FACULTY"})
        assert all("counts" not in r for r in people.list_faculty(c, plain))                # only the Admin / HoD get the figures


# ---------------------------------------------------------------- CSV export with user-chosen columns
import csv as _csv  # noqa: E402
import io as _io  # noqa: E402


def read_csv(data: bytes):
    assert data.startswith(b"\xef\xbb\xbf")                                   # BOM so Excel reads ₹ and Tamil names correctly
    rows = list(_csv.reader(_io.StringIO(data.decode("utf-8-sig"))))
    return rows[0], rows[1:]


def test_export_contains_only_the_columns_the_user_picked(world):
    with db() as c:
        head, rows = read_csv(works.export_csv(c, ADMIN, "RESEARCH", "", {}, ["title", "date", "authors", "quartile", "funding_amount"]))
        assert head == ["Title", "Date", "Authors (in order)", "Quartile", "Funding amount (₹)"]            # exactly these, in this order
        assert [r[0] for r in rows] == ["Paper One", "DST Project", "Patent One"]                           # newest first, same as the screen
        assert rows[0][2] == "Dr. Asha Rao; Kavin M; Dr. X (ext.)" and rows[0][3] == "Q1" and float(rows[1][4]) == 1200000
        _, journal = read_csv(works.export_csv(c, ADMIN, "RESEARCH", "Journal Publications", {}, ["title"]))
        assert journal == [["Paper One"]]
        _, narrowed = read_csv(works.export_csv(c, ADMIN, "RESEARCH", "", {"quartile": "Q1"}, ["title"]))     # the page's work filters still apply
        assert narrowed == [["Paper One"]]


def test_export_date_filters(world):
    with db() as c:
        titles_of = lambda **f: [r[0] for r in read_csv(works.export_csv(c, ADMIN, "RESEARCH", "", f, ["title"]))[1]]
        assert titles_of(date_from="2025-08-01") == ["Paper One"] and titles_of(date_to="2024-12-31") == ["Patent One"]
        assert titles_of(date_from="2025-07-01", date_to="2025-07-31") == ["DST Project"] and titles_of(ay_id="2024-25") == ["Patent One"]
        assert titles_of(date_from="2030-01-01") == []


def test_every_column_of_every_group_exports(world):
    with db() as c:
        cat = works.catalog(c, ADMIN)
        for g in cat["groups"]:
            keys = [col["key"] for col in g["columns"]]
            assert len(keys) == len(set(keys)) and set(g["default_columns"]) <= set(keys), g["id"]
            head, rows = read_csv(works.export_csv(c, ADMIN, g["id"], "", {}, keys))                         # no SQL error for any column
            assert len(head) == len(keys) and len(rows) == g["count"], g["id"]
            assert {col["part"] for col in g["columns"]} >= {"Basics", "Links"}
        head, rows = read_csv(works.export_csv(c, ADMIN, "STUDENT", "Hackathons & Coding Competitions", {}, ["students", "rolls", "n_students", "classes", "mentor", "prize", "entry"]))
        st = dict(zip(head, rows[0]))
        assert st["Roll numbers"] == "21IT001; 21IT002" and st["Number of students"] == "2" and st["Faculty mentor"] == "Dr. Asha Rao"
        assert "Kavin M (21IT001)" in st["Students (name and roll no.)"] and st["Class at the time"] and st["Achievement or participation"] == "Achievement"


def test_export_refuses_bad_requests_and_defuses_formulas(world):
    tutor = User("EMP001", "Dr. Asha Rao", "STAFF", {"FACULTY", "TUTOR"}, class_ids={1}, tutor_class_ids={1})
    with db() as c:
        for who, group, cols, code in ((tutor, "RESEARCH", ["title"], 403), (ADMIN, "RESEARCH", [], 400), (ADMIN, "RESEARCH", ["title", "nope"], 400),
                                       (ADMIN, "RESEARCH", ["r.abstract) FROM x; --"], 400), (ADMIN, "NOPE", ["title"], 400)):
            with pytest.raises(HTTPException) as e:
                works.export_csv(c, who, group, "", {}, cols)
            assert e.value.status_code == code, (group, cols)
        res = ingest.ingest_row(c, "form_research", form_row("form_research", _submitter="EMP001", category="Journal Publications", title='=HYPERLINK("http://evil","click")',
                                                              current_status="Published", _contributors="EMP001", venue_publisher="X", output_date="2025-08-20", abstract="a"))
        assert res["status"] == "inserted"
        _, rows = read_csv(works.export_csv(c, ADMIN, "RESEARCH", "Journal Publications", {}, ["title"]))
        assert any(r[0].startswith("'=HYPERLINK") for r in rows) and not any(r[0].startswith("=") for r in rows)
