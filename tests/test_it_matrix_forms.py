"""The forms the application ships now (the IT Matrix Google Forms of 25 November 2026): cards, questions, uploads, placement."""
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
from backend.master import definitions as D, entry, ingest, media  # noqa: E402
from backend.master.auth import load_user, set_staff_password  # noqa: E402
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


def test_a_department_category_without_a_title_question_gets_one(world):
    me, category = user(), "MoU / Industry Collaboration / Partnerships"
    form, values = filled("form_departmental", category)
    by = {f["q"]: f["fid"] for f in form["fields"]}
    values[by["Industry / Organisation Details"]] = "Acme Labs"
    with db() as c:
        sent = entry.submit(c, me, "form_departmental", category, values)
    assert sent["title"] == "Collaboration with Acme Labs"


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


def test_industry_mous_are_tracked(world):
    from backend.master import analytics
    me, category = user(), "MoUs Signed & Industrial Collaborations"
    form, values = filled("form_industry", category)
    by = {f["q"]: f["fid"] for f in form["fields"]}
    values.update({by["Industry / Organization Name"]: "Acme Labs", by["MoU Start Date"]: "2025-01-10", by["MoU Expiry Date"]: "2035-01-10"})
    with db() as c:
        sent = entry.submit(c, me, "form_industry", category, values)
        service.approve(c, load_user(c, "ADMIN", "STAFF"), sent["item_id"])
        assert tuple(c.execute("SELECT s.event_date, o.start_date, o.agreement_expiry FROM form_submissions s JOIN outreach_activities o USING (submission_id)").fetchone()) == ("2025-01-10", "2025-01-10", "2035-01-10")
        assert analytics._mou_status(c) == [{"partner": "Acme Labs", "expiry": "2035-01-10", "status": "Active"}]


def test_a_class_tutor_uploads_placements_in_bulk_for_their_own_class_only(world):
    import openpyxl
    from backend.master import placements
    with db() as c:
        c.execute("INSERT INTO faculty (emp_id, full_name, email, designation) VALUES ('EMP002', 'Dr. Plain', 'emp002@x.edu', 'Professor')")
        set_staff_password(c, "EMP002", PASS)
        c.execute("INSERT INTO students (roll_no, full_name, programme, class_id) VALUES ('21IT101', 'Other Class', 'UG', 2)")
        c.execute("UPDATE classes SET tutor_id = 'EMP001' WHERE class_id = 1")
    auth = lambda uid: {"Authorization": "Bearer " + client.post("/api/auth/login", json={"id": uid, "password": PASS}).json()["token"]}
    wb = openpyxl.Workbook()
    ws = wb.active
    heads = placements.template_headers()
    ws.append(heads)
    for roll in ("21IT001", "21IT101"):
        row = placements.example_row()
        row[0] = roll
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    send = lambda h: client.post("/api/master/placements/upload", files={"file": ("p.xlsx", buf.getvalue())}, headers=h)
    tutor = auth("EMP001")
    assert client.get("/api/master/placements/template", headers=tutor).status_code == 200
    res = send(tutor).json()
    assert res["students"] == 1 and [e["roll_no"] for e in res["errors"]] == ["21IT101"] and "not in your class" in res["errors"][0]["message"]
    with db() as c:
        assert [r[0] for r in c.execute("SELECT roll_no FROM placement_offers")] == ["21IT001"]
        assert c.execute("SELECT COUNT(*) FROM placement_profiles WHERE roll_no = '21IT101'").fetchone()[0] == 0
    plain = auth("EMP002")
    assert send(plain).status_code == 403 and client.get("/api/master/placements/template", headers=plain).status_code == 403


# ------------------------------------------------------------------------------------------------ Submissions, Reports, My activities
def _approved(form_id, category, change=None):
    me = user()
    form, values = filled(form_id, category)
    by = {f["q"]: f["fid"] for f in form["fields"]}
    values.update({by[k]: v for k, v in (change or {}).items()})
    with db() as c:
        sent = entry.submit(c, me, form_id, category, values)
        service.approve(c, load_user(c, "ADMIN", "STAFF"), sent["item_id"])
    return form


def test_the_three_tabs_show_entries_under_the_current_data_entry_fields(world):
    import csv
    from backend.master import profiles, submissions, works
    form = _approved("form_research", "Journal Publications", {"Title of the Research Paper": "Deep Triage", "Name of the Journal": "IEEE Access"})
    with db() as c:
        admin = load_user(c, "ADMIN", "STAFF")
        # My activities: the card is grouped under the category and lists the form's fields, nothing about consent
        page = profiles.faculty_profile(c, admin, "EMP001")
        research = next(s for s in page["sections"] if s["id"] == "research")
        assert research["title"] == "Research Contributions & Innovations" and [g["title"] for g in research["groups"]] == ["Journal Publications"]
        card = research["groups"][0]["items"][0]
        shown = {k: v for k, v in card["facts"]}
        assert shown["Name of the Journal"] == "IEEE Access" and shown["Indexing"] == "Scopus, Web of Science" and "Type of Journal" in shown and "Authors" in shown
        assert [l["label"] for l in card["links"]] == ["Upload Published Research Paper / Supporting Proof"] and card["links"][0]["url"].startswith("media://")
        assert not any("Accuracy" in k or "Permission" in k or k == "Timestamp" for k, _ in card["facts"] + card["notes"])
        # Submissions
        rows = submissions.list_submissions(c, admin, {})["rows"]
        assert rows[0]["form"] == "Research Contributions & Innovations"
        detail = submissions.get_submission(c, admin, rows[0]["submission_id"])
        assert detail["header"]["category"] == "Journal Publications" and dict(detail["facts"])["Name of the Journal"] == "IEEE Access" and "detail" not in detail
        # Reports: one download column for each field the forms ask, and filters on what is asked
        cat = works.catalog(c, admin)
        group = next(g for g in cat["groups"] if g["id"] == "RESEARCH")
        assert group["title"] == "Research Contributions & Innovations" and "Research Seminar" in [t["category"] for t in group["types"]]
        keys = {col["key"]: col["label"] for col in group["columns"]}
        assert "f_x_journal_type" in keys and keys["f_x_journal_type"] == "Type of Journal" and not any("Permission" in v or "Accuracy" in v for v in keys.values())
        out = works.export_csv(c, admin, "RESEARCH", "", {}, ["title", "f_venue_publisher", "f_indexing"]).decode("utf-8-sig")
        assert list(csv.reader(io.StringIO(out)))[1] == ["Deep Triage", "IEEE Access", "Scopus, Web of Science"]
        assert works.list_works(c, admin, "RESEARCH", "", {"indexing": "Web of Science"})["total"] == 1
        assert works.list_works(c, admin, "RESEARCH", "", {"indexing": "IEEE"})["total"] == 0                  # a whole item of the list, not part of a word
        for g in cat["groups"]:
            works.export_csv(c, admin, g["id"], "", {}, [col["key"] for col in g["columns"]])                   # every column downloads


def test_a_field_added_in_the_form_builder_appears_in_the_three_tabs(world):
    from backend.master import profiles, submissions, works
    with db() as c:
        D.apply_op(c, "form_faculty", "add_field", {"label": "Funding for travel", "type": "text", "categories": ["Awards & Honors Received"], "required": True}, "ADMIN")
        D.publish(c, "form_faculty", "ADMIN", "x")
    _approved("form_faculty", "Awards & Honors Received", {"Funding for travel": "By the department"})
    with db() as c:
        admin = load_user(c, "ADMIN", "STAFF")
        card = next(s for s in profiles.faculty_profile(c, admin, "EMP001")["sections"] if s["id"] == "achievements")["groups"][0]["items"][0]
        assert ["Funding for travel", "By the department"] in card["facts"]
        sid = submissions.list_submissions(c, admin, {})["rows"][0]["submission_id"]
        assert ["Funding for travel", "By the department"] in submissions.get_submission(c, admin, sid)["facts"]
        assert "Funding for travel" in [col["label"] for col in next(g for g in works.catalog(c, admin)["groups"] if g["id"] == "FACULTY")["columns"]]


# ------------------------------------------------------------------------------------------------ the newsletter studio reads the local database
def _studio():
    token = client.post("/api/auth/login", json={"id": "ADMIN", "password": PASS}).json()["token"]
    head = {"Authorization": "Bearer " + token}

    def entries():
        r = client.get("/api/entries", headers=head)
        assert r.status_code == 200, r.text
        return {e["title"]: e for e in r.json()}
    return head, entries


def test_the_studio_lists_what_the_database_holds_with_no_import_step(world):
    head, entries = _studio()
    assert entries() == {}
    _approved("form_research", "Journal Publications", {"Title of the Research Paper": "Deep Triage", "Name of the Journal": "IEEE Access"})
    _approved("form_research", "Conference Publications", {"Title of the Research Paper": "Edge Vision", "Name of the Conference": "ICAI"})
    got = entries()                                                                       # approved a moment ago: already there
    assert set(got) == {"Deep Triage", "Edge Vision"}
    paper = got["Deep Triage"]
    assert paper["organization_or_venue"] == "IEEE Access" and paper["section_id"] == "sec_research" and paper["category_id"] != "cat_gen"
    assert paper["author_or_person"] == "Dr. Asha Rao" and paper["event_date"] == "2026-09-01" and paper["approval_status"] == "Approved"
    assert paper["evidence_url"].startswith("media://")
    assert [e["entry_id"] for e in entries().values()] == [e["entry_id"] for e in got.values()]          # reading again adds nothing


def test_the_studio_follows_changes_keeps_the_editors_decision_and_drops_withdrawn_entries(world):
    from database.db_manager import update_entry_status
    head, entries = _studio()
    _approved("form_research", "Journal Publications", {"Title of the Research Paper": "Deep Triage", "Name of the Journal": "IEEE Access"})
    _approved("form_research", "Conference Publications", {"Title of the Research Paper": "Edge Vision"})
    paper = entries()["Deep Triage"]
    update_entry_status(paper["entry_id"], "Rejected", "not this issue", True, 7, "Editor")
    with db() as c:                                                                       # the record is corrected in the database
        c.execute("UPDATE form_submissions SET title = 'Deep Triage, revised' WHERE title = 'Deep Triage'")
    after = entries()["Deep Triage, revised"]
    assert after["entry_id"] == paper["entry_id"] and after["approval_status"] == "Rejected" and after["featured_flag"] and after["display_order"] == 7
    with db() as c:
        admin = load_user(c, "ADMIN", "STAFF")
        item = c.execute("SELECT item_id FROM staged_items WHERE title = 'Edge Vision'").fetchone()[0]
        service.revoke(c, admin, item)
    assert set(entries()) == {"Deep Triage, revised"}
    with db() as c:
        c.execute("DELETE FROM form_submissions")                                         # a wrong or empty database never empties the newsletter
    assert set(entries()) == {"Deep Triage, revised"}


def test_which_field_fills_the_newsletter_is_set_in_the_form_builder(world):
    head, entries = _studio()
    _approved("form_research", "Journal Publications", {"Title of the Research Paper": "Deep Triage", "Name of the Journal": "IEEE Access", "Publisher Name": "IEEE Press"})
    assert entries()["Deep Triage"]["organization_or_venue"] == "IEEE Access"
    with db() as c:
        view = D.editor_view(c, "form_research")
        pick = lambda label: next(f["fid"] for f in view["fields"] if f["label"] == label and f["cats"] and "Journal Publications" in f["cats"])
        D.apply_op(c, "form_research", "update_field", {"fid": pick("Name of the Journal"), "changes": {"newsletter": ""}}, "ADMIN")
        D.apply_op(c, "form_research", "update_field", {"fid": pick("Publisher Name"), "changes": {"newsletter": "organization_or_venue"}}, "ADMIN")
        D.publish(c, "form_research", "ADMIN", "x")
    assert entries()["Deep Triage"]["organization_or_venue"] == "IEEE Press"


def test_the_studios_own_form_setup_and_hand_typed_entries_are_gone(world):
    head, _ = _studio()
    for method, url in (("post", "/api/entries/ingest"), ("post", "/api/entries/ingest-csv"), ("post", "/api/forms"), ("put", "/api/forms/form_research")):
        assert getattr(client, method)(url, headers=head).status_code in (404, 405), url
    page = client.get("/newsletter/").text
    assert 'data-tab="forms"' not in page and 'data-tab="overview"' not in page and "Add manually" not in page and "Sync from master database" not in page
    assert all(f'data-tab="{t}"' in page for t in ("responses", "front", "layout", "publish"))
