"""The forms the application ships now (the IT Matrix Google Forms of 25 November 2026): cards, questions, sheet layout, uploads, placement."""
import io
import json
import os
import sys

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app import app  # noqa: E402
from backend.master import blocks, definitions as D, entry, ingest, media  # noqa: E402
from backend.master.auth import load_user, set_staff_password  # noqa: E402
from backend.master.common import uniquify_headers  # noqa: E402
from backend.review import service  # noqa: E402
from database import db_manager  # noqa: E402
from database.master_db import db, init_master_db  # noqa: E402

client = TestClient(app)
PASS = "Matrix-Pass-1"
PDF = b"%PDF-1.4 a small certificate"


@pytest.fixture()
def world(monkeypatch, tmp_path):
    monkeypatch.setenv("MASTER_DB_PATH", str(tmp_path / "master.db"))
    monkeypatch.setenv("MASTER_ADMIN_PASSWORD", PASS)
    monkeypatch.setenv("MASTER_SECRET", "matrix-secret")
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.setattr(db_manager, "DB_PATH", str(tmp_path / "news.db"))
    db_manager.init_db()
    init_master_db()
    with db() as c:
        c.execute("INSERT INTO faculty (emp_id, full_name, email, designation) VALUES ('EMP001', 'Dr. Asha Rao', 'emp001@x.edu', 'Professor')")
        set_staff_password(c, "EMP001", PASS)
        for roll, name in (("21IT001", "Kavin M"), ("21IT002", "Divya S")):
            c.execute("INSERT INTO students (roll_no, full_name, programme, class_id) VALUES (?, ?, 'UG', 1)", (roll, name))
    return tmp_path


def user(uid="EMP001", kind="STAFF"):
    with db() as c:
        return load_user(c, uid, kind)


def picture():
    buf = io.BytesIO()
    Image.new("RGB", (60, 40), (10, 90, 160)).save(buf, "PNG")
    return buf.getvalue()


def answer(field):
    """A valid answer for one field of the entry screen."""
    kind = field["type"]
    if kind == "file":
        return media.save_document("EMP001", "certificate.pdf", PDF)["link_ref"]
    if kind == "photo":
        return [media.save_upload("EMP001", "photo.png", picture())["media_id"]]
    if kind == "multi":
        return field["choices"][:2]
    if field["choices"]:
        return field["choices"][0]
    return {"date": "2026-09-01", "number": "5", "url": "https://example.org", "roster_roll": "21IT001\n21IT002"}.get(kind, "Some answer")


def filled(form_id, category):
    form = entry.form_for(form_id, category)
    return form, {f["fid"]: answer(f) for f in form["fields"] if f["req"]}


def test_the_cards_are_titled_and_described_like_the_form_sections(world):
    cat = entry.catalog(None)
    assert [f["title"] for f in cat] == ["Research Contributions & Innovations", "Faculty Participation and Achievements", "Department Milestones & Achievements",
                                         "Industry, Alumni & Outreach", "Student Participation and Achievements"]
    assert [len(f["categories"]) for f in cat] == [8, 6, 8, 5, 15]
    journal = cat[0]["categories"][0]
    assert journal["name"] == "Journal Publications" and journal["description"] == "Enter the details of research articles published in national and international journals."
    assert "Research Seminar" in [c["name"] for c in cat[0]["categories"]]
    assert [c["name"] for c in cat[1]["categories"]][3] == "Resource Person / Session Chair Roles" and [c["name"] for c in cat[3]["categories"]][2] == "MoUs Signed & Industrial Collaborations"


def test_nothing_known_or_consent_related_is_asked(world):
    for form_id in D.FORM_IDS:
        for category in ingest.specs()["forms"][form_id]["categories"]:
            labels = [f["q"] for f in entry.form_for(form_id, category)["fields"]]
            for hidden in ("Accuracy and Authorization Confirmation", "Faculty Name", "Faculty name", "Faculty Email", "Faculty Full Name", "Designation"):
                assert hidden not in labels, (form_id, category, hidden)


def test_every_card_can_be_filled_submitted_and_approved(world):
    me, count = user(), 0
    for form_id in D.FORM_IDS:
        with db() as c:
            assert D.editor_view(c, form_id)["problems"] == [], form_id
        for category in ingest.specs()["forms"][form_id]["categories"]:
            _, values = filled(form_id, category)
            with db() as c:
                sent = entry.submit(c, me, form_id, category, values)
                admin = load_user(c, "ADMIN", "STAFF")
                assert service.get_item(c, admin, sent["item_id"])["blockers"] == [], (form_id, category)
                service.approve(c, admin, sent["item_id"])
            count += 1
    with db() as c:
        assert c.execute("SELECT COUNT(*) FROM form_submissions").fetchone()[0] == count == 42
        assert c.execute("SELECT COUNT(*) FROM research_contributors WHERE emp_id = 'EMP001'").fetchone()[0] == 8       # the person who entered it is an author
        assert {r[0] for r in c.execute("SELECT designation_at_time FROM faculty_achievements")} == {"Professor"}         # filled from their record
        assert c.execute("SELECT COUNT(*) FROM student_achievement_participants WHERE is_lead = 1").fetchone()[0] == 15   # the first roll number leads
        assert {r[0] for r in c.execute("SELECT is_team FROM student_achievements")} == {1}


def test_tick_several_and_documents_are_checked(world):
    me = user()
    form, values = filled("form_research", "Journal Publications")
    by = {f["q"]: f for f in form["fields"]}
    assert by["Indexing"]["type"] == "multi" and by["Upload Published Research Paper / Supporting Proof"]["type"] == "file"
    with db() as c:
        row = entry.build_row(c, me, "form_research", "Journal Publications", values)
    assert row["Indexing"] == "Scopus, Web of Science" and row["Upload Published Research Paper / Supporting Proof"].startswith("media://")
    for field, bad in (("Indexing", ["Nowhere"]), ("Upload Published Research Paper / Supporting Proof", "media://999")):
        with db() as c, pytest.raises(HTTPException) as e:
            entry.build_row(c, me, "form_research", "Journal Publications", {**values, by[field]["fid"]: bad})
        assert e.value.status_code == 400


def test_a_pdf_is_stored_as_it_is_and_served_as_a_pdf(world):
    token = client.post("/api/auth/login", json={"id": "EMP001", "password": PASS}).json()["token"]
    up = client.post("/api/media?kind=document", files={"file": ("c.pdf", PDF, "application/pdf")}, headers={"Authorization": "Bearer " + token})
    assert up.status_code == 200 and up.json()["kind"] == "DOCUMENT" and up.json()["link_ref"].startswith("media://")
    got = client.get("/api/media/" + up.json()["link_ref"][len("media://"):])
    assert got.content == PDF and got.headers["content-type"] == "application/pdf" and got.headers["x-content-type-options"] == "nosniff"
    for content, code in ((b"<html>not a document</html>", 400), (b"%PDF-" + b"x" * media.MAX_DOCUMENT, 413)):
        with pytest.raises(HTTPException) as e:
            media.save_document("EMP001", "x.pdf", content)
        assert e.value.status_code == code
    with pytest.raises(HTTPException):
        media.save_upload("EMP001", "c.pdf", PDF)                                                      # a photo question does not take a PDF


# ------------------------------------------------------------------------------------------------ the Google Forms as a second channel
def sheet_row(form_id, common, answers, closing=None):
    """A response row laid out as the sheet of the form: common columns, then 'which category?' + section columns for every section."""
    lay = ingest.specs()["forms"][form_id]["layout"]
    cells = [(t, common.get(t, "")) for t in lay["common"]]
    for b in lay["blocks"]:
        mine = answers.get(b["category"])
        cells.append((b["gate"], b["category"] if mine is not None else ""))
        cells += [(t, (mine or {}).get(t, "")) for t in b["fields"]]
    cells += [(t, (closing or {}).get(t, "")) for t in lay["closing"]]
    return dict(zip(uniquify_headers([h for h, _ in cells]), [v for _, v in cells]))


def test_the_research_sheet_starts_like_the_printed_form(world):
    heads = blocks.sheet_headers("form_research")
    assert heads[:7] == ["Timestamp", "Email Address", "Faculty Name", "Which research category would you like to fill first?", "Title of the Research Paper",
                         "Name of the Journal", "Type of Journal"]
    assert heads.count("Which remaining research category would you like to fill next?") == 7 and heads[-1] == "Accuracy and Authorization Confirmation"
    assert "Volume Number and Isue number" in heads                                  # the sheet column keeps the printed spelling


def test_a_response_with_two_sections_becomes_two_entries(world):
    row = sheet_row("form_research", {"Timestamp": "2026-11-25 10:00:00", "Email Address": "emp001@x.edu", "Faculty Name": "Dr. Asha Rao"}, {
        "Journal Publications": {"Title of the Research Paper": "Deep Triage", "Name of the Journal": "IEEE Access", "Volume Number and Isue number": "12(3)",
                                 "Month and Year of Publication": "2026-09-01"},
        "Conference Publications": {"Title of the Research Paper": "Edge Vision", "Name of the Conference": "ICAI"}})
    flat = blocks.expand("form_research", row)
    assert [f["Research Category"] for f in flat] == ["Journal Publications", "Conference Publications"]
    with db() as c:
        assert [ingest.ingest_row(c, "form_research", f)["status"] for f in flat] == ["inserted", "inserted"]
        rows = [tuple(r) for r in c.execute("SELECT s.title, r.venue_publisher, s.submitter_emp_id FROM form_submissions s JOIN research_outputs r USING (submission_id) ORDER BY s.submission_id")]
    assert rows == [("Deep Triage", "IEEE Access", "EMP001"), ("Edge Vision", "ICAI", "EMP001")]
    assert ingest.answer_values("form_research", flat[0])["x_volume_issue"] == "12(3)"           # read from the column with the printed spelling


def test_a_department_section_without_a_title_question_gets_one(world):
    row = sheet_row("form_departmental", {"Timestamp": "2026-11-25 10:00:00", "Faculty Name": "Dr. Asha Rao", "Faculty Email": "emp001@x.edu"},
                    {"MoU / Industry Collaboration / Partnerships": {"Industry/Organisation Details": "Acme Labs", "Key Objectives of collaboration": "Internships"}},
                    {"Budget / Investment in Rupees (numbers only)": "5000", "Funding Source": "Department"})
    (flat,) = blocks.expand("form_departmental", row)
    with db() as c:
        assert ingest.ingest_row(c, "form_departmental", flat)["status"] == "inserted"
        got = tuple(c.execute("SELECT s.title, d.budget_amount, d.funding_source FROM form_submissions s JOIN department_highlights d USING (submission_id)").fetchone())
    assert got == ("Collaboration with Acme Labs", 5000.0, "Department")


# ------------------------------------------------------------------------------------------------ a new edition of the forms
def test_forms_the_admin_never_edited_take_a_new_edition_and_edited_ones_are_kept(world):
    with db() as c:
        D.apply_op(c, "form_faculty", "add_field", {"label": "Admin's own question", "type": "text", "categories": ["Awards & Honors Received"]}, "ADMIN")
        D.publish(c, "form_faculty", "ADMIN", "mine")
        for r in c.execute("SELECT form_id, version, spec_json FROM form_definitions WHERE created_by = 'system'").fetchall():
            spec = json.loads(r["spec_json"])
            spec["shipped_version"] = "2.0"                                                           # as an older installation would have it
            spec["title"] = "Old title"
            c.execute("UPDATE form_definitions SET spec_json = ? WHERE form_id = ? AND version = ?", (json.dumps(spec), r["form_id"], r["version"]))
    init_master_db()
    specs = ingest.specs()["forms"]
    assert specs["form_research"]["title"] == "Research Contributions & Innovations"
    assert any(q["q"] == "Admin's own question" for q in specs["form_faculty"]["questions"])
    with db() as c:
        assert [r[0] for r in c.execute("SELECT status FROM form_definitions WHERE form_id = 'form_research' ORDER BY version")] == ["archived", "published"]


# ------------------------------------------------------------------------------------------------ the placement diary
def test_the_placement_diary_has_three_cards_and_keeps_the_new_answers(world):
    sections = entry.placement_form()
    assert [s["title"] for s in sections[1:4]] == ["B. Offer Details", "C. Interview Experience", "D. Internship Experience"]
    student = user("21IT001", "STUDENT")
    offer = {"company": "Acme", "offer_type": "Intern + Full Time", "package_lpa": "9", "difficulty": "Hard"}
    with db() as c, pytest.raises(HTTPException) as e:
        entry.submit_placement(c, student, {"offers": [offer]})                                   # the concepts question is required once the section is used
    assert "Academic Concepts" in str(e.value.detail)
    photo = media.save_upload("21IT001", "offer.png", picture())["link_ref"]
    with db() as c:
        assert entry.submit_placement(c, student, {"offers": [{**offer, "interview_concepts": "DBMS, OS", "offer_photo": photo}]})["offers"] == 1
        admin = load_user(c, "ADMIN", "STAFF")
        item = c.execute("SELECT item_id FROM staged_items WHERE form_id = 'placement'").fetchone()[0]
        service.approve(c, admin, item)
        assert tuple(c.execute("SELECT offer_type, photo FROM placement_offers").fetchone()) == ("FTE+INTERN", photo)
        assert tuple(c.execute("SELECT concepts, difficulty FROM interview_experiences").fetchone()) == ("DBMS, OS", "Hard")
        seen = dict(c.execute("SELECT * FROM v_diary_interviews").fetchone())
    assert seen["concepts"] == "DBMS, OS" and "photo" not in seen and "roll_no" not in seen        # juniors never see a photo or a name


MOU = "MoU / Industry Collaboration / Partnerships"


def test_department_mous_keep_their_dates_and_expiry_is_tracked(world):
    from datetime import date, timedelta
    from backend.master import analytics
    me = user()
    form, values = filled("form_departmental", MOU)
    by = {f["q"]: f for f in form["fields"]}
    assert by["MoU Start Date"]["req"] and not by["MoU Expiry Date"]["req"]
    assert "MoU Start Date" not in blocks.sheet_headers("form_departmental")                 # the Google Form has no such column: the import is not shifted
    soon = (date.today() + timedelta(days=30)).isoformat()
    values.update({by["Industry / Organisation Details"]["fid"]: "Acme Labs", by["MoU Start Date"]["fid"]: "2025-01-10"})
    with db() as c, pytest.raises(HTTPException) as e:
        entry.submit(c, me, "form_departmental", MOU, {**values, by["MoU Expiry Date"]["fid"]: "2024-12-31"})
    assert "is before" in e.value.detail
    with db() as c:
        sent = entry.submit(c, me, "form_departmental", MOU, {**values, by["MoU Expiry Date"]["fid"]: soon})
        admin = load_user(c, "ADMIN", "STAFF")
        service.approve(c, admin, sent["item_id"])
        assert tuple(c.execute("SELECT s.event_date, d.agreement_effective, d.agreement_expiry FROM form_submissions s JOIN department_highlights d USING (submission_id)").fetchone()) == ("2025-01-10", "2025-01-10", soon)
        assert analytics._mou_status(c) == [{"partner": "Acme Labs", "expiry": soon, "status": "Expiring soon"}]


def test_sections_the_google_form_does_not_have_stay_out_of_its_sheet_and_industry_mous_are_tracked(world):
    from backend.master import analytics
    assert "MoU Start Date" not in blocks.sheet_headers("form_industry") and "Title of the Session / Event" not in blocks.sheet_headers("form_faculty")
    row = sheet_row("form_faculty", {"Timestamp": "2026-11-25 10:00:00", "Email Address": "emp001@x.edu"},
                    {"FDP / Workshops Attended": {"Title of the FDP / Workshop / Training Programme": "Cloud FDP"}})
    assert [f["Achievement Category"] for f in blocks.expand("form_faculty", row)] == ["FDP / Workshops Attended"]          # the columns still line up
    me, category = user(), "MoUs Signed & Industrial Collaborations"
    form, values = filled("form_industry", category)
    by = {f["q"]: f["fid"] for f in form["fields"]}
    values.update({by["Industry / Organization Name"]: "Acme Labs", by["MoU Start Date"]: "2025-01-10", by["MoU Expiry Date"]: "2035-01-10"})
    with db() as c:
        sent = entry.submit(c, me, "form_industry", category, values)
        service.approve(c, load_user(c, "ADMIN", "STAFF"), sent["item_id"])
        assert tuple(c.execute("SELECT s.event_date, o.start_date, o.agreement_expiry FROM form_submissions s JOIN outreach_activities o USING (submission_id)").fetchone()) == ("2025-01-10", "2025-01-10", "2035-01-10")
        assert analytics._mou_status(c) == [{"partner": "Acme Labs", "expiry": "2035-01-10", "status": "Active"}]
