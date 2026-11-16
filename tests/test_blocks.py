"""The category-based forms: one response row holds several categories, read by column position.

The layouts are checked against the header rows of the real response sheets (tests/fixtures/sheet_headers.json): if a form changes, the sheet
and config/master_forms.json drift apart and these tests say so.
"""
import io
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.master import blocks, ingest, placements  # noqa: E402
from backend.master.common import base_title, norm_header, uniquify_headers  # noqa: E402
from backend.review import service, sheets  # noqa: E402
from database.master_db import db, init_master_db  # noqa: E402

HEADERS = json.load(open(os.path.join(os.path.dirname(__file__), "fixtures", "sheet_headers.json"), encoding="utf-8"))
FORMS = ["form_student", "form_research", "form_faculty", "form_industry", "form_departmental"]
YES = "Yes - Submit"


def squash(t):
    return " ".join(str(t).split())


def sheet_row(form_id, common=None, blocks_=None, closing=None):
    """A full response row as the Google Sheet holds it: every column, repeated titles made unique by position."""
    lay = ingest.specs()["forms"][form_id]["layout"]
    cells = [(t, (common or {}).get(t, "")) for t in lay["common"]]
    for b in lay["blocks"]:
        answers = (blocks_ or {}).get(b["category"])
        cells.append((b["gate"], YES if answers is not None else "No - Skip this category"))
        cells += [(t, (answers or {}).get(t, "")) for t in b["fields"]]
    cells += [(t, (closing or {}).get(t, "")) for t in lay["closing"]]
    return dict(zip(uniquify_headers([h for h, _ in cells]), [v for _, v in cells]))


@pytest.fixture()
def world(monkeypatch, tmp_path):
    monkeypatch.setenv("MASTER_DB_PATH", str(tmp_path / "master.db"))
    monkeypatch.setenv("MASTER_ADMIN_PASSWORD", "AdminPass1!")
    monkeypatch.setenv("MASTER_SECRET", "blocks-secret")
    init_master_db()
    with db() as c:
        for emp, name in (("C6608", "Dr. M. L. Valarmathi"), ("C5213", "Dr. K. Anitha Kumari"), ("C1940", "Dr. B. Vinoth Kumar")):
            c.execute("INSERT INTO faculty (emp_id, full_name, email, designation) VALUES (?,?,?,?)", (emp, name, emp.lower() + "@psgtech.example", "Professor"))
        for roll, name in (("23IT001", "Kavin M"), ("23IT002", "Divya S")):
            c.execute("INSERT INTO students (roll_no, full_name, programme, class_id) VALUES (?, ?, 'UG', 1)", (roll, name))
            c.execute("INSERT INTO student_class_history (roll_no, class_id, from_date, action) VALUES (?, 1, '2025-06-01', 'Added')", (roll,))
    return tmp_path


def q(sql, *args):
    with db() as c:
        return [tuple(r) for r in c.execute(sql, args)]


# ------------------------------------------------------------------------------------------------ the layouts match the real sheets
@pytest.mark.parametrize("fid", FORMS)
def test_the_layout_matches_the_real_response_sheet_column_by_column(fid):
    mine, real = blocks.sheet_headers(fid), HEADERS[fid]
    assert len(mine) == len(real)
    assert [squash(h) for h in mine] == [squash(h) for h in real]


@pytest.mark.parametrize("fid", FORMS)
def test_testing_the_real_sheet_finds_nothing_wrong(fid):
    r = sheets._check_block_form(fid, uniquify_headers(HEADERS[fid]))
    assert r == {"missing_required": [], "unknown_columns": [], "layout_differences": []}


def test_every_column_of_the_placement_sheet_is_understood():
    known = {norm_header(t) for q_ in placements.questions() for t in (q_["q"], *q_.get("aliases", []))} | {"timestamp", "email address"}
    unknown = [h for h in HEADERS["placement"] if norm_header(h) not in known and not norm_header(h).startswith(("do you have", "would you like"))]
    assert unknown == []


def test_repeated_titles_keep_their_position():
    assert uniquify_headers(["A", "B", "A", "", "A"]) == ["A", "B", "A#2", "", "A#3"] and base_title("A#3") == "A"


# ------------------------------------------------------------------------------------------------ one response, several categories
def test_a_response_with_two_categories_becomes_two_entries(world):
    row = sheet_row("form_research", common={"Timestamp": "2026-11-02 10:00:00", "Email Address": "c6608@psgtech.example", "Submitting Faculty (Select your name)": "C6608 - Dr. M. L. Valarmathi"},
                    blocks_={"Journal Publications": {"Research Paper / Article Title": "Deep Models for Triage", "Journal Name": "IEEE Access", "Author Names and Affiliations": "Dr. M. L. Valarmathi\nEXT - Dr. J. Smith - IIT",
                                                      "Publication Date": "2026-09-15", "DOI / ISSN": "10.1109/x.1", "Indexing": "Scopus", "Quartile": "Q1"},
                             "Patents & Intellectual Property": {"Patent / Intellectual Property Title": "Smart Sensor", "Inventor Names and Affiliations": "C6608 - Dr. M. L. Valarmathi",
                                                                 "Application / Registration Number": "2026/12345", "Filing Date": "2026-08-01", "Patent / IP Status": "Filed"}},
                    closing={"Key Impact Badge / Metric (e.g. Scopus Q1, Patent Granted, ₹25 Lakh Grant, Best Paper Award)": "Scopus Q1", "Is this a Landmark / Milestone Achievement?": "No (Standard Entry)",
                             "Permission to Publish this Submission": "Yes - may be published in the IT Chronicles newsletter"})
    flat = blocks.expand("form_research", row)
    assert [f["Research Subcategory"] for f in flat] == ["Journal Publications", "Patents & Intellectual Property"]
    assert all(f["Key Impact Badge / Metric (e.g. Scopus Q1, Patent Granted, ₹25 Lakh Grant, Best Paper Award)"] == "Scopus Q1" and f["Timestamp"] for f in flat)    # common columns reach every entry
    assert "Smart Sensor" not in " ".join(flat[0].values()) and "Deep Models for Triage" not in " ".join(flat[1].values())                                  # and each entry keeps only its own category's answers
    with db() as c:
        results = [ingest.ingest_row(c, "form_research", f) for f in flat]
    assert [r["status"] for r in results] == ["inserted", "inserted"]
    rows = q("SELECT s.category, s.title, s.event_date, s.submitter_emp_id, r.current_status, r.venue_publisher, r.identifier, r.indexing, r.quartile "
             "FROM form_submissions s JOIN research_outputs r USING (submission_id) ORDER BY s.submission_id")
    assert rows[0] == ("Journal Publications", "Deep Models for Triage", "2026-09-15", "C6608", "Published", "IEEE Access", "10.1109/x.1", "Scopus", "Q1")
    assert rows[1][:5] == ("Patents & Intellectual Property", "Smart Sensor", "2026-08-01", "C6608", "Filed")
    people = q("SELECT person_type, emp_id, name FROM research_contributors WHERE submission_id = 1 ORDER BY author_order")
    assert people == [("FACULTY", "C6608", "Dr. M. L. Valarmathi"), ("EXTERNAL", None, "Dr. J. Smith")]       # a plain name of a faculty member is recognised


def test_categories_answered_no_are_skipped_and_an_empty_response_gives_nothing():
    assert blocks.expand("form_faculty", sheet_row("form_faculty", common={"Timestamp": "t"})) == []
    row = sheet_row("form_faculty", common={"Timestamp": "t"}, blocks_={"Awards & Honors Received": {"Exact Title of Award / Certification / Lecture / Role": "Best Teacher"}})
    assert [f["Achievement Category"] for f in blocks.expand("form_faculty", row)] == ["Awards & Honors Received"]


def test_a_form_without_a_date_question_uses_the_day_it_was_submitted(world):
    row = sheet_row("form_faculty", common={"Timestamp": "2026-10-03 09:30:00", "Email Address": "c5213@psgtech.example", "Faculty Full Name (Select your name)": "C5213 - Dr. K. Anitha Kumari",
                                            "Designation at the Time of Achievement": "Professor"},
                    blocks_={"Invited Keynote / Expert Lectures Delivered": {"Exact Title of Award / Certification / Lecture / Role": "Keynote on AI", "Level": "National",
                                                                              "Awarding Body / Host Institution / Organizing Organization": "XYZ College",
                                                                              "Additional Information for the Review Team": "Spoke on trustworthy AI."}})
    (flat,) = blocks.expand("form_faculty", row)
    with db() as c:
        assert ingest.ingest_row(c, "form_faculty", flat)["status"] == "inserted"
    assert q("SELECT s.category, s.title, s.event_date, s.submitter_emp_id, f.emp_id, f.level, f.designation_at_time, f.description "
             "FROM form_submissions s JOIN faculty_achievements f USING (submission_id)") == [
        ("Invited Keynote / Expert Lectures Delivered", "Keynote on AI", "2026-10-03", "C5213", "C5213", "National", "Professor", "Spoke on trustworthy AI.")]


def test_the_faculty_highlights_form_makes_a_title_and_finds_dates_in_text(world):
    row = sheet_row("form_departmental", common={"Timestamp": "2026-11-01 08:00:00", "Faculty Name": "Dr. B. Vinoth Kumar", "Faculty Email": "c1940@psgtech.example"},
                    blocks_={"Highlights": {"Event / Initiative Overview and Key Highlights": "The department hosted a national hackathon with 40 teams. Winners were felicitated.",
                                            "Objectives and Rationale": "Promote problem solving"},
                             "Events / Programs": {"Event Overview and Key Highlights": "Two-day workshop on cloud security for faculty and students.",
                                                   "Event Date and Venue": "12 March 2026, Seminar Hall", "Number of Participants": "85"}},
                    closing={"Budget / Investment in Rupees (numbers only)": "50000", "Challenges and Mitigation": "Limited lab seats, handled in two batches"})   # the closing column repeats a block title
    flat = blocks.expand("form_departmental", row)
    assert [f["Department Highlight Category"] for f in flat] == ["Highlights", "Events / Programs"]
    assert flat[0]["Email Address"] == "c1940@psgtech.example"                                        # "Faculty Email" stands in for the e-mail column
    with db() as c:
        assert [ingest.ingest_row(c, "form_departmental", f)["status"] for f in flat] == ["inserted", "inserted"]
    rows = q("SELECT s.category, s.title, s.event_date, s.submitter_emp_id, d.venue, d.participant_count, d.challenges, d.budget_amount, d.overview "
             "FROM form_submissions s JOIN department_highlights d USING (submission_id) ORDER BY s.submission_id")
    assert rows[0][:4] == ("Highlights", "The department hosted a national hackathon with 40 teams", "2026-11-01", "C1940")         # title from the overview; date = the day submitted
    assert rows[1][:6] == ("Events / Programs", "Two-day workshop on cloud security for faculty and students.", "2026-03-12", "C1940", "12 March 2026, Seminar Hall", 85)
    assert rows[1][6] == "Limited lab seats, handled in two batches" and rows[1][7] == 50000.0         # the closing answer fills what the category left empty


def test_an_mou_copies_its_effective_date_and_an_alumni_event_is_marked_alumni(world):
    row = sheet_row("form_industry", common={"Timestamp": "2026-10-10 11:00:00", "Submitting Faculty (Select your name)": "C6608 - Dr. M. L. Valarmathi", "Lead Coordinator": "C5213 - Dr. K. Anitha Kumari"},
                    blocks_={"MoUs Signed & Industrial Collaborations": {"Official Title of MoU / Partnership": "MoU with Acme", "Partner Company / Organization": "Acme Corp",
                                                                          "MoU / Partnership Scope": "Joint projects and internships", "Agreement Effective Date": "2026-09-01",
                                                                          "Agreement Expiry / Renewal Date": "2029-09-01"},
                             "Alumni Interactions & Mentorship Sessions": {"Official Title of Event / Interaction": "Alumni meet", "Partner Company / Organization / Alumni Group": "Alumni Association",
                                                                           "Alumni Names and Current Designations": "R. Kumar, SDE", "Event Date": "2026-09-20"}})
    flat = blocks.expand("form_industry", row)
    with db() as c:
        assert [ingest.ingest_row(c, "form_industry", f)["status"] for f in flat] == ["inserted", "inserted"]
    rows = q("SELECT s.category, s.title, s.event_date, o.lead_emp_id, o.start_date, o.agreement_effective, o.agreement_expiry, o.partner_type, o.speakers "
             "FROM form_submissions s JOIN outreach_activities o USING (submission_id) ORDER BY s.submission_id")
    assert rows[0] == ("MoUs Signed & Industrial Collaborations", "MoU with Acme", "2026-09-01", "C5213", "2026-09-01", "2026-09-01", "2029-09-01", None, None)
    assert rows[1][0] == "Alumni Interactions & Mentorship Sessions" and rows[1][2] == "2026-09-20" and rows[1][7] == "Alumni Association" and rows[1][8] == "R. Kumar, SDE"


def test_student_response_keeps_the_roll_numbers_for_every_category(world):
    row = sheet_row("form_student", common={"Timestamp": "2026-10-20 12:00:00", "Email Address": "c6608@psgtech.example", "Achievement or Participation": "Achievement (won, ranked or awarded)",
                                            "Participants (One roll number per line)": "23IT001\n23IT002", "Lead Student Roll Number": "23IT001", "Individual or Team Achievement": "Team"},
                    blocks_={"Hackathons & Coding Competitions": {"Name of Competition / Award / Project / Event": "Smart India Hackathon", "Organizing Institute / Company / Awarding Body": "AICTE",
                                                                  "Achievement Level": "National", "Position / Rank / Prize / Scholarship": "Winner",
                                                                  "Prize / Scholarship Amount in Rupees (numbers only, 0 if none)": "50000", "Date of Achievement / Result": "2026-09-12",
                                                                  "Faculty Mentor / Project Guide": "Dr. M. L. Valarmathi", "Project Abstract / Solution Details": "A triage bot."},
                             "Sports, Cultural & Co-Curricular Accomplishments": {"Name of Competition / Award / Project / Event": "Chess", "Organizing Institute / Company / Awarding Body": "PSG",
                                                                                  "Date of Achievement / Result": "2026-08-01", "Position / Rank / Prize / Scholarship": "Runner-up"}})
    flat = blocks.expand("form_student", row)
    with db() as c:
        assert [ingest.ingest_row(c, "form_student", f)["status"] for f in flat] == ["inserted", "inserted"]
    assert q("SELECT s.category, s.title, a.position, a.prize_amount, a.mentor_emp_id, a.abstract FROM form_submissions s JOIN student_achievements a USING (submission_id) ORDER BY 1") == [
        ("Hackathons & Coding Competitions", "Smart India Hackathon", "Winner", 50000.0, "C6608", "A triage bot."), ("Sports, Cultural & Co-Curricular Accomplishments", "Chess", "Runner-up", None, None, None)]
    assert q("SELECT submission_id, COUNT(*) FROM student_achievement_participants GROUP BY 1") == [(1, 2), (2, 2)]


# ------------------------------------------------------------------------------------------------ the review queue and uploads
def test_each_category_of_a_response_is_reviewed_on_its_own(world):
    row = sheet_row("form_research", common={"Timestamp": "2026-11-02 10:00:00", "Email Address": "c6608@psgtech.example", "Submitting Faculty (Select your name)": "C6608 - Dr. M. L. Valarmathi"},
                    blocks_={"Journal Publications": {"Research Paper / Article Title": "Paper A", "Journal Name": "J1", "Author Names and Affiliations": "C6608", "Publication Date": "2026-09-01"},
                             "Funded Research Projects": {"Project Title": "Project B", "Principal Investigator": "C6608", "Funding Agency": "DST", "Sanctioned Grant Amount (INR)": "1200000",
                                                          "Project Start Date": "2026-07-01", "Project Objectives and Rationale": "Study it."}})
    with db() as c:
        assert service.stage_rows(c, "form_research", [row])["new"] == 2
        assert service.stage_rows(c, "form_research", [row])["unchanged"] == 2                      # pulling the same sheet again adds nothing
        titles = {r[0]: r[1] for r in c.execute("SELECT title, category FROM staged_items")}
        assert titles == {"Paper A": "Journal Publications", "Project B": "Funded Research Projects"}
        from backend.master.auth import User
        admin = User("ADMIN", "Admin", "STAFF", {"ADMIN"}, all_access=True)
        item = [r[0] for r in c.execute("SELECT item_id FROM staged_items WHERE title = 'Project B'")][0]
        d = service.get_item(c, admin, item)
        shown = {f["q"] for f in d["rows"][0]["fields"]}
        assert "Project Title" in shown and "Funding Agency" in shown and "Journal Name" not in shown            # only the fields of that category
        assert d["blockers"] == []
        service.approve(c, admin, item, edits=[{"Sanctioned Grant Amount (INR)": "1500000"}])
        assert [tuple(r) for r in c.execute("SELECT s.title, r.funding_amount, r.funding_status FROM form_submissions s JOIN research_outputs r USING (submission_id)")] == [("Project B", 1500000.0, "Funded")]


def test_an_excel_export_of_the_sheet_uploads_like_the_sheet_itself(world):
    import openpyxl
    row = sheet_row("form_faculty", common={"Timestamp": "2026-10-03 09:30:00", "Email Address": "c5213@psgtech.example", "Faculty Full Name (Select your name)": "C5213 - Dr. K. Anitha Kumari",
                                            "Designation at the Time of Achievement": "Professor"},
                    blocks_={"Awards & Honors Received": {"Exact Title of Award / Certification / Lecture / Role": "Best Teacher"},
                             "FDP / Workshops Attended": {"Exact Title of Award / Certification / Lecture / Role": "FDP on Cloud"}})
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(blocks.sheet_headers("form_faculty"))                       # the header row repeats titles, exactly like the sheet
    ws.append(list(row.values()))
    buf = io.BytesIO()
    wb.save(buf)
    res = ingest.upload_excel("form_faculty", buf.getvalue())
    assert res["inserted"] == 2 and res["duplicates_skipped"] == 0
    assert ingest.upload_excel("form_faculty", buf.getvalue())["duplicates_skipped"] == 2
    assert [r[0] for r in q("SELECT title FROM form_submissions ORDER BY title")] == ["Best Teacher", "FDP on Cloud"]


def test_the_newsletter_reads_the_same_entries_and_names_each_category(world):
    from backend.services.normalization_service import NormalizationService
    norm = NormalizationService()
    row = sheet_row("form_research", common={"Timestamp": "t", "Email Address": "e@x", "Submitting Faculty (Select your name)": "C6608 - Dr. M. L. Valarmathi"},
                    blocks_={"Funded Research Projects": {"Project Title": "Project B", "Principal Investigator": "C6608 - Dr. M. L. Valarmathi", "Funding Agency": "DST",
                                                          "Sanctioned Grant Amount (INR)": "1200000", "Project Start Date": "2026-07-01", "Project Objectives and Rationale": "Study it."}})
    (flat,) = blocks.expand("form_research", row)
    e = norm.normalize_response("form_research", flat)
    assert (e["title"], e["organization_or_venue"], e["event_date"], e["category_id"], e["description"]) == ("Project B", "DST", "2026-07-01", "cat_funded_projects", "Study it.")
    hl = sheet_row("form_departmental", common={"Timestamp": "t", "Faculty Name": "Dr. B. Vinoth Kumar"},
                   blocks_={"Highlights": {"Event / Initiative Overview and Key Highlights": "A national hackathon with 40 teams."}})
    (flat,) = blocks.expand("form_departmental", hl)
    with db() as c:
        ingest.ingest_row(c, "form_departmental", flat)
    e = norm.normalize_response("form_departmental", flat)
    assert e["category_id"] == "cat_dept_highlights" and e["description"] == "A national hackathon with 40 teams."


def test_faculty_are_matched_by_the_e_mail_when_no_name_was_chosen_from_a_list(world):
    """The forms may still carry the placeholder drop-down ('Replace with Faculty Name 1'): the e-mail saved in the portal identifies the person."""
    row = sheet_row("form_faculty", common={"Timestamp": "2026-10-03 09:30:00", "Email Address": "C5213@PSGTECH.example", "Faculty Full Name (Select your name)": "Replace with Faculty Name 1",
                                            "Designation at the Time of Achievement": "Professor"},
                    blocks_={"Awards & Honors Received": {"Exact Title of Award / Certification / Lecture / Role": "Best Teacher"}})
    ind = sheet_row("form_industry", common={"Timestamp": "2026-10-10 11:00:00", "Email Address": "c6608@psgtech.example", "Submitting Faculty (Select your name)": "Replace with Faculty Name 1",
                                             "Lead Coordinator": "EMP001 - Faculty Name 1"},
                    blocks_={"Industrial Visits & Field Tours": {"Official Title of Industrial Visit / Field Tour": "Visit to Acme", "Partner Company / Organization": "Acme"}})
    with db() as c:
        res = ingest.ingest_row(c, "form_faculty", blocks.expand("form_faculty", row)[0])
        assert res["status"] == "inserted" and not any("not found" in w or "matched" in w for w in res["warnings"]), res
        res2 = ingest.ingest_row(c, "form_industry", blocks.expand("form_industry", ind)[0])
    assert q("SELECT s.submitter_emp_id, f.emp_id FROM form_submissions s JOIN faculty_achievements f USING (submission_id)") == [("C5213", "C5213")]
    assert q("SELECT s.submitter_emp_id, o.lead_emp_id FROM form_submissions s JOIN outreach_activities o USING (submission_id)") == [("C6608", "C6608")]
    assert any("lead coordinator" in w for w in res2["warnings"])                  # the approver is told, and can pick someone else
