"""The guided tours are shown once per person per app: the server remembers which ones were finished or skipped."""
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient  # noqa: E402

from backend.app import app  # noqa: E402
from backend.master.auth import set_staff_password  # noqa: E402
from database.master_db import add_tours_seen, db, init_master_db  # noqa: E402


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("MASTER_DB_PATH", str(tmp_path / "master.db"))
    monkeypatch.setenv("MASTER_ADMIN_PASSWORD", "AdminPass1!")
    monkeypatch.setenv("MASTER_SECRET", "test-secret")
    init_master_db()
    with db() as c:
        c.execute("INSERT INTO faculty (emp_id, full_name, email) VALUES ('EMP001', 'Dr. Asha Rao', 'a@x.edu')")
        set_staff_password(c, "EMP001", "Temp-Pass-1")
        c.execute("INSERT INTO students (roll_no, full_name, programme, class_id) VALUES ('21IT001', 'Kavin M', 'UG', 1)")
    return TestClient(app)


def sign_in(client, uid, pw):
    r = client.post("/api/auth/login", json={"id": uid, "password": pw})
    assert r.status_code == 200, r.text
    return r.json()


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_a_new_person_has_seen_no_tours_and_each_one_is_remembered(client):
    login = sign_in(client, "EMP001", "Temp-Pass-1")
    assert login["user"]["tours_seen"] == []
    h = auth(login["token"])
    assert client.get("/api/auth/me", headers=h).json()["tours_seen"] == []
    assert client.post("/api/auth/tour-seen", json={"tour": "home"}, headers=h).json() == {"tours_seen": ["home"]}
    assert client.post("/api/auth/tour-seen", json={"tour": "portal"}, headers=h).json() == {"tours_seen": ["home", "portal"]}
    assert client.post("/api/auth/tour-seen", json={"tour": "portal"}, headers=h).json() == {"tours_seen": ["home", "portal"]}   # twice is harmless
    # it is stored for the person, so a later sign-in (any device) does not start the tour again
    again = sign_in(client, "EMP001", "Temp-Pass-1")
    assert again["user"]["tours_seen"] == ["home", "portal"]
    assert client.get("/api/auth/me", headers=auth(again["token"])).json()["tours_seen"] == ["home", "portal"]


def test_tours_are_kept_per_person(client):
    staff = sign_in(client, "EMP001", "Temp-Pass-1")
    student = sign_in(client, "21IT001", "21IT001")                       # a student's first password is the roll number
    client.post("/api/auth/tour-seen", json={"tour": "diary"}, headers=auth(student["token"]))
    assert client.get("/api/auth/me", headers=auth(staff["token"])).json()["tours_seen"] == []
    assert client.get("/api/auth/me", headers=auth(student["token"])).json()["tours_seen"] == ["diary"]


def test_only_known_tours_and_only_when_signed_in(client):
    h = auth(sign_in(client, "EMP001", "Temp-Pass-1")["token"])
    assert client.post("/api/auth/tour-seen", json={"tour": "nonsense"}, headers=h).status_code == 400
    assert client.post("/api/auth/tour-seen", json={"tour": "home,portal"}, headers=h).status_code == 400
    assert client.post("/api/auth/tour-seen", json={}, headers=h).status_code == 400
    assert client.post("/api/auth/tour-seen", json={"tour": "home"}).status_code == 401


def test_an_older_database_gets_the_new_column(tmp_path):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE users (user_id TEXT PRIMARY KEY, user_type TEXT, password_hash TEXT, must_change INTEGER DEFAULT 1, last_login TIMESTAMP)")
    conn.execute("INSERT INTO users (user_id, user_type, password_hash) VALUES ('X', 'STAFF', 'h')")
    add_tours_seen(conn)
    add_tours_seen(conn)                                                   # running it again is fine
    assert conn.execute("SELECT tours_seen FROM users WHERE user_id = 'X'").fetchone()[0] == ""
