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

from backend.master import ingest
from backend.master.common import norm_header

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
    try:
        return json.loads(raw) if raw.startswith("{") else json.load(open(raw, encoding="utf-8"))
    except (ValueError, OSError):
        raise SheetError("GOOGLE_SERVICE_ACCOUNT_JSON is set but is not valid JSON (or the file cannot be read).")


def using_service_account() -> bool:
    try:
        return service_account_info() is not None
    except SheetError:
        return True


def _table(values: List[List[Any]]) -> List[Dict[str, str]]:
    """First row = column titles; the rest = one response each. Empty rows and untitled columns are dropped."""
    if not values:
        return []
    heads = [str(h).strip() for h in values[0]]
    out = []
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


def _fetch_api(sid: str, gid: Optional[str]) -> List[Dict[str, str]]:
    try:
        from google.auth.transport.requests import AuthorizedSession
        from google.oauth2 import service_account
        creds = service_account.Credentials.from_service_account_info(service_account_info(), scopes=[SCOPE])
        session = AuthorizedSession(creds)
        meta = session.get(f"https://sheets.googleapis.com/v4/spreadsheets/{sid}?fields=sheets.properties(sheetId,title)", timeout=TIMEOUT)
        if meta.status_code in (403, 404):
            raise SheetError("The service account cannot open this sheet. Share the sheet with the service account's e-mail address (Viewer is enough).")
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


def check_source(form_id: str, url: str) -> Dict[str, Any]:
    """'Test this link': can it be read, and do its columns look like this form's questions?"""
    rows = fetch_rows(url)
    heads = list(dict.fromkeys(k for r in rows for k in r)) if rows else []
    found = {norm_header(h) for h in heads}
    qs = ingest.specs()["placement" if form_id == "placement" else "forms"]
    questions = (qs["questions"] if form_id == "placement" else qs[form_id]["questions"])
    expected = [q for q in questions if q["type"] != "section" and q.get("key")]
    missing = [q["q"] for q in expected if q.get("req") and not any(norm_header(t) in found for t in (q["q"], *q.get("aliases", [])))]
    known = {norm_header(t) for q in expected for t in (q["q"], *q.get("aliases", []))} | {"timestamp", "email address"}
    return {"rows": len(rows), "columns": len(heads), "missing_required": missing, "unknown_columns": [h for h in heads if norm_header(h) not in known]}
