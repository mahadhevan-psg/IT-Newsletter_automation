"""Entering data in the portal: editable definitions (draft, publish, history), the entry screen's data, submission into the approval queue, photos."""
import io
import json
import os
import sys

import pytest
from fastapi.testclient import TestClient
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app import app  # noqa: E402
from backend.master import definitions as D, entry, ingest, media  # noqa: E402
from backend.master.auth import set_staff_password  # noqa: E402
from backend.review import service  # noqa: E402
from database import db_manager  # noqa: E402
from database.master_db import db, init_master_db  # noqa: E402

pytestmark = pytest.mark.usefixtures("previous_forms")            # engine tests: see conftest.py

client = TestClient(app)
PASS = "Entry-Pass-1"
RESEARCH, JOURNAL = "form_research", "Journal Publications"


@pytest.fixture()
def world(monkeypatch, tmp_path):
    monkeypatch.setenv("MASTER_DB_PATH", str(tmp_path / "master.db"))
    monkeypatch.setenv("MASTER_ADMIN_PASSWORD", PASS)
    monkeypatch.setenv("MASTER_SECRET", "entry-secret")
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.setattr(db_manager, "DB_PATH", str(tmp_path / "news.db"))
    db_manager.init_db()
    init_master_db()
    with db() as c:
        for emp, name in (("EMP001", "Dr. Asha Rao"), ("EMP002", "Dr. Head")):
            c.execute("INSERT INTO faculty (emp_id, full_name, email, designation) VALUES (?,?,?,?)", (emp, name, f"{emp.lower()}@x.edu", "Professor"))
            set_staff_password(c, emp, PASS)
        c.execute("INSERT INTO role_assignments (emp_id, role) VALUES ('EMP002', 'HOD')")
        c.execute("INSERT INTO students (roll_no, full_name, programme, class_id) VALUES ('21IT001', 'Kavin M', 'UG', 1)")
    return tmp_path


def token(uid):
    r = client.post("/api/auth/login", json={"id": uid, "password": PASS})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


def user(uid="EMP001"):
    from backend.master.auth import load_user
    with db() as c:
        return load_user(c, uid, "STAFF")


def jpeg(w=3000, h=2000, color=(30, 120, 200)):
    img = Image.effect_noise((w, h), 60).convert("RGB")      # noisy on purpose: a poor candidate for compression
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=95)
    return buf.getvalue()


def field(view, label, cat=JOURNAL):
    return next(f for f in view["fields"] if f["label"] == label and (not f["cats"] or cat in f["cats"]))


# ------------------------------------------------------------------------------------------------ definitions: draft, publish, history
def test_a_new_database_starts_from_the_shipped_definitions_and_serves_them_from_the_database(world):
    with db() as c:
        assert [r[0] for r in c.execute("SELECT DISTINCT status FROM form_definitions")] == ["published"]
        assert c.execute("SELECT COUNT(*) FROM form_definitions WHERE form_id = '_sections'").fetchone()[0] == 1
    assert JOURNAL in ingest.specs()["forms"][RESEARCH]["categories"] and ingest.specs()["placement"]["questions"]


def test_edits_stay_in_a_draft_until_published_and_then_reach_everything(world):
    with db() as c:
        D.apply_op(c, RESEARCH, "add_field", {"label": "Impact on teaching", "type": "para", "categories": [JOURNAL], "newsletter": "description"}, "ADMIN")
        view = D.editor_view(c, RESEARCH)
    assert view["has_draft"] and field(view, "Impact on teaching")["key"].startswith("x_")
    assert "Impact on teaching" not in [f["q"] for f in entry.form_for(RESEARCH, JOURNAL)["fields"]]          # not yet: a draft changes nothing for users
    with db() as c:
        res = D.publish(c, RESEARCH, "ADMIN", "teaching impact")
    assert res["version"] == 2 and res["impact"]["added_fields"] == ["Impact on teaching"]
    assert "Impact on teaching" in [f["q"] for f in entry.form_for(RESEARCH, JOURNAL)["fields"]]               # now it is on the entry screen ...
    assert "Impact on teaching" in [q["q"] for q in ingest.specs()["forms"][RESEARCH]["questions"]]            # ... and in the importer, reviews and reports
    with db() as c:
        assert [h["status"] for h in D.history(c, RESEARCH)][:2] == ["published", "archived"]


def _preview(view, cat):
    """What the builder's canvas draws for a category, from the editor data alone."""
    by = {f["fid"]: f for f in view["fields"]}
    c = next(x for x in view["categories"] if x["name"] == cat)
    return [(by[i]["display"], by[i]["widget"], by[i]["required"]) for i in c["fids"]]


def _real(form_id, cat):
    return [(f["q"], f["type"], f["req"]) for f in entry.form_for(form_id, cat)["fields"]]


def test_the_builders_canvas_shows_exactly_what_the_entry_screen_shows(world):
    with db() as c:
        for form_id in ("form_student", RESEARCH, "form_faculty", "form_departmental", "form_industry"):
            view = D.editor_view(c, form_id)
            for cat in view["categories"]:
                assert _preview(view, cat["name"]) == _real(form_id, cat["name"]), (form_id, cat["name"])
    # an edited draft must preview what faculty will see once it is published
    with db() as c:
        D.apply_op(c, RESEARCH, "add_field", {"label": "Impact on teaching", "type": "para", "categories": [JOURNAL]}, "ADMIN")
        D.apply_op(c, RESEARCH, "update_field", {"fid": field(D.editor_view(c, RESEARCH), "Impact on teaching")["fid"], "changes": {"required": True}}, "ADMIN")
        retire = next(f for f in D.editor_view(c, RESEARCH)["fields"] if not f["locked"] and not f["retired"] and f["cats"] == [JOURNAL] and not f["required"])
        D.apply_op(c, RESEARCH, "retire_field", {"fid": retire["fid"], "category": JOURNAL}, "ADMIN")
        before = _preview(D.editor_view(c, RESEARCH), JOURNAL)
    with db() as c:
        D.publish(c, RESEARCH, "ADMIN", "parity")
    assert before == _real(RESEARCH, JOURNAL) and ("Impact on teaching", "para", True) in before and retire["display"] not in [b[0] for b in before]


def test_field_and_category_edits_follow_the_rules(world):
    with db() as c:
        spec = D.get_draft(c, RESEARCH, "ADMIN")
        with pytest.raises(Exception):
            D.add_field(spec, "Journal Name", "text", [JOURNAL])                                  # the same name twice in one category
        with pytest.raises(Exception):
            D.add_field(spec, "Stage", "choice", [JOURNAL], choices=["only one"])                  # a pick-one needs two choices
        q = D.add_field(spec, "Stage", "list", [JOURNAL], choices=["Draft", "Final"], required=True)
        D.update_field(spec, q["fid"], {"label": "Manuscript stage", "help": "Where is it now?"})
        assert q["q"] == "Manuscript stage" and "Stage" in q["aliases"]                           # the earlier label stays understood
        title = next(x for x in spec["questions"] if x.get("key") == "title" and JOURNAL in (x.get("cats") or []))
        with pytest.raises(Exception):
            D.retire_field(spec, title["fid"])                                                    # the heading cannot go
        D.move_field(spec, q["fid"], -1, JOURNAL)
        D.retire_field(spec, q["fid"])
        assert q["legacy"] is True and q["q"] not in [x["q"] for x in D.active(spec)]
        D.restore_field(spec, q["fid"])
        assert "legacy" not in q
        name = D.add_category(spec, RESEARCH, "Technical reports")
        assert [x["q"] for x in D.active(spec) if name in (x.get("cats") or [])] == ["Title", "Date", "Description"]      # a new category starts with the three essentials
        D.rename_category(spec, "Technical reports", "Technical notes")
        assert "Technical notes" in spec["categories"] and spec["category_aliases"]["Technical reports"] == "Technical notes"
        D.delete_category(spec, "Technical notes")
        assert "Technical notes" not in spec["categories"] and "Technical notes" in spec["retired_categories"]
        with pytest.raises(Exception):
            for n in list(spec["categories"]):
                D.delete_category(spec, n)                                                        # the last category cannot be deleted


def test_publishing_checks_the_draft_and_an_earlier_version_can_be_restored(world):
    with db() as c:
        spec = D.get_draft(c, RESEARCH, "ADMIN")
        spec["categories"].append("Broken")
        D.save_draft(c, RESEARCH, spec, "ADMIN")
        with pytest.raises(Exception) as e:
            D.publish(c, RESEARCH, "ADMIN")
        assert "heading" in str(e.value.detail)
        D.discard_draft(c, RESEARCH, "ADMIN")
        D.apply_op(c, RESEARCH, "add_field", {"label": "Reviewer note", "type": "text", "categories": [JOURNAL]}, "ADMIN")
        D.publish(c, RESEARCH, "ADMIN")
        D.restore(c, RESEARCH, 1, "ADMIN")
        D.publish(c, RESEARCH, "ADMIN", "back to the original")
    assert "Reviewer note" not in [f["q"] for f in entry.form_for(RESEARCH, JOURNAL)["fields"]]


def test_sections_can_be_added_and_a_category_can_move_to_one(world):
    with db() as c:
        sec = D.sections_apply(c, "add", {"name": "Innovation"}, "ADMIN")["sections"][-1]
        assert sec["name"] == "Innovation" and sec["section_id"] == "sec_innovation"
        D.apply_op(c, RESEARCH, "category_meta", {"name": "Patents & Intellectual Property", "section_id": "sec_innovation"}, "ADMIN")
        D.publish(c, RESEARCH, "ADMIN")
        with pytest.raises(Exception):
            D.sections_apply(c, "delete", {"section_id": "sec_innovation"}, "ADMIN")               # a section in use cannot be deleted
    assert ingest.specs()["sections"]["sections"][-1]["name"] == "Innovation"                       # visible once committed


def test_renamed_category_and_field_still_read_old_responses(world):
    old_row = {"Timestamp": "2026-10-01 10:00:00", "Email Address": "emp001@x.edu", "Research Subcategory": JOURNAL, "Research Paper / Article Title": "Old paper", "Journal Name": "J1",
               "Author Names and Affiliations": "EMP001", "Publication Date": "2026-09-01"}
    with db() as c:
        D.apply_op(c, RESEARCH, "rename_category", {"name": JOURNAL, "new_name": "Journal articles"}, "ADMIN")
        D.apply_op(c, RESEARCH, "update_field", {"fid": next(f["fid"] for f in D.editor_view(c, RESEARCH)["fields"] if f["label"] == "Journal Name"), "changes": {"label": "Name of the journal"}}, "ADMIN")
        D.publish(c, RESEARCH, "ADMIN")
    with db() as c:                                                                                 # after the publish has committed
        res = ingest.ingest_row(c, RESEARCH, old_row)
    assert res["status"] == "inserted"
    with db() as c:
        assert [tuple(r) for r in c.execute("SELECT s.category, s.title, r.venue_publisher FROM form_submissions s JOIN research_outputs r USING (submission_id)")] == [("Journal articles", "Old paper", "J1")]


# ------------------------------------------------------------------------------------------------ the entry screen and submitting
def test_the_entry_screen_asks_only_what_a_person_should_type(world):
    cat = {c["name"]: c for f in entry.catalog(None) for c in f["categories"]}
    assert cat[JOURNAL]["name"] == JOURNAL and "description" in cat[JOURNAL] and JOURNAL.lower() in cat[JOURNAL]["keywords"]      # a card is titled by its category
    form = entry.form_for(RESEARCH, JOURNAL)
    labels = [f["q"] for f in form["fields"]]
    assert "Research Paper / Article Title" in labels and "Submitting Faculty (Select your name)" not in labels            # the person is known from the sign-in
    assert "Is this a Landmark / Milestone Achievement?" not in labels and "Research Subcategory" not in labels
    assert next(f for f in form["fields"] if f["q"].endswith("(up to 4)"))["type"] == "photo"
    assert next(f for f in form["fields"] if f["q"] == "Publication Date")["type"] == "date"


def values_for(form, **by_label):
    by = {f["q"]: f["fid"] for f in form["fields"]}
    return {by[k.replace("_", " ")] if k.replace("_", " ") in by else by[k]: v for k, v in by_label.items()}


def test_submitting_joins_the_approval_queue_and_approval_writes_the_record(world):
    form = entry.form_for(RESEARCH, JOURNAL)
    vals = {f["fid"]: "" for f in form["fields"]}
    by = {f["q"]: f["fid"] for f in form["fields"]}
    vals.update({by["Research Paper / Article Title"]: "Deep Models", by["Journal Name"]: "IEEE Access", by["Author Names and Affiliations"]: "EMP001 - Dr. Asha Rao",
                 by["Publication Date"]: "2026-09-15"})
    assert "Permission to Publish this Submission" not in by and "Accuracy and Authorization Confirmation" not in by      # no consent is asked
    me = user("EMP001")
    with db() as c:
        res = entry.submit(c, me, RESEARCH, JOURNAL, vals)
        row = c.execute("SELECT status, title, category, submitter_emp_id, event_date FROM staged_items WHERE item_id = ?", (res["item_id"],)).fetchone()
        assert tuple(row) == ("PENDING", "Deep Models", JOURNAL, "EMP001", "2026-09-15")
        assert c.execute("SELECT COUNT(*) FROM form_submissions").fetchone()[0] == 0              # nothing is live before approval
        service.approve(c, user("EMP002"), res["item_id"])
        assert [tuple(r) for r in c.execute("SELECT s.title, s.submitter_emp_id, r.venue_publisher, r.current_status FROM form_submissions s JOIN research_outputs r USING (submission_id)")] == [
            ("Deep Models", "EMP001", "IEEE Access", "Published")]


def test_submitting_checks_required_fields_dates_and_choices(world):
    form = entry.form_for(RESEARCH, JOURNAL)
    by = {f["q"]: f["fid"] for f in form["fields"]}
    me = user("EMP001")
    with db() as c:
        with pytest.raises(Exception) as e:
            entry.submit(c, me, RESEARCH, JOURNAL, {by["Research Paper / Article Title"]: "x"})
        assert "Please fill in" in str(e.value.detail) and "Journal Name" in str(e.value.detail)
        full = {by["Research Paper / Article Title"]: "x", by["Journal Name"]: "J", by["Author Names and Affiliations"]: "A", by["Publication Date"]: "next week"}
        with pytest.raises(Exception) as e:
            entry.submit(c, me, RESEARCH, JOURNAL, full)
        assert "date" in str(e.value.detail)
        full[by["Publication Date"]] = "2026-09-15"
        full[by["Quartile"]] = "Q9"
        with pytest.raises(Exception) as e:
            entry.submit(c, me, RESEARCH, JOURNAL, full)
        assert "listed options" in str(e.value.detail)
        with pytest.raises(Exception) as e:
            entry.submit(c, me, RESEARCH, "No such category", full)
        assert e.value.status_code == 404


def test_drafts_are_private_and_deleted_when_submitted(world):
    a, b = user("EMP001"), user("EMP002")
    with db() as c:
        entry.save_draft(c, a, "d1", RESEARCH, JOURNAL, {"x": "half done"})
        assert [d["draft_id"] for d in entry.list_drafts(c, a)] == ["d1"] and entry.list_drafts(c, b) == []
        with pytest.raises(Exception):
            entry.get_draft(c, b, "d1")
        entry.save_draft(c, b, "d1", RESEARCH, JOURNAL, {"x": "someone else's"})                   # cannot overwrite another person's draft
        assert entry.get_draft(c, a, "d1")["values"] == {"x": "half done"}


def test_people_look_ups(world):
    with db() as c:
        assert [f["emp_id"] for f in entry.find_faculty(c, "asha")] == ["EMP001"]
        assert entry.find_students(c, "21IT0")[0]["name"] == "Kavin M"
        assert [(r["roll_no"], r["found"]) for r in entry.check_rolls(c, "21it001\n99IT999")] == [("21IT001", True), ("99IT999", False)]


# ------------------------------------------------------------------------------------------------ photos
def test_a_big_photo_is_shrunk_and_stored_in_the_database_apart_from_the_listing_row(world):
    raw = jpeg()
    assert len(raw) > 1_000_000
    info = media.save_upload("EMP001", "IMG_0001.jpg", raw)
    assert max(info["width"], info["height"]) == media.MAX_SIDE and info["bytes"] < len(raw) / 2 and info["ref"] == f"media://{info['media_id']}"
    data, thumb = media.read(info["media_id"]), media.read(info["media_id"], thumb=True)
    assert len(data) == info["bytes"] and len(thumb) < 60_000 and Image.open(io.BytesIO(data)).format == "JPEG"
    with db() as c:
        cols = [r[1] for r in c.execute("PRAGMA table_info(media_files)")]
        assert not any(x in ("data", "thumb", "blob") for x in cols)                                # the metadata row never carries picture data
    assert os.path.getsize(str(world / "master.db")) < len(raw)                                      # the stored picture is the small one, not the original
    assert media.save_upload("EMP001", "again.jpg", raw)["media_id"] == info["media_id"]           # the same photo twice is stored once
    path = media.resolve(info["ref"])                                                                # the newsletter generator gets a file
    assert path and open(path, "rb").read() == data


def test_bad_uploads_are_refused(world):
    for content, code in ((b"", 400), (b"not a picture at all", 400), (b"x" * (media.MAX_UPLOAD + 1), 413)):
        with pytest.raises(Exception) as e:
            media.save_upload("EMP001", "f.jpg", content)
        assert e.value.status_code == code
    assert media.save_upload("EMP001", "t.png", (lambda b: (Image.new("RGBA", (50, 40), (255, 0, 0, 120)).save(b, "PNG"), b.getvalue())[1])(io.BytesIO()))["width"] == 50     # a PNG with transparency works


# ------------------------------------------------------------------------------------------------ the web API
def test_the_api_serves_entry_photos_and_the_admin_editor_with_the_right_access(world):
    fac, admin = token("EMP001"), token("ADMIN")
    cat = client.get("/api/entry/catalog", headers=fac).json()
    assert [f["form_id"] for f in cat["forms"]]== ["form_research", "form_faculty", "form_departmental", "form_industry", "form_student"]
    up = client.post("/api/media", files={"file": ("p.jpg", jpeg(1000, 700), "image/jpeg")}, headers=fac)
    assert up.status_code == 200
    got = client.get(up.json()["url"])                                                          # <img> tags carry no sign-in: the address itself is the key
    assert got.status_code == 200 and got.headers["content-type"] == "image/jpeg"
    assert client.get(f"/api/media/{up.json()['media_id']}/wrongtoken").status_code == 404
    assert client.post("/api/defs/forms/form_research/ops", json={"op": "add_field", "label": "X"}, headers=fac).status_code == 403          # faculty cannot edit forms
    r = client.post("/api/defs/forms/form_research/ops", json={"op": "add_field", "label": "Patent office note", "categories": ["Patents & Intellectual Property"]}, headers=admin)
    assert r.status_code == 200 and r.json()["has_draft"]
    assert client.post("/api/defs/forms/form_research/publish", json={"note": "x"}, headers=admin).json()["version"] == 2
    assert "Patent office note" in [f["q"] for f in client.get("/api/entry/form", params={"form_id": "form_research", "category": "Patents & Intellectual Property"}, headers=fac).json()["fields"]]
    assert client.get("/api/defs/forms", headers=fac).status_code == 403


# ------------------------------------------------------------------------------------------------ a student's placement record
def student_token():
    from backend.master.auth import hash_password
    with db() as c:
        c.execute("INSERT OR REPLACE INTO users (user_id, user_type, password_hash, must_change) VALUES ('21IT001', 'STUDENT', ?, 0)", (hash_password(PASS),))
        c.execute("UPDATE classes SET tutor_id = 'EMP001' WHERE class_id = 1")
    r = client.post("/api/auth/login", json={"id": "21IT001", "password": PASS})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


def test_a_student_sends_offers_and_experiences_and_the_class_tutor_approves_them(world):
    from datetime import date
    from database.master_db import ay_for
    stu = student_token()
    d = client.get("/api/diary/my-record", headers=stu).json()
    assert d["record"] is None and d["roll_no"] == "21IT001" and len(d["sections"]) == 5
    body = {"offers": [{"company": "Acme Technologies", "offer_type": "FTE", "package_lpa": "8.5", "job_role": "Engineer", "offer_status": "Accepted", "difficulty": "Medium",
                        "result": "Selected", "interview_experience": "Friendly panel"}, {}]}                  # no year, no opt-in, no consent: none of that is the student's to answer
    r = client.post("/api/diary/my-record", json=body, headers=stu)
    assert r.status_code == 200 and r.json() == {"status": "PENDING", "offers": 1}, r.text
    with db() as c:
        assert [tuple(x) for x in c.execute("SELECT kind, status, roll_no, ay_id, class_id FROM staged_items")] == [("PLACEMENT", "PENDING", "21IT001", ay_for(date.today()), 1)]
        assert c.execute("SELECT COUNT(*) FROM placement_offers").fetchone()[0] == 0                 # nothing is live before the tutor approves
    mine = client.get("/api/diary/my-record", headers=stu).json()["record"]
    assert mine["status"] == "PENDING" and mine["offers"][0]["company"] == "Acme Technologies"
    tutor = token("EMP001")
    item = client.get("/api/review/items?scope=review", headers=tutor).json()["items"][0]["item_id"]
    assert client.post(f"/api/review/items/{item}/approve", json={}, headers=tutor).status_code == 200
    with db() as c:
        assert [tuple(x) for x in c.execute("SELECT o.roll_no, g.name, o.package_lpa, o.offer_status FROM placement_offers o JOIN organizations g USING (org_id)")] == [("21IT001", "Acme Technologies", 8.5, "Accepted")]
        assert c.execute("SELECT is_shareable FROM interview_experiences").fetchone()[0] == 1       # always shown to juniors (without the name)
    r = client.post("/api/diary/my-record", json={"offers": [{**body["offers"][0], "package_lpa": "9"}]}, headers=stu)       # a change needs approval again
    assert r.json()["status"] == "PENDING"


def test_a_placement_record_is_checked_and_only_students_may_send_one(world):
    stu, fac = student_token(), token("EMP001")
    bad = lambda **kw: client.post("/api/diary/my-record", json=kw, headers=stu)
    assert bad(offers=[]).status_code == 400 and bad(offers=[{}]).status_code == 400                                            # at least one offer
    assert bad(offers=[{"company": "Acme"}]).status_code == 400                                                                  # an offer needs its type
    assert bad(offers=[{"company": "Acme", "offer_type": "Nonsense"}]).status_code == 400
    assert bad(offers=[{"company": "Acme", "offer_type": "FTE", "package_lpa": "lots"}]).status_code == 400
    assert bad(offers=[{"company": "Acme", "offer_type": "FTE"}]).status_code == 200
    assert client.post("/api/diary/my-record", json={"offers": []}, headers=fac).status_code == 403
    assert client.get("/api/diary/my-record", headers=fac).status_code == 403


def test_the_class_tutor_records_who_opted_in_or_out_and_the_student_does_not_overwrite_it(world):
    stu, tutor = student_token(), token("EMP001")
    got = client.get("/api/entry/placement-preferences", params={"ay_id": "2026-27"}, headers=tutor).json()
    assert got["class_code"] and [s["roll_no"] for s in got["students"]] == ["21IT001"] and got["students"][0]["opt_status"] is None and "Higher Studies" in got["reasons"]
    r = client.put("/api/entry/placement-preferences", json={"ay_id": "2026-27", "rows": [{"roll_no": "21IT001", "opt_status": "Opted Out", "opt_out_reason": "Higher Studies"}]}, headers=tutor)
    assert r.json() == {"saved": 1}
    with db() as c:
        assert [tuple(x) for x in c.execute("SELECT roll_no, ay_id, opt_status, opt_out_reason FROM placement_profiles")] == [("21IT001", "2026-27", "OPTED_OUT", "Higher Studies")]
    again = client.get("/api/entry/placement-preferences", params={"ay_id": "2026-27"}, headers=tutor).json()["students"][0]
    assert again["opt_status"] == "OPTED_OUT" and again["opt_out_reason"] == "Higher Studies"
    assert client.post("/api/diary/my-record", json={"offers": [{"company": "Acme", "offer_type": "FTE"}]}, headers=stu).status_code == 200
    with db() as c:
        row = json.loads(c.execute("SELECT answers_json FROM staged_items").fetchone()[0])[0]
    assert row["Placement Academic Year"] == "2026-27" and row["Placement Preference"] == "Opted Out"                        # what the tutor recorded is kept
    assert client.put("/api/entry/placement-preferences", json={"ay_id": "bad", "rows": []}, headers=tutor).status_code == 400
    assert client.get("/api/entry/placement-preferences", params={"ay_id": "2026-27"}, headers=token("EMP002")).status_code == 403     # not a class tutor
    with db() as c:
        c.execute("INSERT INTO students (roll_no, full_name, programme, class_id) VALUES ('21IT909', 'Other Class', 'UG', 2)")
    out = client.put("/api/entry/placement-preferences", json={"ay_id": "2026-27", "rows": [{"roll_no": "21IT909", "opt_status": "Opted In"}]}, headers=tutor)
    assert out.status_code == 403                                                                                                 # a tutor records only their own class
