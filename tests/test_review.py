"""Approval workflow: responses wait in a staging area, only approved ones become live; who decides what; the four decisions;
return-to-faculty and resubmission."""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient  # noqa: E402

from backend.app import app  # noqa: E402
from backend.master import blocks, ingest, placements  # noqa: E402
from backend.master.auth import set_staff_password  # noqa: E402
from backend.review import service  # noqa: E402
from database import db_manager  # noqa: E402
from database.master_db import db, init_master_db  # noqa: E402

pytestmark = pytest.mark.usefixtures("previous_forms")            # engine tests: see conftest.py

PASS = "Review-Test-1"
client = TestClient(app)


def form_row(form_id, **by_key):
    spec = ingest.specs()["forms"][form_id]
    heads = {q["key"]: q["q"] for q in spec["questions"] if q.get("key") and q.get("legacy")}          # the earlier wording ...
    heads.update({q["key"]: q["q"] for q in blocks.questions_for(spec, by_key.get("category"), legacy=False) if q.get("key")})        # ... overridden by the current form's questions of this category
    row = {"Timestamp": by_key.pop("_ts", "2025-10-01 10:00:00"), "Email Address": by_key.pop("_email", "x@x.edu")}
    row.update({heads[k]: v for k, v in by_key.items()})
    return row


def plac_row(**by_key):
    heads = {q["key"]: q["q"] for q in placements.questions()}
    return {heads[k]: v for k, v in by_key.items()}


def research(title="Paper One", **kw):
    k = dict(_submitter="EMP003", category="Journal Publications", title=title, current_status="Published", _contributors="EMP003\n21IT001", venue_publisher="IEEE Access",
             output_date="2025-08-15", indexing="Scopus", quartile="Q1", abstract="About it.", _ts=kw.pop("_ts", "2025-10-01 10:00:00"))
    k.update(kw)
    return form_row("form_research", **k)


@pytest.fixture()
def world(monkeypatch, tmp_path):
    monkeypatch.setenv("MASTER_DB_PATH", str(tmp_path / "master.db"))
    monkeypatch.setenv("MASTER_ADMIN_PASSWORD", PASS)
    monkeypatch.setenv("MASTER_SECRET", "review-secret")
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.setattr(db_manager, "DB_PATH", str(tmp_path / "news.db"))
    db_manager.init_db()
    init_master_db()
    with db() as c:
        for emp, name in (("EMP001", "Dr. Tutor One"), ("EMP002", "Dr. Head"), ("EMP003", "Dr. Plain Faculty"), ("EMP004", "Dr. Tutor Two"), ("EMP005", "Dr. Other Faculty")):
            c.execute("INSERT INTO faculty (emp_id, full_name, email, designation) VALUES (?,?,?,?)", (emp, name, f"{emp.lower()}@x.edu", "Professor"))
            set_staff_password(c, emp, PASS)
        c.execute("INSERT INTO role_assignments (emp_id, role) VALUES ('EMP002', 'HOD')")
        c.execute("UPDATE classes SET tutor_id = 'EMP001' WHERE class_id = 1")
        c.execute("UPDATE classes SET tutor_id = 'EMP004' WHERE class_id = 2")
        for roll, name, cid in (("21IT001", "Kavin M", 1), ("21IT002", "Divya S", 1), ("21IT101", "Other Class", 2), ("21IT201", "No Tutor Class", 3)):
            c.execute("INSERT INTO students (roll_no, full_name, programme, class_id) VALUES (?, ?, 'UG', ?)", (roll, name, cid))
            c.execute("INSERT INTO student_class_history (roll_no, class_id, from_date, action) VALUES (?, ?, '2025-06-01', 'Added')", (roll, cid))
    return None


def sign_in(uid):
    r = client.post("/api/auth/login", json={"id": uid, "password": PASS})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


def stage(form_id, rows):
    with db() as c:
        return service.stage_rows(c, form_id, rows)


def item_ids(status="PENDING", form_id=None):
    with db() as c:
        sql, a = "SELECT item_id FROM staged_items WHERE status = ?" + (" AND form_id = ?" if form_id else "") + " ORDER BY item_id", [status] + ([form_id] if form_id else [])
        return [r[0] for r in c.execute(sql, a)]


def live(sql, *a):
    with db() as c:
        return [tuple(r) for r in c.execute(sql, a).fetchall()]


def as_user(uid, kind="STAFF"):
    from backend.master.auth import load_user
    with db() as c:
        return load_user(c, uid, kind)


# ---------------------------------------------------------------- 1. nothing is live until approved
def test_waiting_entries_are_never_live_before_approval(world):
    res = stage("form_research", [research("Paper One"), research("Paper Two", _ts="2025-10-02 09:00:00")])
    assert res["new"] == 2
    assert live("SELECT COUNT(*) FROM form_submissions")[0][0] == 0                       # staged, not live
    admin = sign_in("ADMIN")
    assert client.get("/api/master/submissions", headers=admin).json()["total"] == 0
    assert client.get("/api/master/works/catalog", headers=admin).json()["total"] == 0
    assert client.get("/api/master/analytics", headers=admin).json()["department"]["submissions_by_form"] == []
    it = client.get("/api/review/items?scope=review", headers=admin).json()
    assert it["total"] == 2 and it["items"][0]["status"] == "PENDING" and it["items"][0]["submitter"] == "Dr. Plain Faculty"
    again = stage("form_research", [research("Paper One"), research("Paper Two", _ts="2025-10-02 09:00:00")])
    assert again == {"new": 0, "updated": 0, "already_in_system": 0, "unchanged": 2}       # queuing them again adds nothing


def test_an_entry_already_in_the_records_is_recorded_as_approved_not_asked_again(world):
    row = research("Already There")
    with db() as c:
        assert ingest.ingest_row(c, "form_research", row)["status"] == "inserted"
    assert stage("form_research", [row])["already_in_system"] == 1
    assert item_ids("PENDING") == [] and len(item_ids("APPROVED")) == 1
    assert live("SELECT COUNT(*) FROM form_submissions")[0][0] == 1                       # not duplicated


# ---------------------------------------------------------------- 2. approve, and edit & approve
def test_approve_makes_it_live_once(world):
    stage("form_research", [research("Paper One")])
    admin = sign_in("ADMIN")
    iid = item_ids()[0]
    assert client.post(f"/api/review/items/{iid}/approve", json={}, headers=admin).json()["status"] == "APPROVED"
    assert live("SELECT title, category FROM form_submissions") == [("Paper One", "Journal Publications")]
    assert client.get("/api/master/works/catalog", headers=admin).json()["total"] == 1
    assert client.post(f"/api/review/items/{iid}/approve", json={}, headers=admin).status_code == 409    # already decided
    assert [e["action"] for e in client.get(f"/api/review/items/{iid}", headers=admin).json()["timeline"]] == ["pulled", "approved"]


def test_edit_and_approve_saves_the_edit_keeps_the_original_and_logs_what_changed(world):
    stage("form_research", [research("Papper One with a typo", indexing="Scopus")])
    hod = sign_in("EMP002")
    iid = item_ids()[0]
    title_q = next(q["q"] for q in ingest.specs()["forms"]["form_research"]["questions"] if q.get("key") == "title")
    idx_q = next(q["q"] for q in ingest.specs()["forms"]["form_research"]["questions"] if q.get("key") == "indexing")
    r = client.post(f"/api/review/items/{iid}/approve", json={"answers": [{title_q: "Paper One, corrected", idx_q: "Web of Science"}]}, headers=hod)
    assert r.status_code == 200 and r.json()["edited"] and r.json()["changes"] == 2
    assert live("SELECT title FROM form_submissions") == [("Paper One, corrected",)]
    assert live("SELECT indexing FROM research_outputs") == [("Web of Science",)]
    with db() as c:
        row = c.execute("SELECT answers_json, original_json FROM staged_items WHERE item_id = ?", (iid,)).fetchone()
    import json
    assert json.loads(row[1])[0][title_q] == "Papper One with a typo"                    # the sheet's version is never altered
    assert len(json.loads(row[0])[0]) == len(json.loads(row[1])[0])                       # edited in place: no duplicate columns appeared
    detail = client.get(f"/api/review/items/{iid}", headers=hod).json()
    edited = next(e for e in detail["timeline"] if e["action"] == "edited")
    assert {c["field"] for c in edited["detail"]} == {title_q, idx_q} and any(e["action"] == "approved_edited" for e in detail["timeline"])
    changed = [f["q"] for f in detail["rows"][0]["fields"] if f.get("changed")]
    assert set(changed) == {title_q, idx_q}                                                # the editor can show "was: ..." for these


def test_an_item_with_a_blocking_problem_cannot_be_approved_until_it_is_fixed(world):
    stage("form_research", [research(title="")])
    admin = sign_in("ADMIN")
    iid = item_ids()[0]
    assert client.get("/api/review/items?scope=review", headers=admin).json()["items"][0]["blockers"]
    r = client.post(f"/api/review/items/{iid}/approve", json={}, headers=admin)
    assert r.status_code == 400 and "title" in r.json()["detail"].lower()
    assert live("SELECT COUNT(*) FROM form_submissions")[0][0] == 0
    title_q = next(q["q"] for q in ingest.specs()["forms"]["form_research"]["questions"] if q.get("key") == "title")
    assert client.post(f"/api/review/items/{iid}/approve", json={"answers": [{title_q: "Now it has a title"}]}, headers=admin).status_code == 200
    assert live("SELECT title FROM form_submissions") == [("Now it has a title",)]


# ---------------------------------------------------------------- 3. the two rejections and the faculty loop
def test_reject_without_a_reason_closes_it_and_it_can_be_reopened(world):
    stage("form_research", [research()])
    admin = sign_in("ADMIN")
    iid = item_ids()[0]
    assert client.post(f"/api/review/items/{iid}/reject", json={}, headers=admin).json()["status"] == "REJECTED"
    assert live("SELECT COUNT(*) FROM form_submissions")[0][0] == 0 and item_ids("REJECTED") == [iid]
    assert client.post(f"/api/review/items/{iid}/reopen", headers=admin).json()["status"] == "PENDING"


def test_reject_with_a_reason_goes_to_the_chosen_faculty_who_corrects_and_resubmits(world):
    stage("form_research", [research("Needs fixing")])
    hod, faculty, other = sign_in("EMP002"), sign_in("EMP003"), sign_in("EMP005")
    iid = item_ids()[0]
    no_target = client.post(f"/api/review/items/{iid}/reject", json={"reason": "Wrong indexing"}, headers=hod)
    assert no_target.status_code == 400 and "faculty" in no_target.json()["detail"].lower()          # the approver must choose who gets it
    detail = client.get(f"/api/review/items/{iid}", headers=hod).json()
    assert detail["suggested_send_to"] == "EMP003" and any(f["emp_id"] == "EMP005" for f in detail["faculty"])
    r = client.post(f"/api/review/items/{iid}/reject", json={"reason": "Wrong indexing: please check", "send_to": "EMP005"}, headers=hod)   # the approver picked someone else
    assert r.json() == {"status": "RETURNED", "assigned_to": "Dr. Other Faculty"}
    assert live("SELECT COUNT(*) FROM form_submissions")[0][0] == 0
    # it shows up for the faculty member it was sent to, and for nobody else
    mine = client.get("/api/review/items?scope=returned", headers=other).json()
    assert mine["total"] == 1 and mine["items"][0]["reason"] == "Wrong indexing: please check"
    assert client.get("/api/review/items?scope=returned", headers=faculty).json()["total"] == 0
    assert client.get("/api/review/summary", headers=other).json()["returned_to_me"] == 1
    idx_q = next(q["q"] for q in ingest.specs()["forms"]["form_research"]["questions"] if q.get("key") == "indexing")
    assert client.post(f"/api/review/items/{iid}/resubmit", json={"answers": [{idx_q: "UGC-CARE"}]}, headers=faculty).status_code == 403   # not theirs
    assert client.post(f"/api/review/items/{iid}/resubmit", json={"answers": [{}]}, headers=other).status_code == 400                # nothing changed, no note
    ok = client.post(f"/api/review/items/{iid}/resubmit", json={"answers": [{idx_q: "UGC-CARE"}]}, headers=other)
    assert ok.status_code == 200 and ok.json()["status"] == "PENDING"
    assert client.get("/api/review/items?scope=returned", headers=other).json()["total"] == 0
    assert client.get("/api/review/items?scope=review", headers=hod).json()["total"] == 1                                              # back in the approver's queue
    assert client.post(f"/api/review/items/{iid}/approve", json={}, headers=hod).status_code == 200
    assert live("SELECT indexing FROM research_outputs") == [("UGC-CARE",)]
    actions = [e["action"] for e in client.get(f"/api/review/items/{iid}", headers=hod).json()["timeline"]]
    assert actions == ["pulled", "returned", "edited", "resubmitted", "approved"]


def test_a_note_alone_is_enough_to_resubmit_when_the_data_was_right(world):
    stage("form_research", [research()])
    hod, faculty = sign_in("EMP002"), sign_in("EMP003")
    iid = item_ids()[0]
    client.post(f"/api/review/items/{iid}/reject", json={"reason": "Is the DOI right?", "send_to": "EMP003"}, headers=hod)
    r = client.post(f"/api/review/items/{iid}/resubmit", json={"answers": [{}], "note": "Checked: the DOI is correct"}, headers=faculty)
    assert r.status_code == 200
    assert client.get(f"/api/review/items/{iid}", headers=hod).json()["timeline"][-1]["note"] == "Checked: the DOI is correct"


# ---------------------------------------------------------------- 4. who decides what
def test_forms_are_decided_by_admin_or_hod_only(world):
    stage("form_research", [research()])
    iid = item_ids()[0]
    for uid in ("EMP001", "EMP003", "EMP004"):                                              # a tutor and ordinary faculty
        h = sign_in(uid)
        assert client.post(f"/api/review/items/{iid}/approve", json={}, headers=h).status_code == 403, uid
        assert client.post(f"/api/review/items/{iid}/reject", json={}, headers=h).status_code == 403, uid
        assert client.get("/api/review/items?scope=review", headers=h).json()["total"] == 0, uid
    assert client.post(f"/api/review/items/{iid}/approve", json={}, headers=sign_in("EMP002")).status_code == 200      # the HoD can


def test_placements_are_approved_by_the_class_tutor(world):
    stage(service.PLACEMENT, [plac_row(roll_no="21IT001", ay_id="2025-26", opt_status="Opted In", company="Acme Technologies", offer_type="FTE", package_lpa="8.5", job_role="SDE"),
                              plac_row(roll_no="21IT101", ay_id="2025-26", opt_status="Opted Out", opt_out_reason="Higher studies")])
    assert live("SELECT COUNT(*) FROM placement_offers")[0][0] == 0
    ids = {i["roll_no"]: i for i in client.get("/api/review/items?scope=review", headers=sign_in("EMP001")).json()["items"]}
    assert set(ids) == {"21IT001"}                                                          # EMP001 sees only their own class's student
    own, theirs = ids["21IT001"]["item_id"], item_ids()[1]
    assert client.post(f"/api/review/items/{theirs}/approve", json={}, headers=sign_in("EMP001")).status_code == 403   # another class's student
    assert client.post(f"/api/review/items/{own}/approve", json={}, headers=sign_in("EMP002")).status_code == 403      # even the HoD does not approve placements
    assert client.post(f"/api/review/items/{own}/approve", json={}, headers=sign_in("ADMIN")).status_code == 403       # nor the Admin, while the class has a tutor
    assert client.post(f"/api/review/items/{own}/approve", json={}, headers=sign_in("EMP001")).status_code == 200
    assert live("SELECT roll_no, package_lpa FROM placement_offers") == [("21IT001", 8.5)]
    assert client.post(f"/api/review/items/{theirs}/approve", json={}, headers=sign_in("EMP004")).status_code == 200
    assert live("SELECT opt_status, opt_out_reason FROM placement_profiles WHERE roll_no = '21IT101'") == [("OPTED_OUT", "Higher studies")]


def test_the_admin_steps_in_only_when_a_class_has_no_tutor(world):
    stage(service.PLACEMENT, [plac_row(roll_no="21IT201", ay_id="2025-26", opt_status="Opted In", company="Beta Soft", offer_type="FTE", package_lpa="4.5")])
    iid = item_ids()[0]
    detail = client.get(f"/api/review/items/{iid}", headers=sign_in("ADMIN")).json()
    assert any("no tutor" in w for w in detail["warnings"]) and detail["permissions"]["decide"]
    assert client.post(f"/api/review/items/{iid}/approve", json={}, headers=sign_in("ADMIN")).status_code == 200


def test_a_placement_approval_replaces_what_was_there_and_unknown_students_are_blocked(world):
    with db() as c:
        placements.apply_rows(c, as_user("ADMIN"), {"21IT001": [{"roll_no": "21IT001", "ay_id": "2025-26", "company": "Old Corp", "offer_type": "FTE", "package_lpa": "3"}]}, "2025-26")
    stage(service.PLACEMENT, [plac_row(roll_no="21IT001", ay_id="2025-26", company="New Corp", offer_type="FTE", package_lpa="9"),
                              plac_row(roll_no="99XX999", ay_id="2025-26", company="Ghost Co", offer_type="FTE", package_lpa="9")])
    tutor, admin = sign_in("EMP001"), sign_in("ADMIN")
    ids = item_ids()
    assert live("SELECT g.name FROM placement_offers o JOIN organizations g USING (org_id)") == [("Old Corp",)]       # untouched until approved
    warn = client.get(f"/api/review/items/{ids[0]}", headers=tutor).json()["warnings"]
    assert any("replaces" in w for w in warn)
    assert client.post(f"/api/review/items/{ids[0]}/approve", json={}, headers=tutor).status_code == 200
    assert live("SELECT g.name, o.package_lpa FROM placement_offers o JOIN organizations g USING (org_id)") == [("New Corp", 9.0)]
    ghost = client.get(f"/api/review/items/{ids[1]}", headers=admin).json()
    assert any("not in the student list" in b for b in ghost["blockers"])
    assert client.post(f"/api/review/items/{ids[1]}/approve", json={}, headers=admin).status_code == 400


def test_more_rows_for_the_same_student_reopen_a_decided_placement_item(world):
    r1 = plac_row(roll_no="21IT001", ay_id="2025-26", company="One Corp", offer_type="FTE", package_lpa="6")
    stage(service.PLACEMENT, [r1])
    tutor = sign_in("EMP001")
    client.post(f"/api/review/items/{item_ids()[0]}/approve", json={}, headers=tutor)
    r2 = plac_row(roll_no="21IT001", ay_id="2025-26", company="Two Corp", offer_type="INTERN", stipend_per_month="20000")
    assert stage(service.PLACEMENT, [r1, r2]) == {"new": 0, "updated": 1, "already_in_system": 0, "unchanged": 0, "skipped": 0}     # same student, one item, two offers now
    assert len(item_ids("PENDING")) == 1 and live("SELECT COUNT(*) FROM placement_offers")[0][0] == 1                                 # live data still the old version
    assert client.post(f"/api/review/items/{item_ids()[0]}/approve", json={}, headers=tutor).status_code == 200
    assert live("SELECT COUNT(*) FROM placement_offers")[0][0] == 2


# ---------------------------------------------------------------- 5. bulk approve, revoke, preview, lists
def test_bulk_approve_takes_the_clean_ones_and_leaves_the_flagged_for_a_human(world):
    stage("form_research", [research("Clean A"), research("Clean B", _ts="2025-10-02 09:00:00"),
                            research("Has a stranger", _ts="2025-10-03 09:00:00", _contributors="EMP003\n99XX999")])
    admin = sign_in("ADMIN")
    flagged = client.get("/api/review/items?scope=review&flagged=true", headers=admin).json()
    assert flagged["total"] == 1 and flagged["items"][0]["title"] == "Has a stranger" and any("99XX999" in w for w in flagged["items"][0]["warnings"])
    r = client.post("/api/review/bulk-approve", json={"all_clean": True}, headers=admin).json()
    assert r["approved"] == 2 and live("SELECT COUNT(*) FROM form_submissions")[0][0] == 2
    assert [i["title"] for i in client.get("/api/review/items?scope=review", headers=admin).json()["items"]] == ["Has a stranger"]
    assert client.post("/api/review/bulk-approve", json={"ids": [item_ids()[0]]}, headers=admin).json()["approved"] == 1       # a human can still take the flagged one


def test_revoke_takes_an_approved_response_back_out_of_the_application(world):
    stage("form_research", [research("Approved by mistake")])
    admin = sign_in("ADMIN")
    iid = item_ids()[0]
    client.post(f"/api/review/items/{iid}/approve", json={}, headers=admin)
    assert live("SELECT COUNT(*) FROM research_contributors")[0][0] == 2
    assert client.post(f"/api/review/items/{iid}/revoke", headers=admin).json()["status"] == "PENDING"
    assert live("SELECT COUNT(*) FROM form_submissions")[0][0] == 0 and live("SELECT COUNT(*) FROM research_contributors")[0][0] == 0
    assert client.get("/api/master/works/catalog", headers=admin).json()["total"] == 0
    assert client.post(f"/api/review/items/{iid}/revoke", headers=admin).status_code == 409                                  # nothing left to revoke


def test_preview_says_who_the_ids_are_and_what_is_wrong_without_saving(world):
    admin = sign_in("ADMIN")
    row = research("Preview me", _contributors="EMP003\n21IT001\n99XX999")
    r = client.post("/api/review/preview", json={"form_id": "form_research", "answers": [row]}, headers=admin).json()
    authors = next(p for p in r["people"] if p["label"] == "Authors")
    assert [i["text"] for i in authors["items"]][:2] == ["Dr. Plain Faculty", "Kavin M"] and any("99XX999" in w for w in r["warnings"])
    assert live("SELECT COUNT(*) FROM form_submissions")[0][0] == 0 and live("SELECT COUNT(*) FROM organizations")[0][0] == 0   # a dry run: nothing saved


def test_lists_and_badges_per_role(world):
    stage("form_research", [research("A"), research("B", _ts="2025-10-02 09:00:00")])
    stage(service.PLACEMENT, [plac_row(roll_no="21IT001", ay_id="2025-26", opt_status="Opted In", company="Acme", offer_type="FTE", package_lpa="7")])
    counts = lambda uid: client.get("/api/review/summary", headers=sign_in(uid)).json()
    assert counts("ADMIN")["to_review"] == 2 and counts("EMP002")["to_review"] == 2        # the five forms
    assert counts("EMP001")["to_review"] == 1 and counts("EMP004")["to_review"] == 0       # a tutor: only their own students' placements
    assert counts("EMP003")["badge"] == 0
    mine = client.get("/api/review/items?scope=mine", headers=sign_in("EMP003")).json()
    assert mine["total"] == 2 and {i["status"] for i in mine["items"]} == {"PENDING"}      # a faculty member follows their own submissions
    assert client.get("/api/review/items?scope=review", headers=sign_in("EMP003")).json()["total"] == 0
    assert client.get("/api/review/items?scope=nonsense", headers=sign_in("ADMIN")).status_code == 400
    other = item_ids()[0]
    assert client.get(f"/api/review/items/{other}", headers=sign_in("EMP005")).status_code == 403                          # strangers cannot read it


