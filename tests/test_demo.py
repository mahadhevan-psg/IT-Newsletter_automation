"""Demo mode: a rich, invented department; safe shared logins; reset; and a hard refusal to touch real data."""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient  # noqa: E402

from backend.app import app  # noqa: E402
from backend.demo import seed  # noqa: E402
from backend.demo.mode import PASSWORD  # noqa: E402
from database import db_manager  # noqa: E402
from database.master_db import db, init_master_db  # noqa: E402

client = TestClient(app)


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    """One seeded demo for the whole module (seeding takes a while). Everything points at temporary files."""
    d = tmp_path_factory.mktemp("demo")
    mp = pytest.MonkeyPatch()
    mp.setenv("DEMO_MODE", "true")
    mp.setenv("MASTER_DB_PATH", str(d / "master.db"))
    mp.setenv("MASTER_SECRET", "demo-test-secret")
    mp.delenv("MASTER_ADMIN_PASSWORD", raising=False)
    mp.setattr(db_manager, "DB_PATH", str(d / "news.db"))
    from backend.services import front_matter_service as fms
    mp.setattr(fms, "CONFIG_FILE", str(d / "front.json"))
    db_manager.init_db()
    seed.start()
    yield d
    mp.undo()


def sign_in(uid, pw=PASSWORD):
    r = client.post("/api/auth/login", json={"id": uid, "password": pw})
    assert r.status_code == 200, (uid, r.text)
    return r.json()


def auth(login):
    return {"Authorization": f"Bearer {login['token']}"}


def q(sql, *args):
    with db() as c:
        return c.execute(sql, args).fetchall()


def test_the_demo_department_is_rich_enough_for_every_feature(demo):
    one = lambda sql: q(sql)[0][0]
    assert one("SELECT COUNT(*) FROM faculty WHERE emp_id != 'ADMIN'") == 16
    assert one("SELECT COUNT(*) FROM students WHERE status = 'Active'") >= 250 and one("SELECT COUNT(*) FROM students WHERE status = 'Graduated'") >= 50
    assert {r[0] for r in q("SELECT DISTINCT form_type FROM form_submissions")} == {"STUDENT", "RESEARCH", "FACULTY", "DEPARTMENT", "OUTREACH"}
    assert one("SELECT COUNT(*) FROM form_submissions") >= 300
    assert q("SELECT form_type, category, COUNT(*) FROM form_submissions GROUP BY 1, 2 HAVING COUNT(*) < 3") == []             # every kind of work has examples
    assert one("SELECT COUNT(*) FROM student_achievement_participants WHERE roll_no IS NULL") == 0                                 # every roll number resolved
    assert one("SELECT COUNT(*) FROM student_achievements WHERE entry_kind = 'PARTICIPATION'") > 5
    assert len({r[0] for r in q("SELECT DISTINCT ay_id FROM placement_offers")}) == 3                                              # the diary's three-year window
    assert one("SELECT COUNT(*) FROM interview_experiences WHERE is_shareable = 1") >= 15 and one("SELECT COUNT(*) FROM internship_experiences WHERE is_shareable = 1") >= 5
    assert one("SELECT COUNT(DISTINCT class_id) FROM classes WHERE tutor_id IS NOT NULL") == 10 and one("SELECT COUNT(*) FROM classes WHERE status = 'Completed'") == 2
    # MoUs: some active, some expiring soon, some expired (the dashboard's MoU table has something to say)
    states = {r[0] for r in q("SELECT CASE WHEN agreement_expiry < date('now') THEN 'Expired' WHEN agreement_expiry <= date('now','+90 day') THEN 'Soon' ELSE 'Active' END FROM outreach_activities WHERE agreement_expiry IS NOT NULL")}
    assert states == {"Expired", "Soon", "Active"}
    # the newsletter has entries, mostly approved, and front pages
    n = db_manager.get_connection()
    by = dict(n.execute("SELECT approval_status, COUNT(*) FROM canonical_entries GROUP BY 1").fetchall())
    assert by["Approved"] > 250 and by.get("Draft", 0) > 0 and sum(by.values()) >= 300
    import json
    assert "Venkatesan" in json.load(open(demo / "demo_front_matter.json"))["hod"]["name"]


def test_every_demo_login_works_and_sees_the_right_things(demo):
    info = client.get("/api/demo/info").json()
    assert info["enabled"] and info["password"] == PASSWORD
    roles = {a["role"]: a["id"] for a in info["accounts"]}
    assert set(roles) == {"Admin", "Head of Department", "Programme Coordinator (UG)", "Class tutor", "Faculty", "Student"}
    users = {}
    for role, uid in roles.items():
        login = sign_in(uid)
        assert login["user"]["must_change"] is False, role                                      # nobody is forced to change a shared password
        users[role] = login
    assert users["Admin"]["user"]["all_access"] and users["Head of Department"]["user"]["all_access"]
    pc = client.get("/api/master/classes", headers=auth(users["Programme Coordinator (UG)"])).json()
    assert {c["grp"] for c in pc} == {"G1", "G2"} and {c["programme"] for c in pc} == {"UG"}   # both groups, as asked
    tutor = users["Class tutor"]["user"]
    assert len(tutor["tutor_class_ids"]) == 1
    mine = client.get("/api/master/students?limit=500", headers=auth(users["Class tutor"])).json()
    assert 20 <= mine["total"] <= 30                                                            # exactly their own class
    assert client.get("/api/master/students", headers=auth(users["Faculty"])).json()["total"] == 0
    comps = client.get("/api/diary/companies", headers=auth(users["Student"])).json()
    assert len(comps["years"]) == 3 and len(comps["companies"]) >= 10


def test_every_screen_has_something_to_show(demo):
    admin = auth(sign_in("ADMIN"))
    cat = client.get("/api/master/works/catalog", headers=admin).json()
    empty = [t["label"] for g in cat["groups"] for t in g["types"] if t["count"] == 0]
    assert empty == [] and cat["total"] >= 300                                                  # every kind of work, with entries
    dash = client.get("/api/master/analytics", headers=admin).json()
    assert dash["students"]["participation_rate"] > 10 and dash["placements"]["placed"] > 50 and dash["placements"]["highest_lpa"] > 20
    assert len(dash["department"]["mou_status"]) >= 6
    prof = client.get("/api/master/faculty/EMP101/profile", headers=admin).json()
    assert prof["total"] > 3 and prof["sections"]
    faculty = {f["emp_id"]: f for f in client.get("/api/master/faculty", headers=admin).json()}
    assert all(sum(f["counts"].values()) > 0 for f in faculty.values())                         # no empty faculty page in the demo
    student = q("SELECT roll_no FROM students WHERE status = 'Active' AND class_id = 4 ORDER BY roll_no LIMIT 1")[0][0]
    sp = client.get(f"/api/master/students/{student}/profile", headers=admin).json()
    assert sp["person"]["id"] == student
    offers = client.get("/api/master/placements/offers?limit=500", headers=admin).json()
    assert offers["total"] >= 80
    export = client.get("/api/master/works/export?group=RESEARCH&columns=title,date,authors,quartile", headers=admin)
    assert export.status_code == 200 and export.content.count(b"\n") > 70


def test_demo_protections(demo):
    admin = sign_in("ADMIN")
    h = auth(admin)
    r = client.post("/api/auth/change-password", json={"old_password": PASSWORD, "new_password": "SomethingElse-1"}, headers=h)
    assert r.status_code == 403 and "demo" in r.json()["detail"].lower()
    assert sign_in("ADMIN")                                                                     # still signs in with the shared password
    assert client.post("/api/master/faculty/EMP102/reset-password", headers=h).status_code == 403
    # the tour is never recorded as seen, so every visitor gets it (the page itself remembers per browser tab)
    assert client.post("/api/auth/tour-seen", json={"tour": "portal"}, headers=h).json()["tours_seen"] == []
    assert client.get("/api/auth/me", headers=h).json()["tours_seen"] == []


def test_reset_restores_the_original_department_and_is_rate_limited(demo):
    admin = auth(sign_in("ADMIN"))
    before = {t: q(f"SELECT COUNT(*) FROM {t}")[0][0] for t in ("students", "faculty", "form_submissions", "placement_offers")}
    cls = client.get("/api/master/classes", headers=admin).json()[0]["class_id"]
    assert client.post("/api/master/students", json={"roll_no": "99XX001", "full_name": "Visitor Added", "class_id": cls}, headers=admin).status_code == 200
    assert client.put("/api/master/faculty/EMP116", json={"designation": "Changed by a visitor"}, headers=admin).status_code == 200
    assert q("SELECT COUNT(*) FROM students")[0][0] == before["students"] + 1
    r = client.post("/api/demo/reset")
    assert r.status_code == 200 and r.json()["success"]
    after = {t: q(f"SELECT COUNT(*) FROM {t}")[0][0] for t in before}
    assert after == before                                                                      # exactly the same department again
    assert q("SELECT COUNT(*) FROM students WHERE roll_no = '99XX001'")[0][0] == 0
    assert q("SELECT designation FROM faculty WHERE emp_id = 'EMP116'")[0][0] != "Changed by a visitor"
    assert sign_in("EMP101") and sign_in("ADMIN")                                               # logins survive the reset
    again = client.post("/api/demo/reset")                                                      # the button is public, so it is rate limited
    assert again.status_code == 429 and "seconds" in again.json()["detail"]


def test_demo_refuses_to_touch_a_database_with_real_data(monkeypatch, tmp_path):
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("MASTER_DB_PATH", str(tmp_path / "real.db"))
    monkeypatch.setattr(db_manager, "DB_PATH", str(tmp_path / "real-news.db"))
    db_manager.init_db()
    init_master_db()
    with db() as c:
        c.execute("INSERT INTO faculty (emp_id, full_name, email) VALUES ('EMP001', 'A Real Person', 'real@college.edu')")
    with pytest.raises(seed.DemoRefused):
        seed.start()
    assert q("SELECT COUNT(*) FROM faculty WHERE emp_id = 'EMP001'")[0][0] == 1                  # untouched
    with db() as c:                                                                              # only the demo's own marker unlocks a reset
        assert c.execute("SELECT COUNT(*) FROM sqlite_master WHERE name = 'demo_state'").fetchone()[0] == 1
        assert c.execute("SELECT COUNT(*) FROM demo_state").fetchone()[0] == 0


def test_outside_demo_mode_nothing_demo_is_active(monkeypatch, tmp_path):
    monkeypatch.delenv("DEMO_MODE", raising=False)
    assert client.get("/api/demo/info").json() == {"enabled": False}
    assert client.post("/api/demo/reset").status_code == 404
    monkeypatch.setenv("MASTER_DB_PATH", str(tmp_path / "m.db"))
    monkeypatch.setenv("MASTER_ADMIN_PASSWORD", "RealAdmin-Pass-1")
    monkeypatch.setenv("MASTER_SECRET", "s")
    init_master_db()
    r = client.post("/api/auth/login", json={"id": "ADMIN", "password": "RealAdmin-Pass-1"})
    assert r.status_code == 200 and r.json()["user"]["must_change"] is True                      # a normal deployment still forces a change
    assert client.post("/api/auth/login", json={"id": "ADMIN", "password": PASSWORD}).status_code == 401   # the demo password opens nothing real
    assert client.post("/api/auth/change-password", json={"old_password": "RealAdmin-Pass-1", "new_password": "A-Better-Pass-2"},
                       headers={"Authorization": "Bearer " + r.json()["token"]}).status_code == 200


def test_demo_has_approvals_and_a_working_pretend_sheet(demo):
    from backend.demo import data as D
    hod, tutor = sign_in(D.HOD), sign_in(D.TUTORS[2])
    s = client.get("/api/review/summary", headers=auth(hod)).json()
    assert s["to_review"] >= 8, s
    items = client.get("/api/review/items?scope=review", headers=auth(hod)).json()["items"]
    assert any(i["warnings"] for i in items), "some responses should be flagged for the walkthrough"
    assert client.get("/api/review/items?scope=returned", headers=auth(hod)).json()["total"] >= 1
    mine = client.get("/api/review/items?scope=review", headers=auth(tutor)).json()
    assert mine["total"] >= 1 and all(i["kind"] == "PLACEMENT" for i in mine["items"]), mine["total"]
    # a returned response reaches the faculty member it was sent to
    ret = client.get("/api/review/items?scope=returned", headers=auth(hod)).json()["items"][0]
    with db() as conn:
        emp = conn.execute("SELECT assigned_emp_id FROM staged_items WHERE item_id = ?", (ret["item_id"],)).fetchone()[0]
    f = sign_in(emp)
    assert client.get("/api/review/summary", headers=auth(f)).json()["returned_to_me"] >= 1
    # Pull now brings in a few new responses
    before = client.get("/api/review/summary", headers=auth(hod)).json()["to_review"]
    r = client.post("/api/sync/run", json={}, headers=auth(hod))
    assert r.status_code == 200 and r.json()["new_or_updated"] >= 5, r.text
    assert client.get("/api/review/summary", headers=auth(hod)).json()["to_review"] > before
