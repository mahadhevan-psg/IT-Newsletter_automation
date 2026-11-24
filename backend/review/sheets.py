"""Reading a Google Sheet of form responses. The sheet is only ever READ: nothing is written to it or deleted from it,
so the original responses stay in Google exactly as they are.

Two ways in, chosen automatically:
  * a service account (set GOOGLE_SERVICE_ACCOUNT_JSON to its key; share each sheet with its e-mail address as Viewer):
    the sheets stay private. Recommended, since the responses hold e-mail addresses and roll numbers.
  * no credentials: the sheet is shared as "Anyone with the link can view" and is read through its CSV export link.
"""
import csv
import io
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import requests

from backend.master import blocks, ingest
from backend.master.common import base_title, norm_header, uniquify_headers

TIMEOUT = 30
SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly"


class SheetError(Exception):
    """Something went wrong reading a sheet; the message is written for the person who set it up."""


def parse_url(url: str) -> Tuple[str, Optional[str]]:
    m = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", url or "")
    if not m:
        raise SheetError("That does not look like a Google Sheets link. Copy the address of the responses sheet from your browser.")
    g = re.search(r"[#&?]gid=(\d+)", url)
    return m.group(1), (g.group(1) if g else None)


def service_account_info() -> Optional[Dict[str, Any]]:
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw:
        return None
    if raw.startswith("{"):
        try:
            return json.loads(raw)
        except ValueError:
            raise SheetError("GOOGLE_SERVICE_ACCOUNT_JSON holds JSON text that is not valid (it must be the whole key on one line).")
    path = _find_key_file(raw)
    if not path:
        raise SheetError(f"The key file '{raw}' was not found. Put the file in the project folder and set GOOGLE_SERVICE_ACCOUNT_JSON=google-key.json "
                         "(a path like /data/... only exists inside Docker).")
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except (ValueError, OSError):
        raise SheetError(f"The key file '{path}' could not be read as JSON. Download the service account's JSON key again from Google Cloud.")


def _find_key_file(raw: str) -> Optional[str]:
    """The key file named in GOOGLE_SERVICE_ACCOUNT_JSON. A path written for Docker (/data/google-key.json) is also looked for by its file name in the
    project folder and the database folder, so the same .env works on a computer without Docker."""
    here = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    name = os.path.basename(raw.replace("\\", "/"))
    for cand in (raw, os.path.join(here, raw), os.path.join(here, name), os.path.join(here, "database", name), os.path.join(os.environ.get("DATA_DIR", ""), name) if os.environ.get("DATA_DIR") else ""):
        if cand and os.path.isfile(cand):
            return cand
    return None


def using_service_account() -> bool:
    try:
        return service_account_info() is not None
    except SheetError:
        return True


class Rows(list):
    """The responses, which also remember the sheet's column titles (a sheet with no responses yet still has its titles)."""
    headers: List[str] = []


def _table(values: List[List[Any]]) -> List[Dict[str, str]]:
    """First row = column titles; the rest = one response each. Empty rows and untitled columns are dropped."""
    if not values:
        return Rows()
    heads = uniquify_headers([str(h).strip() for h in values[0]])          # a title that repeats keeps its place: 'Title', 'Title#2' ...
    out = Rows()
    out.headers = [h for h in heads if h]
    for row in values[1:]:
        rec = {heads[i]: ("" if v is None else str(v).strip()) for i, v in enumerate(row) if i < len(heads) and heads[i]}
        if any(rec.values()):
            out.append(rec)
    return out


def _fetch_csv(sid: str, gid: Optional[str]) -> List[Dict[str, str]]:
    url = f"https://docs.google.com/spreadsheets/d/{sid}/export?format=csv" + (f"&gid={gid}" if gid else "")
    try:
        r = requests.get(url, timeout=TIMEOUT)
    except requests.RequestException:
        raise SheetError("Could not reach Google. Check the internet connection and try again.")
    ctype = r.headers.get("content-type", "")
    if r.status_code in (401, 403, 404) or "text/html" in ctype or r.text.lstrip().lower().startswith("<!doctype html"):
        raise SheetError("The sheet cannot be opened. Share it as 'Anyone with the link can view', or connect a Google service account (see the setup note below).")
    if r.status_code != 200:
        raise SheetError(f"Google answered with an error ({r.status_code}).")
    return _table(list(csv.reader(io.StringIO(r.content.decode("utf-8-sig")))))


def _explain(resp, email: str) -> None:
    """Turn Google's refusal into the real reason (it is not always 'not shared')."""
    try:
        err = resp.json().get("error", {})
    except ValueError:
        err = {}
    text = (err.get("message") or "") + " " + " ".join(str(d.get("reason", "")) for d in err.get("details", []) if isinstance(d, dict))
    low = text.lower()
    if "has not been used" in low or "service_disabled" in low or "is disabled" in low:
        raise SheetError("The Google Sheets API is not switched on for the Google Cloud project that owns this key. In Google Cloud, open 'APIs & Services', "
                         "search for 'Google Sheets API' and press Enable (use the same project as the service account), then wait a minute and test again.")
    if "not supported for this document" in low or resp.status_code == 400:
        raise SheetError("This file is not a native Google Sheet (it may be an uploaded Excel file). Open it and use File > Save as Google Sheets, then use the new link.")
    if resp.status_code == 404:
        raise SheetError("Google could not find that sheet. Check the link is the responses sheet's address.")
    if resp.status_code == 403:
        raise SheetError(f"The service account cannot open this sheet. Share it with {email} (Viewer or Editor), exactly that address. Google said: {err.get('message', 'permission denied')}")
    raise SheetError(f"Google refused the request ({resp.status_code}): {err.get('message', 'no details')}")


def _fetch_api(sid: str, gid: Optional[str]) -> List[Dict[str, str]]:
    try:
        from google.auth.transport.requests import AuthorizedSession
        from google.oauth2 import service_account
        creds = service_account.Credentials.from_service_account_info(service_account_info(), scopes=[SCOPE])
        session = AuthorizedSession(creds)
        meta = session.get(f"https://sheets.googleapis.com/v4/spreadsheets/{sid}?fields=sheets.properties(sheetId,title)", timeout=TIMEOUT)
        if meta.status_code >= 400:
            _explain(meta, service_account_info().get("client_email", "the service account"))
        meta.raise_for_status()
        sheets = meta.json().get("sheets", [])
        pick = next((s for s in sheets if gid is not None and str(s["properties"]["sheetId"]) == gid), sheets[0] if sheets else None)
        if not pick:
            raise SheetError("The spreadsheet has no sheets.")
        title = pick["properties"]["title"].replace("'", "''")
        vals = session.get(f"https://sheets.googleapis.com/v4/spreadsheets/{sid}/values/{quote(chr(39) + title + chr(39))}",
                           params={"majorDimension": "ROWS", "valueRenderOption": "FORMATTED_VALUE", "dateTimeRenderOption": "FORMATTED_STRING"}, timeout=TIMEOUT)
        vals.raise_for_status()
        return _table(vals.json().get("values", []))
    except SheetError:
        raise
    except requests.RequestException:
        raise SheetError("Could not reach Google. Check the internet connection and try again.")
    except Exception as e:                                                         # bad key, expired credentials ...
        raise SheetError(f"Google would not let the service account in ({type(e).__name__}). Check the service account key.")


def fetch_rows(url: str) -> List[Dict[str, str]]:
    """Every response in the sheet as {column title: text}."""
    if (url or "").startswith("demo://"):
        from backend.demo import fake_sheets                                       # the demo site has no real sheets: a pretend one
        return fake_sheets.rows(url[len("demo://"):])
    sid, gid = parse_url(url)
    return _fetch_api(sid, gid) if using_service_account() else _fetch_csv(sid, gid)


def _check_block_form(form_id: str, heads: List[str]) -> Dict[str, Any]:
    """The category-based forms: the sheet's columns compared with the layout the application expects, position by position."""
    spec = ingest.specs()["forms"][form_id]
    expected = blocks.sheet_headers(form_id)
    have = {norm_header(base_title(h)) for h in heads}
    sheet_of = {flat: sheet for sheet, flat in spec["layout"].get("closing_rename", {}).items()}       # a renamed closing question is a column of the sheet under its sheet title
    required = set()
    for q in spec["questions"]:
        if q.get("req") and not q.get("legacy") and q["type"] != "section" and not q.get("derived"):
            required.update(norm_header(t) for t in (sheet_of.get(q["q"], q["q"]), *q.get("aliases", [])))
    gates = [norm_header(b["gate"]) for b in spec["layout"]["blocks"]]
    missing, seen = [], set()
    for title in expected:
        n = norm_header(title)
        if n in seen:
            continue
        seen.add(n)
        if (n in required or n in gates) and n not in have:
            missing.append(title)
    known = {norm_header(t) for t in expected} | {"timestamp", "email address"}
    for q in spec["questions"]:
        known.update(norm_header(t) for t in (q["q"], *q.get("aliases", [])))
    unknown = [h for h in dict.fromkeys(base_title(h) for h in heads) if norm_header(h) not in known]
    differences = []
    if len(heads) != len(expected):
        differences.append(f"The sheet has {len(heads)} columns; the form should give {len(expected)}")
    for i, (h, e) in enumerate(zip(heads, expected)):
        if norm_header(base_title(h)) != norm_header(e):
            differences.append(f"Column {i + 1} is '{base_title(h)}' but '{e}' was expected")
            if len(differences) >= 4:
                break
    return {"missing_required": missing, "unknown_columns": unknown, "layout_differences": differences}


def check_source(form_id: str, url: str) -> Dict[str, Any]:
    """'Test this link': can it be read, and do its columns look like this form's questions?"""
    rows = fetch_rows(url)
    heads = list(getattr(rows, "headers", None) or dict.fromkeys(k for r in rows for k in r))
    if form_id != "placement" and blocks.has_blocks(ingest.specs()["forms"][form_id]):
        out = _check_block_form(form_id, heads)
        return {"rows": len(rows), "columns": len(heads), **out}
    found = {norm_header(h) for h in heads}
    qs = ingest.specs()["placement" if form_id == "placement" else "forms"]
    questions = (qs["questions"] if form_id == "placement" else qs[form_id]["questions"])
    expected = [q for q in questions if q["type"] != "section" and q.get("key")]
    missing = [q["q"] for q in expected if q.get("req") and not q.get("legacy") and not any(norm_header(t) in found for t in (q["q"], *q.get("aliases", [])))]
    known = {norm_header(t) for q in expected for t in (q["q"], *q.get("aliases", []))} | {"timestamp", "email address"}
    asks = ("do you have", "would you like")                                  # the placement form's yes / no gates are not data
    return {"rows": len(rows), "columns": len(heads), "missing_required": missing, "layout_differences": [],
            "unknown_columns": [h for h in heads if norm_header(h) not in known and not norm_header(h).startswith(asks)]}
