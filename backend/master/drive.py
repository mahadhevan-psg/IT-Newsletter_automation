"""Google Drive storage for uploaded photos (the long-term copy).

Uses an OAuth refresh token of the Google account that owns the Drive folder (so the files count against that account's storage, not a service
account's, which has none). Set these in .env:

  GOOGLE_DRIVE_FOLDER_ID          the folder photos go into (open it in Drive: the id is the last part of its address)
  GOOGLE_OAUTH_CLIENT_ID          from Google Cloud -> APIs & Services -> Credentials -> OAuth client (type: Desktop app)
  GOOGLE_OAUTH_CLIENT_SECRET
  GOOGLE_OAUTH_REFRESH_TOKEN      created once by `python drive_authorize.py` while signed in as the account that owns the folder

Without them, photos stay on the server (still resized and compressed) and nothing breaks.
"""
import json
import os
from typing import Dict, Tuple

import requests

SCOPE = "https://www.googleapis.com/auth/drive.file"          # only files this app created
TOKEN_URI = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"
TIMEOUT = 40
_folders: Dict[Tuple[str, str], str] = {}
_session = {"obj": None}


def configured() -> bool:
    return all(os.environ.get(k, "").strip() for k in ("GOOGLE_DRIVE_FOLDER_ID", "GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET", "GOOGLE_OAUTH_REFRESH_TOKEN"))


def _authed():
    if _session["obj"] is None:
        from google.auth.transport.requests import AuthorizedSession
        from google.oauth2.credentials import Credentials
        creds = Credentials(None, refresh_token=os.environ["GOOGLE_OAUTH_REFRESH_TOKEN"], token_uri=TOKEN_URI, client_id=os.environ["GOOGLE_OAUTH_CLIENT_ID"],
                            client_secret=os.environ["GOOGLE_OAUTH_CLIENT_SECRET"], scopes=[SCOPE])
        _session["obj"] = AuthorizedSession(creds)
    return _session["obj"]


def _ok(r):
    if r.status_code >= 400:
        try:
            msg = r.json().get("error", {}).get("message", r.text[:200])
        except ValueError:
            msg = r.text[:200]
        raise RuntimeError(f"Google Drive said {r.status_code}: {msg}")
    return r


def _folder(parent: str, name: str) -> str:
    key = (parent, name)
    if key in _folders:
        return _folders[key]
    s = _authed()
    q = f"name = '{name}' and '{parent}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    found = _ok(s.get(f"{API}/files", params={"q": q, "fields": "files(id)", "spaces": "drive"}, timeout=TIMEOUT)).json().get("files", [])
    if found:
        _folders[key] = found[0]["id"]
    else:
        made = _ok(s.post(f"{API}/files", json={"name": name, "mimeType": "application/vnd.google-apps.folder", "parents": [parent]}, params={"fields": "id"}, timeout=TIMEOUT)).json()
        _folders[key] = made["id"]
    return _folders[key]


def upload(name: str, data: bytes, year: str) -> Tuple[str, str]:
    """Put a JPEG in <root folder>/<year>/ and return (file id, link)."""
    parent = _folder(os.environ["GOOGLE_DRIVE_FOLDER_ID"].strip(), str(year))
    boundary = "ITMATRIXBOUNDARY"
    meta = json.dumps({"name": name, "parents": [parent]})
    body = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{meta}\r\n--{boundary}\r\nContent-Type: image/jpeg\r\n\r\n").encode() + data + f"\r\n--{boundary}--".encode()
    r = _ok(_authed().post(UPLOAD, params={"uploadType": "multipart", "fields": "id,webViewLink"}, data=body, headers={"Content-Type": f"multipart/related; boundary={boundary}"}, timeout=TIMEOUT * 3))
    j = r.json()
    return j["id"], j.get("webViewLink", f"https://drive.google.com/file/d/{j['id']}/view")


def download(file_id: str) -> bytes:
    return _ok(_authed().get(f"{API}/files/{file_id}", params={"alt": "media"}, timeout=TIMEOUT * 3)).content
