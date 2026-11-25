"""Where each address leads: / is the sign-in page, /portal/ and /diary/ the applications."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient  # noqa: E402

from backend.app import app  # noqa: E402

client = TestClient(app)


def test_root_is_the_sign_in_page_and_nothing_else():
    r = client.get("/")
    assert r.status_code == 200
    assert 'id="login-form"' in r.text and "Sign in" in r.text
    assert "Open form" not in r.text                                    # no form links before signing in
    # staff go to the portal, students to the diary
    assert "STAFF_HOME = '/portal/'" in r.text and "STUDENT_HOME = '/diary/'" in r.text
    assert "/home.css" in r.text and client.get("/home.css").status_code == 200
    assert client.get("/assets/logo-psg.jpg").status_code in (200, 404)    # logos are optional files; the path must be the sign-in folder


def test_old_login_address_redirects_to_root_keeping_next():
    for src, dst in (("/login/", "/"), ("/login", "/"), ("/login/?next=/newsletter/", "/?next=/newsletter/")):
        r = client.get(src, follow_redirects=False)
        assert r.status_code in (302, 307) and r.headers["location"] == dst, (src, r.status_code, r.headers.get("location"))


def test_the_google_forms_page_is_gone_and_its_old_address_leads_to_the_portal():
    r = client.get("/homepage/", follow_redirects=False)
    assert r.status_code in (302, 307) and r.headers["location"] == "/portal/"
    page = client.get("/portal/").text
    assert "Google Forms" not in page and "/homepage/" not in page
    for path in ("/api/sync/overview", "/api/master/forms/form_student/template"):
        assert client.get(path).status_code in (401, 404, 405), path             # gone (an unknown /api/ address asks for a sign-in first)


def test_applications_still_served_and_send_signed_out_users_to_root():
    assert client.get("/portal/").status_code == 200 and client.get("/diary/").status_code == 200
    for path in ("/portal/portal.js", "/diary/diary.js", "/newsletter/app.js"):
        js = client.get(path).text
        assert "/login/" not in js and ("location.replace('/')" in js or 'location.replace("/?next=/newsletter/")' in js), path


def test_every_application_loads_the_guided_tour_and_has_a_help_slot():
    """Staff portal, student diary and newsletter studio each load the tour engine and the shared tour texts."""
    for page in ("/portal/", "/diary/", "/newsletter/"):
        html = client.get(page).text
        assert 'id="help-host"' in html, page                              # where the Help button is placed
        assert "tour.css" in html and "tour.js" in html and "tours.js" in html, page
    for asset in ("/portal/tour.js", "/portal/tours.js", "/portal/tour.css"):
        assert client.get(asset).status_code == 200, asset
    tours = client.get("/portal/tours.js").text
    for entry in ("app: 'portal'", "app: 'diary'", "app: 'studio'"):
        assert entry in tours, entry
    # each app starts its tour from its own start-up code
    assert "Tours.portal(me, token)" in client.get("/portal/portal.js").text
    assert "Tours.diary(me, token)" in client.get("/diary/diary.js").text
    assert "Tours.studio(r.me, r.token)" in client.get("/newsletter/app.js").text


def test_health_check_answers_without_signing_in(monkeypatch, tmp_path):
    """The hosting platform polls /healthz; it must work with no login and fail loudly if a database is unreadable."""
    from database import db_manager
    monkeypatch.setenv("MASTER_DB_PATH", str(tmp_path / "master.db"))
    monkeypatch.setattr(db_manager, "DB_PATH", str(tmp_path / "news.db"))
    from database.master_db import init_master_db
    db_manager.init_db()
    init_master_db()
    r = client.get("/healthz")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_deployment_files_exist_and_agree():
    root = os.path.join(os.path.dirname(__file__), "..")
    read = lambda n: open(os.path.join(root, n), encoding="utf-8").read()
    docker, blueprint, ignore = read("Dockerfile"), read("render.yaml"), read(".dockerignore")
    assert "healthz" in blueprint and "mountPath: /data" in blueprint and "plan: starter" in blueprint       # a paid plan: the free one has no disk
    for var in ("MASTER_DB_PATH", "NEWSLETTER_DB_PATH", "MASTER_SECRET", "MASTER_ADMIN_PASSWORD"):
        assert var in blueprint, var
    assert "/data/master_system.db" in docker and "/data/newsletter_system.db" in docker
    assert "**/*.db" in ignore and "output/" in ignore and "venv/" in ignore                                  # no local data or secrets in the image
    assert "pytest" not in read("requirements.txt") and "pytest" in read("requirements-dev.txt")


def test_demo_service_files_are_safe_and_complete():
    """The demo service is the same image with DEMO_MODE on: no disk, free plan, and it must not be defined inside the real service."""
    root = os.path.join(os.path.dirname(__file__), "..")
    read = lambda n: open(os.path.join(root, n), encoding="utf-8").read()
    demo, real = read("render.demo.yaml"), read("render.yaml")
    assert 'key: DEMO_MODE' in demo and 'value: "true"' in demo and "plan: free" in demo and "disk:" not in demo and "/healthz" in demo
    assert "DEMO_MODE" not in real                                                         # the real service can never be a demo by accident
    assert "config.default" in read("Dockerfile") and "DEMO" in read("docker-entrypoint.sh")
    html = client.get("/").text
    assert "demo-box" in html and "/api/demo/info" in html and "/portal/demo.js" in html
    for page in ("/portal/", "/diary/", "/newsletter/"):
        assert "/portal/demo.js" in client.get(page).text, page
