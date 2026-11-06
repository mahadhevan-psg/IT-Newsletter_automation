"""Where each address leads: / is the sign-in page, /homepage/ the faculty forms page, /portal/ and /diary/ the applications."""
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
    # staff go to the forms page, students to the diary
    assert "STAFF_HOME = '/homepage/'" in r.text and "STUDENT_HOME = '/diary/'" in r.text
    assert "/homepage/home.css" in r.text and client.get("/homepage/home.css").status_code == 200
    assert client.get("/homepage/assets/logo-psg.jpg").status_code in (200, 404)    # logos are optional files; the path must be the homepage folder


def test_old_login_address_redirects_to_root_keeping_next():
    for src, dst in (("/login/", "/"), ("/login", "/"), ("/login/?next=/newsletter/", "/?next=/newsletter/")):
        r = client.get(src, follow_redirects=False)
        assert r.status_code in (302, 307) and r.headers["location"] == dst, (src, r.status_code, r.headers.get("location"))


def test_forms_homepage_is_login_gated_with_portal_and_signout_buttons():
    r = client.get("/homepage/")
    assert r.status_code == 200
    html = r.text
    assert 'style="visibility:hidden"' in html and "sessionStorage.getItem('tok')" in html      # hidden until the check passes
    assert html.count("Open form") == 6                                                          # all the form links are there for faculty
    assert 'href="/portal/">Go to portal</a>' in html
    assert ">Sign in<" not in html                                                               # the old Sign in button is gone
    signout = html[html.index('id="signout"') - 40: html.index("</button>", html.index('id="signout"')) + 9]
    assert "<svg" in signout and "Sign out" in signout.split("<svg")[0]                          # an icon button: the label is only title / aria-label
    assert html.index('id="signout"') < html.index('class="portal-btn"')                          # sign-out sits to the LEFT of Go to portal


def test_applications_still_served_and_send_signed_out_users_to_root():
    assert client.get("/portal/").status_code == 200 and client.get("/diary/").status_code == 200
    for path in ("/portal/portal.js", "/diary/diary.js", "/newsletter/app.js"):
        js = client.get(path).text
        assert "/login/" not in js and ("location.replace('/')" in js or 'location.replace("/?next=/newsletter/")' in js), path
