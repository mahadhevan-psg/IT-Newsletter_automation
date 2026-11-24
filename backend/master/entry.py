"""Entering data in the application itself.

A person chooses WHAT HAPPENED (a category), fills the fields the Admin has defined for it, and submits. The submission becomes an item in the
approval queue exactly like a response pulled from a Google Sheet, so approval, editing, profiles, reports and the newsletter all work unchanged.
The fields come from the published form definitions (ingest.specs()), so a change the Admin publishes shows up here at once.
"""
import json
import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from backend.master import blocks, ingest, media
from backend.master.auth import User
from backend.master.common import norm_header, parse_date, parse_num
from backend.review import service as review

# fields the person never types: filled in by the application
HIDDEN_KEYS = {"category", "is_landmark", "publish_permission", "authorization_confirmed"}      # consent is not asked: the department collects this data as part of its records
AUTO_YES = ("publish_permission", "authorization_confirmed")
FRIENDLY = {   # (what the tile says, extra words that find it)
    "Academic Excellence & Ranks": ("Students earned a rank or academic honour", "rank topper scholarship university"),
    "Hackathons & Coding Competitions": ("Students won or took part in a hackathon", "hackathon coding contest competition"),
    "Higher Education & Top Placements": ("Student got into higher studies or a top placement", "gate gre admission placement offer"),
    "Technical Projects & Innovations": ("Students built a project or innovation", "project prototype product startup"),
    "Sports, Cultural & Co-Curricular Accomplishments": ("Students did well in sports, culture or clubs", "sports cultural dance music club"),
    "Journal Publications": ("I published a journal paper", "paper article journal scopus"),
    "Conference Publications": ("I presented a conference paper", "conference paper proceedings"),
    "Book / Book Chapters": ("I wrote a book or a chapter", "book chapter isbn"),
    "Funded Research Projects": ("I got a funded research project", "grant funding project dst serb"),
    "Consultancy Projects": ("I did a consultancy project", "consultancy industry client"),
    "Patents & Intellectual Property": ("I filed or got a patent", "patent ip copyright design"),
    "Key Research Innovations & Technical Accomplishments": ("I made a research innovation", "innovation prototype technical"),
    "Awards & Honors Received": ("I received an award", "award honour prize recognition"),
    "Certifications & Upskilling Completed": ("I completed a certification", "certificate nptel course"),
    "Invited Keynote / Expert Lectures Delivered": ("I gave a keynote or expert talk", "keynote lecture talk invited"),
    "Resource Person / Session Chair Roles": ("I was a resource person or session chair", "resource person chair moderator"),
    "FDP / Workshops Attended": ("I attended an FDP or workshop", "fdp workshop training attended"),
    "Professional Body & Editorial Board Roles": ("I joined a professional body or editorial board", "membership editorial reviewer ieee"),
    "Industrial Visits & Field Tours": ("We went on an industrial visit", "industrial visit tour field"),
    "Industry Expert Lectures & Technical Talks": ("An industry expert gave a talk", "expert talk lecture guest"),
    "MoUs Signed & Industrial Collaborations": ("An MoU was signed", "mou collaboration partnership agreement"),
    "Alumni Interactions & Mentorship Sessions": ("We met alumni or ran mentoring", "alumni mentor interaction"),
    "Community & Social Outreach Initiatives": ("We did community outreach", "outreach community social camp"),
    "Highlights": ("A department highlight", "highlight news"), "Achievements / Awards / Recognitions": ("The department won an award", "award recognition"),
    "Events / Programs": ("We organised an event or programme", "event workshop seminar conference programme"),
    "Research / Publications / Innovation": ("A research or publication highlight", "research publication"),
    "Infrastructure / Laboratory Development": ("A new lab or infrastructure", "lab infrastructure equipment"),
    "MoU / Industry Collaboration / Partnerships": ("A partnership or MoU for the department", "mou partnership collaboration"),
    "Faculty Development / Professional Achievements": ("A faculty development programme", "fdp training development"),
    "Student Development / Outreach / Social Initiatives": ("A student development or social initiative", "student development outreach social"),
    "Accreditation / Quality Assurance / Institutional Initiatives": ("Accreditation or quality work", "nba naac nirf accreditation quality"),
    "Other Significant Initiatives": ("Something else worth reporting", "other"),
}


FORM_LABELS = {"form_student": "Student achievements", "form_research": "Research & innovation", "form_faculty": "Faculty achievements",
               "form_departmental": "Department highlights", "form_industry": "Industry, alumni & outreach"}


def catalog(conn) -> List[Dict[str, Any]]:
    """Every form with its categories as tiles: {form_id, title, categories: [{name, tile, keywords, fields}]}."""
    out = []
    specs = ingest.specs()["forms"]
    for fid in ("form_student", "form_research", "form_faculty", "form_departmental", "form_industry"):
        spec = specs.get(fid)
        if not spec:
            continue
        cats = []
        for name in spec["categories"]:
            cfg = spec.get("category_config", {}).get(name, {})
            tile, words = FRIENDLY.get(name, (name, ""))
            cats.append({"name": name, "tile": cfg.get("tile") or tile, "keywords": " ".join(x for x in (name, cfg.get("keywords") or words, spec["title"]) if x).lower(),
                         "fields": len([q for q in blocks.questions_for(spec, name, legacy=False) if _shown(q)])})
        out.append({"form_id": fid, "title": FORM_LABELS.get(fid) or spec["title"].replace("IT Chronicles - ", "").replace(" Submission Form", ""), "categories": cats})
    return out


def _shown(q: Dict[str, Any]) -> bool:
    return not (q.get("key") in HIDDEN_KEYS or q.get("submitter") or q.get("derived") or q["type"] == "section")


def _widget(q: Dict[str, Any]) -> str:
    if q.get("key") == "media_url":
        return "photo"
    if q["type"] == "confirm":
        return "confirm"
    return q["type"]


def display_label(q: Dict[str, Any]) -> str:
    """The label faculty see (the builder shows the same text)."""
    return "Photos (optional, up to 4)" if q.get("key") == "media_url" else q["q"]


ZONE_ORDER = {"common": 0, "block": 1, "closing": 2}


def form_for(form_id: str, category: str) -> Dict[str, Any]:
    spec = ingest.specs()["forms"].get(form_id)
    if not spec or category not in spec["categories"]:
        raise HTTPException(404, "That kind of entry no longer exists")
    qs = [q for q in blocks.questions_for(spec, category, legacy=False) if _shown(q)]
    qs.sort(key=lambda q: ZONE_ORDER.get(q.get("zone"), 1))                     # stable: keeps the Admin's order inside each part
    return {"form_id": form_id, "category": category, "title": category,
            "fields": [{"fid": q["fid"], "q": display_label(q), "type": _widget(q), "req": bool(q.get("req")), "help": q.get("help"), "choices": q.get("choices"), "zone": q.get("zone"), "nl": q.get("nl"),
                        "default": None} for q in qs]}      # consent is never pre-ticked: the person chooses


# ------------------------------------------------------------------------------------------------ people look-ups used by the entry screen
def find_faculty(conn, q: str, limit: int = 12) -> List[Dict[str, str]]:
    like = f"%{(q or '').strip()}%"
    return [{"emp_id": r[0], "name": r[1], "label": f"{r[0]} - {r[1]}"} for r in conn.execute(
        "SELECT emp_id, full_name FROM faculty WHERE status = 'Active' AND emp_id != 'ADMIN' AND (full_name LIKE ? OR emp_id LIKE ?) ORDER BY full_name LIMIT ?", (like, like, limit))]


def find_students(conn, q: str, limit: int = 12) -> List[Dict[str, str]]:
    like = f"%{(q or '').strip()}%"
    return [{"roll_no": r[0], "name": r[1], "class": r[2]} for r in conn.execute(
        "SELECT s.roll_no, s.full_name, c.class_code FROM students s LEFT JOIN classes c ON c.class_id = s.class_id WHERE s.roll_no LIKE ? OR s.full_name LIKE ? ORDER BY s.roll_no LIMIT ?", (like, like, limit))]


def check_rolls(conn, text: str) -> List[Dict[str, Any]]:
    out = []
    for line in str(text or "").replace(",", "\n").split("\n"):
        roll = line.strip().upper()
        if roll:
            r = conn.execute("SELECT s.roll_no, s.full_name, c.class_code FROM students s LEFT JOIN classes c ON c.class_id = s.class_id WHERE upper(s.roll_no) = ?", (roll,)).fetchone()
            out.append({"roll_no": roll, "name": r[1] if r else None, "class": r[2] if r else None, "found": bool(r)})
    return out


# ------------------------------------------------------------------------------------------------ submitting
def _clean(q: Dict[str, Any], value: Any) -> str:
    """One answer as the text a sheet cell would hold; raises HTTPException(400) naming the field when it is not valid."""
    kind = _widget(q)
    if kind == "photo":
        ids = [int(x) for x in (value if isinstance(value, list) else [value] if value else [])]
        for mid in ids:
            if not media.get(mid):
                raise HTTPException(400, f"'{q['q']}': a photo is missing, upload it again")
        return media.ref(ids[0]) if ids else ""
    v = ", ".join(str(x) for x in value) if isinstance(value, list) else str(value if value is not None else "").strip()
    if not v:
        return ""
    if kind == "date" and not parse_date(v):
        raise HTTPException(400, f"'{q['q']}': enter a date like 2026-03-31")
    if kind == "number" and parse_num(v) is None:
        raise HTTPException(400, f"'{q['q']}': enter a number")
    if kind == "url" and not v.lower().startswith(("http://", "https://")):
        raise HTTPException(400, f"'{q['q']}': a link must start with http:// or https://")
    if kind in ("choice", "list") and q.get("choices") and v not in q["choices"]:
        raise HTTPException(400, f"'{q['q']}': choose one of the listed options")
    return v


def build_row(conn, user: User, form_id: str, category: str, values: Dict[str, Any]) -> Dict[str, str]:
    spec = ingest.specs()["forms"].get(form_id)
    if not spec or category not in spec["categories"]:
        raise HTTPException(404, "That kind of entry no longer exists")
    me = conn.execute("SELECT emp_id, full_name, email FROM faculty WHERE emp_id = ?", (user.id,)).fetchone()
    if not me:
        raise HTTPException(403, "Only faculty can enter this kind of data")
    cat_q = next(q for q in spec["questions"] if q.get("key") == "category" and not q.get("legacy"))
    row: Dict[str, str] = {"Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "Email Address": me["email"] or "", cat_q["q"]: category}
    missing = []
    for q in blocks.questions_for(spec, category, legacy=False):
        key = q.get("key")
        if q.get("submitter"):
            row[q["q"]] = f"{me['emp_id']} - {me['full_name']}"
        elif key in AUTO_YES:
            row[q["q"]] = "Yes"
        elif key == "is_landmark":
            row[q["q"]] = (q.get("choices") or ["No (Standard Entry)"])[0]
        elif _shown(q):
            v = _clean(q, values.get(q["fid"]))
            if v:
                row[q["q"]] = v
            elif q.get("req"):
                missing.append(q["q"])
    if missing:
        raise HTTPException(400, "Please fill in: " + ", ".join(missing))
    extra = values.get("_more_photos")
    if extra:
        refs = [media.ref(int(i)) for i in extra if media.get(int(i))]
        if refs:
            row["Additional photos"] = ", ".join(refs)
    return row


def submit(conn, user: User, form_id: str, category: str, values: Dict[str, Any], draft_id: Optional[str] = None) -> Dict[str, Any]:
    row = build_row(conn, user, form_id, category, values)
    item_id = review.stage_app_entry(conn, form_id, row, user)
    if draft_id:
        conn.execute("DELETE FROM entry_drafts WHERE draft_id = ? AND owner_id = ?", (draft_id, user.id))
    return {"item_id": item_id, "title": ingest.summarize(form_id, row)["title"]}


# ------------------------------------------------------------------------------------------------ drafts
def save_draft(conn, user: User, draft_id: str, form_id: str, category: str, values: Dict[str, Any]) -> Dict[str, Any]:
    if not draft_id or len(draft_id) > 64:
        draft_id = uuid.uuid4().hex
    conn.execute("INSERT INTO entry_drafts (draft_id, owner_id, form_id, category, data_json, updated_at) VALUES (?,?,?,?,?,CURRENT_TIMESTAMP) "
                 "ON CONFLICT(draft_id) DO UPDATE SET data_json = excluded.data_json, category = excluded.category, updated_at = CURRENT_TIMESTAMP WHERE owner_id = excluded.owner_id",
                 (draft_id, user.id, form_id, category, json.dumps(values, ensure_ascii=False)))
    return {"draft_id": draft_id}


def list_drafts(conn, user: User) -> List[Dict[str, Any]]:
    out = []
    for r in conn.execute("SELECT draft_id, form_id, category, data_json, updated_at FROM entry_drafts WHERE owner_id = ? ORDER BY updated_at DESC", (user.id,)):
        data = json.loads(r["data_json"] or "{}")
        title = next((str(v) for k, v in data.items() if str(v).strip() and not str(k).startswith("_")), "")
        out.append({"draft_id": r["draft_id"], "form_id": r["form_id"], "category": r["category"], "summary": title[:80], "updated_at": r["updated_at"]})
    return out


def get_draft(conn, user: User, draft_id: str) -> Dict[str, Any]:
    r = conn.execute("SELECT * FROM entry_drafts WHERE draft_id = ? AND owner_id = ?", (draft_id, user.id)).fetchone()
    if not r:
        raise HTTPException(404, "That draft no longer exists")
    return {"draft_id": r["draft_id"], "form_id": r["form_id"], "category": r["category"], "values": json.loads(r["data_json"] or "{}")}


def delete_draft(conn, user: User, draft_id: str):
    conn.execute("DELETE FROM entry_drafts WHERE draft_id = ? AND owner_id = ?", (draft_id, user.id))


# ------------------------------------------------------------------------------------------------ a student's placement record
def placement_form() -> List[Dict[str, Any]]:
    """The placement questions grouped in the steps the student sees (the first group is 'about you', the last is 'consent', those between belong to each offer)."""
    sections: List[Dict[str, Any]] = []
    for q in ingest.specs()["placement"]["questions"]:
        if q["type"] == "section":
            sections.append({"title": q["q"], "fields": []})
        elif sections:
            sections[-1]["fields"].append({"key": q["key"], "q": q["q"], "type": q["type"], "req": bool(q.get("req")), "help": q.get("help"), "choices": q.get("choices")})
    return sections


def my_placement(conn, user: User) -> Dict[str, Any]:
    from backend.master import placements
    sections = placement_form()
    rec = conn.execute("SELECT item_id, status, reason, ay_id, answers_json FROM staged_items WHERE form_id = 'placement' AND roll_no = ? ORDER BY updated_at DESC LIMIT 1", (user.id,)).fetchone()
    record = None
    if rec:
        keyed = placements.keyed(json.loads(rec["answers_json"]))
        offer_keys = {f["key"] for s in sections[1:-1] for f in s["fields"]}
        common = {k: v for k, v in (keyed[0] if keyed else {}).items() if k not in offer_keys}
        record = {"status": rec["status"], "reason": rec["reason"], "ay_id": rec["ay_id"], "common": common,
                  "offers": [{k: v for k, v in r.items() if k in offer_keys} for r in keyed if r.get("company")]}
    return {"roll_no": user.id, "sections": sections, "record": record}


def _known_common(conn, roll: str) -> Dict[str, str]:
    """What the class tutor has already recorded for this student (year, opted in or out, reason): the latest pending or approved record, else the live profile."""
    from backend.master import placements
    rec = conn.execute("SELECT answers_json, ay_id FROM staged_items WHERE form_id = 'placement' AND roll_no = ? ORDER BY updated_at DESC LIMIT 1", (roll,)).fetchone()
    if rec:
        keyed = placements.keyed(json.loads(rec["answers_json"]))
        first = keyed[0] if keyed else {}
        return {"ay_id": rec["ay_id"] or first.get("ay_id", ""), "opt_status": first.get("opt_status", ""), "opt_out_reason": first.get("opt_out_reason", "")}
    p = conn.execute("SELECT ay_id, opt_status, opt_out_reason FROM placement_profiles WHERE roll_no = ? ORDER BY ay_id DESC LIMIT 1", (roll,)).fetchone()
    if p:
        return {"ay_id": p["ay_id"], "opt_status": "Opted Out" if p["opt_status"] == "OPTED_OUT" else "Opted In", "opt_out_reason": p["opt_out_reason"] or ""}
    return {}


def submit_placement(conn, user: User, payload: Dict[str, Any]) -> Dict[str, Any]:
    """A student sends their offers and experiences. The year and whether they opted in or out are the class tutor's to record, so the student does not answer
    them; nothing here asks for consent (what students share is shown to juniors, anonymously). The class tutor approves the record."""
    from database.master_db import ay_for
    from datetime import date
    sections = placement_form()
    if len(sections) < 3:
        raise HTTPException(500, "The placement form is not set up")
    qs = {f["key"]: f for s in sections for f in s["fields"]}
    offer_keys = [f["key"] for s in sections[1:-1] for f in s["fields"]]

    def clean(key, value):
        f = qs[key]
        v = str(value if value is not None else "").strip()
        if not v:
            return ""
        if f["type"] == "date" and not parse_date(v):
            raise HTTPException(400, f"'{f['q']}': enter a date like 2026-03-31")
        if f["type"] == "number" and parse_num(v) is None:
            raise HTTPException(400, f"'{f['q']}': enter a number")
        if f["type"] in ("choice", "list") and f.get("choices") and v not in f["choices"]:
            raise HTTPException(400, f"'{f['q']}': choose one of the listed options")
        return v

    offers = []
    for o in payload.get("offers") or []:
        row = {k: clean(k, (o or {}).get(k)) for k in offer_keys}
        if row.get("company"):
            if not row.get("offer_type"):
                raise HTTPException(400, f"Choose the offer type for {row['company']}")
            offers.append(row)
    if not offers:
        raise HTTPException(400, "Add at least one offer: the company and the offer type")
    known = _known_common(conn, user.id)
    common = {"ay_id": known.get("ay_id") or ay_for(date.today()), "opt_status": known.get("opt_status") or "Opted In", "opt_out_reason": known.get("opt_out_reason", ""),
              "consent": (qs["consent"]["choices"] or [""])[0], "authorization_confirmed": "yes"}
    rows = []
    for o in offers:
        row = {qs[k]["q"]: v for k, v in {**common, **o}.items() if v}
        row[qs["roll_no"]["q"]] = user.id
        rows.append(row)
    review._stage_placements(conn, rows)
    item = conn.execute("SELECT item_id, status FROM staged_items WHERE form_id = 'placement' AND source_key = ?", (f"{user.id.upper()}|{common['ay_id']}",)).fetchone()
    if item:
        review.event(conn, item["item_id"], "submitted", user.id, "Entered by the student")
    return {"status": item["status"] if item else "PENDING", "offers": len(offers)}


# ------------------------------------------------------------------------------------------------ the class tutor's record of "about you"
def class_preferences(conn, user: User, ay_id: str, class_id: Optional[int]) -> Dict[str, Any]:
    """Every active student of a class with what the tutor has recorded for the placement year (blank = not recorded yet)."""
    ids = sorted(user.tutor_class_ids)
    cid = class_id if user.is_admin else (class_id if class_id in ids else (ids[0] if ids else None))
    if not cid:
        raise HTTPException(403, "Only a class tutor (or the Admin) records this")
    rows = [dict(r) for r in conn.execute(
        "SELECT s.roll_no, s.full_name, p.opt_status, p.opt_out_reason, "
        "(SELECT COUNT(*) FROM placement_offers o WHERE o.roll_no = s.roll_no AND o.ay_id = ?) AS offers FROM students s "
        "LEFT JOIN placement_profiles p ON p.roll_no = s.roll_no AND p.ay_id = ? WHERE s.status = 'Active' AND s.class_id = ? ORDER BY s.roll_no", (ay_id, ay_id, cid))]
    cls = conn.execute("SELECT class_code FROM classes WHERE class_id = ?", (cid,)).fetchone()
    reasons = next((q.get("choices") for q in ingest.specs()["placement"]["questions"] if q.get("key") == "opt_out_reason"), []) or []
    return {"class_id": cid, "class_code": cls[0] if cls else "", "ay_id": ay_id, "students": rows, "reasons": reasons}


def save_preferences(conn, user: User, ay_id: str, rows: List[Dict[str, Any]]) -> Dict[str, int]:
    from backend.master import placements
    if not re.fullmatch(r"\d{4}-\d{2}", ay_id or ""):
        raise HTTPException(400, "The placement year must look like 2026-27")
    saved = 0
    for r in rows:
        roll = str(r.get("roll_no", "")).strip().upper()
        status = {"Opted In": "OPTED_IN", "Opted Out": "OPTED_OUT"}.get(r.get("opt_status"))
        if not roll or not status:
            continue
        if not placements._can_edit_student(conn, user, roll):
            raise HTTPException(403, f"{roll} is not in your class")
        if status == "OPTED_OUT" and conn.execute("SELECT 1 FROM placement_offers WHERE roll_no = ? AND ay_id = ?", (roll, ay_id)).fetchone():
            raise HTTPException(400, f"{roll} already has an offer recorded, so cannot be marked as opted out")
        conn.execute("INSERT INTO placement_profiles (roll_no, ay_id, opt_status, opt_out_reason, updated_by) VALUES (?,?,?,?,?) "
                     "ON CONFLICT(roll_no, ay_id) DO UPDATE SET opt_status = excluded.opt_status, opt_out_reason = excluded.opt_out_reason, updated_by = excluded.updated_by",
                     (roll, ay_id, status, (r.get("opt_out_reason") or None) if status == "OPTED_OUT" else None, user.id))
        saved += 1
    return {"saved": saved}
