"""One-time sign-in that lets the portal copy photos to a Google Drive folder.

    python drive_authorize.py

Needs GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET in .env (an OAuth client of type "Desktop app" from Google Cloud).
A browser page opens: sign in as the Google account that OWNS the Drive folder (the photos will count against that account's storage) and
allow access. The script prints GOOGLE_OAUTH_REFRESH_TOKEN: copy that line into .env. Nothing else is stored.
Only files this application itself creates are reachable with this permission (scope drive.file), never the rest of the Drive.
"""
import http.server
import os
import secrets
import sys
import threading
import urllib.parse
import webbrowser

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import envfile  # noqa: E402,F401
import requests  # noqa: E402

SCOPE = "https://www.googleapis.com/auth/drive.file"


def main() -> int:
    cid, secret = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", ""), os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "")
    if not cid or not secret:
        print("Put GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET in .env first (see .env.example).")
        return 1
    state, got = secrets.token_urlsafe(16), {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            got.update({k: v[0] for k, v in q.items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<h3>Done. You can close this tab and go back to the terminal.</h3>")

        def log_message(self, *a):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    redirect = f"http://127.0.0.1:{server.server_port}"
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({"client_id": cid, "redirect_uri": redirect, "response_type": "code", "scope": SCOPE,
                                                                                   "access_type": "offline", "prompt": "consent", "state": state})
    print("Opening your browser. If it does not open, paste this address into it:\n" + url + "\n")
    webbrowser.open(url)
    t = threading.Thread(target=server.handle_request)
    t.start()
    t.join(300)
    if got.get("state") != state or "code" not in got:
        print("No answer from Google (or it was cancelled). Run the command again.")
        return 1
    r = requests.post("https://oauth2.googleapis.com/token", data={"code": got["code"], "client_id": cid, "client_secret": secret, "redirect_uri": redirect, "grant_type": "authorization_code"}, timeout=30)
    token = r.json().get("refresh_token")
    if not token:
        print("Google did not return a refresh token:", r.text[:300])
        return 1
    print("Add this line to your .env file:\n\nGOOGLE_OAUTH_REFRESH_TOKEN=" + token + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
