"""Review: responses pulled from the Google Sheets wait here until an authority approves them.

  PENDING --approve / edit & approve--> APPROVED   (only now is anything written to the live tables)
  PENDING --reject with reason--------> RETURNED   (sent to a faculty member the approver picks; form items only)
  PENDING --reject without reason-----> REJECTED
  RETURNED --faculty corrects & resubmits--> PENDING
  APPROVED --revoke--> PENDING (the live record is taken out again)      REJECTED --reopen--> PENDING

Who decides: the five submission forms -> Admin or HoD; a student's placement record -> the tutor of that student's class
(the Admin steps in only when the class has no tutor). The rest of the application reads only the live tables, so a response
that has not been approved cannot show up in any list, chart, profile, diary or newsletter.
"""
import hashlib
import json
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException

from backend.master import ingest, placements
from backend.master.auth import User
from backend.master.common import norm_header
from database.master_db import audit, ay_for, ensure_ay

PLACEMENT = "placement"
LABELS = {"form_student": "Student achievement", "form_research": "Research & innovation", "form_faculty": "Faculty achievement",
          "form_departmental": "Department highlight", "form_industry": "Industry & outreach", PLACEMENT: "Placement"}


# ---------------------------------------------------------------- small helpers
def _j(v) -> str:
    return json.dumps(v, ensure_ascii=False)


def _l(text, default=None):
    try:
        return json.loads(text) if text else (default if default is not None else [])
    except ValueError:
        return default if default is not None else []


def _now() -> str:
    return datetime.now().isoformat(sep=" ", timespec="seconds")


def event(conn, item_id: int, action: str, actor: Optional[str], note: Optional[str] = None, detail: Any = None):
    conn.execute("INSERT INTO review_events (item_id, action, actor, note, detail_json) VALUES (?,?,?,?,?)",
                 (item_id, action, actor, note or None, _j(detail) if detail is not None else None))


def _spec_questions(form_id: str) -> List[Dict[str, Any]]:
    return (ingest.specs()["placement"] if form_id == PLACEMENT else ingest.specs()["forms"][form_id])["questions"]


def _titles(q: Dict[str, Any]) -> List[str]:
    return [q["q"], *q.get("aliases", [])]


def _faculty_name(conn, emp: Optional[str]) -> Optional[str]:
    row = conn.execute("SELECT full_name FROM faculty WHERE emp_id = ?", (emp,)).fetchone() if emp else None
    return row[0] if row else None


def _hash_rows(rows: List[Dict[str, Any]]) -> str:
    canon = [sorted((norm_header(k), str(v).strip()) for k, v in r.items() if v is not None and str(v).strip()) for r in rows]
    return hashlib.sha256(_j(canon).encode()).hexdigest()


def _clean_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    return [{k: ("" if v is None else str(v).strip()) for k, v in r.items() if k} for r in rows]


# ---------------------------------------------------------------- staging: what a sheet pull does with the rows it reads
def stage_rows(conn, form_id: str, rows: List[Dict[str, Any]]) -> Dict[str, int]:
    """Put the sheet's rows into the review queue. A response seen before is not added again; one that is already live
    (uploaded earlier from Excel) is recorded as approved without bothering anyone."""
    rows = [r for r in _clean_rows(rows) if any(r.values())]
    return _stage_placements(conn, rows) if form_id == PLACEMENT else _stage_forms(conn, form_id, rows)


def _stage_forms(conn, form_id: str, rows: List[Dict[str, str]]) -> Dict[str, int]:
    counts = {"new": 0, "updated": 0, "already_in_system": 0, "unchanged": 0}
    for row in rows:
        n = {norm_header(k): v for k, v in row.items()}
        ts, email = n.get("timestamp", ""), n.get("email address", "").lower()
        key = f"{ts}|{email}" if (ts or email) else "hash:" + ingest.row_hash(form_id, row)
        digest = _hash_rows([row])
        have = conn.execute("SELECT item_id, status, content_hash FROM staged_items WHERE form_id = ? AND source_key = ?", (form_id, key)).fetchone()
        pv = ingest.preview_row(conn, form_id, row)
        info = ingest.summarize(form_id, row)
        if have:
            if have["status"] == "PENDING" and have["content_hash"] != digest:       # changed in the sheet before anyone reviewed it
                conn.execute("UPDATE staged_items SET answers_json = ?, content_hash = ?, title = ?, category = ?, event_date = ?, warnings_json = ?, blockers_json = ?, "
                             "updated_at = CURRENT_TIMESTAMP WHERE item_id = ?", (_j([row]), digest, info["title"], info["category"], info["event_date"], _j(pv["warnings"]), _j(pv["errors"]), have["item_id"]))
                event(conn, have["item_id"], "updated", "sheet", "The response was changed in the Google Sheet before it was reviewed")
                counts["updated"] += 1
            else:
                counts["unchanged"] += 1
            continue
        submitter = ingest.guess_submitter(conn, form_id, row)
        cur = conn.execute(
            "INSERT INTO staged_items (kind, form_id, source_key, content_hash, answers_json, original_json, status, title, category, event_date, submitter_email, submitter_emp_id, "
            "warnings_json, blockers_json) VALUES ('FORM',?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (form_id, key, digest, _j([row]), _j([row]), "PENDING", info["title"], info["category"], info["event_date"], n.get("email address") or None, submitter, _j(pv["warnings"]), _j(pv["errors"])))
        item_id = cur.lastrowid
        if pv["already_live"]:                                                       # same response was uploaded from Excel earlier: nothing to review
            live = conn.execute("SELECT submission_id FROM form_submissions WHERE source_row_hash = ?", (ingest.row_hash(form_id, row),)).fetchone()
            conn.execute("UPDATE staged_items SET status = 'APPROVED', submission_id = ?, warnings_json = '[]', blockers_json = '[]', decided_by = 'system', decided_at = ? WHERE item_id = ?",
                         (live[0] if live else None, _now(), item_id))
            event(conn, item_id, "already_live", "sheet", "Already in the system from an earlier upload; recorded as approved")
            counts["already_in_system"] += 1
        else:
            event(conn, item_id, "pulled", "sheet", "Pulled from the Google Sheet")
            counts["new"] += 1
    return counts


def _stage_placements(conn, rows: List[Dict[str, str]]) -> Dict[str, int]:
    """One review item per student per placement year, holding all of that student's rows (one per offer)."""
    counts = {"new": 0, "updated": 0, "already_in_system": 0, "unchanged": 0, "skipped": 0}
    default_ay = ay_for(date.today())
    groups: Dict[Tuple[str, str], List[Dict[str, str]]] = {}
    for row in rows:
        k = placements.keyed([row])
        if not k or not k[0].get("roll_no"):
            counts["skipped"] += 1                                                   # no roll number: nothing to attach it to
            continue
        groups.setdefault((k[0]["roll_no"].upper(), k[0].get("ay_id") or default_ay), []).append(row)
    for (roll, ay), grp in groups.items():
        key, digest = f"{roll}|{ay}", _hash_rows(grp)
        have = conn.execute("SELECT item_id, status, content_hash FROM staged_items WHERE form_id = ? AND source_key = ?", (PLACEMENT, key)).fetchone()
        if have and have["content_hash"] == digest:
            counts["unchanged"] += 1
            continue
        keyed = placements.keyed(grp)
        pv = placements.preview_student(conn, keyed, roll)
        warnings = list(pv["warnings"])
        title = f"{pv['student_name'] or roll} ({roll}) - {ay}"
        if have:
            # the student sent more rows (another offer) or corrected something: whatever was decided, the new version needs a decision
            conn.execute("UPDATE staged_items SET answers_json = ?, content_hash = ?, status = 'PENDING', title = ?, class_id = ?, warnings_json = ?, blockers_json = ?, "
                         "reason = NULL, assigned_emp_id = NULL, updated_at = CURRENT_TIMESTAMP WHERE item_id = ?",
                         (_j(grp), digest, title, pv["class_id"], _j(warnings), _j(pv["blockers"]), have["item_id"]))
            event(conn, have["item_id"], "updated", "sheet", "New or changed rows in the Google Sheet: needs approval again" if have["status"] != "PENDING" else "Rows changed in the Google Sheet before review")
            counts["updated"] += 1
        else:
            item_id = conn.execute(
                "INSERT INTO staged_items (kind, form_id, source_key, content_hash, answers_json, original_json, status, title, category, roll_no, ay_id, class_id, warnings_json, blockers_json) "
                "VALUES ('PLACEMENT',?,?,?,?,?,'PENDING',?,?,?,?,?,?,?)", (PLACEMENT, key, digest, _j(grp), _j(grp), title, "; ".join(pv["summary"])[:300], roll, ay, pv["class_id"], _j(warnings), _j(pv["blockers"]))).lastrowid
            event(conn, item_id, "pulled", "sheet", "Pulled from the Google Sheet")
            counts["new"] += 1
    return counts


# ---------------------------------------------------------------- who may do what
def _is_approver_of_forms(user: User) -> bool:
    return user.is_admin or "HOD" in user.roles


def _class_has_tutor(conn, class_id: Optional[int]) -> bool:
    row = conn.execute("SELECT tutor_id FROM classes WHERE class_id = ?", (class_id,)).fetchone() if class_id else None
    return bool(row and row[0])


def can_decide(conn, user: User, it: Dict[str, Any]) -> bool:
    if user.kind != "STAFF":
        return False
    if it["kind"] == "FORM":
        return _is_approver_of_forms(user)
    if it["class_id"] in user.tutor_class_ids and it["class_id"] is not None:
        return True
    return user.is_admin and not _class_has_tutor(conn, it["class_id"])


def can_resubmit(user: User, it: Dict[str, Any]) -> bool:
    return it["status"] == "RETURNED" and it["kind"] == "FORM" and it["assigned_emp_id"] == user.id


def can_view(conn, user: User, it: Dict[str, Any]) -> bool:
    return (user.all_access or can_decide(conn, user, it) or can_resubmit(user, it) or it["submitter_emp_id"] == user.id
            or (it["kind"] == "PLACEMENT" and it["class_id"] in user.class_ids and it["class_id"] is not None))


def _load(conn, item_id: int) -> Dict[str, Any]:
    r = conn.execute("SELECT * FROM staged_items WHERE item_id = ?", (item_id,)).fetchone()
    if not r:
        raise HTTPException(404, "That response was not found")
    d = dict(r)
    d["answers"], d["original"] = _l(d.pop("answers_json")), _l(d.pop("original_json"))
    d["warnings"], d["blockers"] = _l(d.pop("warnings_json")), _l(d.pop("blockers_json"))
    return d


def _decider_sql(conn, user: User) -> Tuple[Optional[str], list]:
    parts, args = [], []
    if _is_approver_of_forms(user):
        parts.append("i.kind = 'FORM'")
    if user.is_admin:
        parts.append("(i.kind = 'PLACEMENT' AND (i.class_id IS NULL OR i.class_id IN (SELECT class_id FROM classes WHERE tutor_id IS NULL)))")
    if user.tutor_class_ids:
        ids = sorted(user.tutor_class_ids)
        parts.append(f"(i.kind = 'PLACEMENT' AND i.class_id IN ({','.join('?' * len(ids))}))")
        args += ids
    return ("(" + " OR ".join(parts) + ")" if parts else None), args


# ---------------------------------------------------------------- lists
def summary(conn, user: User) -> Dict[str, int]:
    """Numbers for the badges."""
    clause, args = _decider_sql(conn, user)
    to_review = conn.execute(f"SELECT COUNT(*) FROM staged_items i WHERE i.status = 'PENDING' AND {clause}", args).fetchone()[0] if clause else 0
    flagged = conn.execute(f"SELECT COUNT(*) FROM staged_items i WHERE i.status = 'PENDING' AND {clause} AND (i.warnings_json != '[]' OR i.blockers_json != '[]')", args).fetchone()[0] if clause else 0
    mine = conn.execute("SELECT COUNT(*) FROM staged_items WHERE status = 'RETURNED' AND assigned_emp_id = ?", (user.id,)).fetchone()[0]
    out = conn.execute(f"SELECT COUNT(*) FROM staged_items i WHERE i.status = 'RETURNED' AND {clause}", args).fetchone()[0] if clause else 0
    return {"to_review": to_review, "flagged": flagged, "returned_to_me": mine, "returned_open": out, "badge": to_review + mine}


def _card(conn, user: User, d: Dict[str, Any], names: Dict[str, str]) -> Dict[str, Any]:
    return {
        "item_id": d["item_id"], "kind": d["kind"], "form_id": d["form_id"], "label": LABELS.get(d["form_id"], d["form_id"]), "status": d["status"], "title": d["title"] or "(no title)",
        "category": d["category"], "event_date": d["event_date"], "submitter": names.get(d["submitter_emp_id"]) or d["submitter_email"], "roll_no": d["roll_no"], "ay_id": d["ay_id"],
        "assigned_to": names.get(d["assigned_emp_id"]), "assigned_emp_id": d["assigned_emp_id"], "reason": d["reason"], "decided_by": d["decided_by"], "decided_at": d["decided_at"],
        "warnings": d["warnings"], "blockers": d["blockers"], "updated_at": d["updated_at"], "can_decide": can_decide(conn, user, d)}


def list_items(conn, user: User, scope: str, f: Dict[str, Any], limit: int = 100, offset: int = 0) -> Dict[str, Any]:
    clause, cargs = _decider_sql(conn, user)
    where, args = ["1=1"], []
    if scope == "review":
        if not clause:
            return {"total": 0, "items": []}
        where += ["i.status = 'PENDING'", clause]
        args += cargs
    elif scope == "returned":
        who = ["i.assigned_emp_id = ?"]
        args.append(user.id)
        if clause:
            who.append(clause)
            args += cargs
        where += ["i.status = 'RETURNED'", "(" + " OR ".join(who) + ")"]
    elif scope == "decided":
        if not clause:
            return {"total": 0, "items": []}
        where += ["i.status IN ('APPROVED','REJECTED')", clause]
        args += cargs
    elif scope == "mine":
        where += ["i.kind = 'FORM'", "i.submitter_emp_id = ?"]
        args.append(user.id)
    else:
        raise HTTPException(400, "Unknown list")
    if f.get("form_id"):
        where.append("i.form_id = ?")
        args.append(f["form_id"])
    if f.get("q"):
        where.append("(i.title LIKE ? OR i.category LIKE ? OR i.roll_no LIKE ?)")
        args += [f"%{f['q']}%"] * 3
    if f.get("flagged"):
        where.append("(i.warnings_json != '[]' OR i.blockers_json != '[]')")
    if f.get("status") and scope == "decided":
        where.append("i.status = ?")
        args.append(f["status"])
    order = "i.created_at ASC, i.item_id ASC" if scope == "review" else "i.updated_at DESC, i.item_id DESC"
    base = f"FROM staged_items i WHERE {' AND '.join(where)}"
    total = conn.execute(f"SELECT COUNT(*) {base}", args).fetchone()[0]
    names = {r[0]: r[1] for r in conn.execute("SELECT emp_id, full_name FROM faculty")}
    items = []
    for r in conn.execute(f"SELECT i.* {base} ORDER BY {order} LIMIT ? OFFSET ?", args + [limit, offset]):
        d = dict(r)
        d["answers"], d["original"] = [], []
        d["warnings"], d["blockers"] = _l(d.pop("warnings_json")), _l(d.pop("blockers_json"))
        items.append(_card(conn, user, d, names))
    return {"total": total, "items": items}


# ---------------------------------------------------------------- one item, laid out for the editor
def _field_value(row: Dict[str, str], q: Dict[str, Any]) -> Tuple[str, Optional[str]]:
    """(value, column title it came from)"""
    byn = {norm_header(k): k for k in row}
    for t in _titles(q):
        if norm_header(t) in byn:
            return row[byn[norm_header(t)]], byn[norm_header(t)]
    return "", None


def _layout(form_id: str, rows: List[Dict[str, str]], originals: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    out = []
    for n, row in enumerate(rows):
        orig = originals[n] if n < len(originals) else {}
        fields, seen = [], set()
        for q in _spec_questions(form_id):
            if q["type"] == "section":
                fields.append({"type": "section", "q": q["q"]})
                continue
            if not q.get("key"):
                continue
            value, col = _field_value(row, q)
            ov, _ = _field_value(orig, q)
            if col:
                seen.add(col)
            fields.append({"q": q["q"], "type": q["type"], "req": bool(q.get("req")), "help": q.get("help"), "choices": q.get("choices"), "value": value, "original": ov,
                           "changed": norm_header(value) != norm_header(ov)})
        meta = {k: v for k, v in row.items() if norm_header(k) in ("timestamp", "email address") and v}
        extras = [{"q": k, "value": v} for k, v in row.items() if k not in seen and k not in meta and v]
        out.append({"fields": fields, "meta": meta, "extras": extras})
    return out


def get_item(conn, user: User, item_id: int) -> Dict[str, Any]:
    it = _load(conn, item_id)
    if not can_view(conn, user, it):
        raise HTTPException(403, "This response is not yours to see")
    names = {r[0]: r[1] for r in conn.execute("SELECT emp_id, full_name FROM faculty")}
    card = _card(conn, user, it, names)
    timeline = [{"action": r["action"], "actor": names.get(r["actor"]) or r["actor"], "note": r["note"], "detail": _l(r["detail_json"], None), "at": r["at"]}
                for r in conn.execute("SELECT * FROM review_events WHERE item_id = ? ORDER BY event_id", (item_id,))]
    pv = preview_answers(conn, it["form_id"], it["answers"])
    if it["status"] in ("APPROVED", "REJECTED"):                          # problems matter while something is still to be decided
        pv = {**pv, "warnings": [], "blockers": []}
    suggested = it["submitter_emp_id"] or None
    return {"item": card, "rows": _layout(it["form_id"], it["answers"], it["original"]), "people": pv.get("people", []), "summary": pv.get("summary", []),
            "warnings": pv["warnings"], "blockers": pv["blockers"], "timeline": timeline,
            "permissions": {"decide": can_decide(conn, user, it) and it["status"] in ("PENDING", "RETURNED"), "revoke": can_decide(conn, user, it) and it["status"] == "APPROVED",
                            "reopen": can_decide(conn, user, it) and it["status"] == "REJECTED", "resubmit": can_resubmit(user, it), "can_return": it["kind"] == "FORM"},
            "faculty": [{"emp_id": e, "full_name": n} for e, n in sorted(names.items(), key=lambda x: x[1]) if e != "ADMIN"], "suggested_send_to": suggested,
            "student_name": (conn.execute("SELECT full_name FROM students WHERE roll_no = ?", (it["roll_no"],)).fetchone() or [None])[0] if it["roll_no"] else None}


def preview_answers(conn, form_id: str, rows: List[Dict[str, str]]) -> Dict[str, Any]:
    """Fresh problems and resolved names for the answers as they currently stand (used while editing). Saves nothing."""
    rows = _clean_rows(rows)
    if form_id == PLACEMENT:
        keyed = placements.keyed(rows)
        roll = next((r["roll_no"].upper() for r in keyed if r.get("roll_no")), "")
        if not roll:
            return {"warnings": [], "blockers": ["Roll number is missing"], "people": [], "summary": []}
        pv = placements.preview_student(conn, keyed, roll)
        who = [{"label": "Student", "items": [{"text": f"{pv['student_name']} ({roll})" if pv["student_name"] else roll, "ok": bool(pv["student_name"])}]}]
        return {"warnings": pv["warnings"], "blockers": pv["blockers"], "people": who, "summary": pv["summary"]}
    if form_id not in ingest.specs()["forms"]:
        raise HTTPException(400, "Unknown form")
    pv = ingest.preview_row(conn, form_id, rows[0] if rows else {})
    return {"warnings": pv["warnings"], "blockers": pv["errors"], "people": pv["people"], "summary": [], "already_live": pv["already_live"]}


# ---------------------------------------------------------------- editing
def _apply_edits(form_id: str, rows: List[Dict[str, str]], edits: List[Dict[str, Any]]) -> Tuple[List[Dict[str, str]], List[Dict[str, Any]]]:
    """Merge the edited answers into the stored ones. edits[i] = {question title: new value}; only those titles are touched.
    Returns (new rows, list of {row, field, from, to})."""
    qs = [q for q in _spec_questions(form_id) if q["type"] != "section" and q.get("key")]
    out, changes = [], []
    for n, row in enumerate(rows):
        row = dict(row)
        for title, new in (edits[n] if n < len(edits) else {}).items():
            q = next((q for q in qs if norm_header(title) in {norm_header(t) for t in _titles(q)}), None)
            if not q:
                continue
            old, col = _field_value(row, q)
            new = "" if new is None else str(new).strip()
            if norm_header(old) == norm_header(new):
                continue
            row[col or q["q"]] = new
            changes.append({"row": n + 1, "field": q["q"], "from": old, "to": new})
        out.append(row)
    return out, changes


def _need_state(it, *allowed):
    if it["status"] not in allowed:
        raise HTTPException(409, f"This response is already {it['status'].lower()}")


def _save_answers(conn, it, rows):
    info = ingest.summarize(it["form_id"], rows[0]) if it["kind"] == "FORM" else {"title": it["title"], "category": it["category"], "event_date": it["event_date"]}
    conn.execute("UPDATE staged_items SET answers_json = ?, title = ?, category = ?, event_date = ?, updated_at = CURRENT_TIMESTAMP WHERE item_id = ?",
                 (_j(rows), info["title"], info["category"], info["event_date"], it["item_id"]))


def _refresh_flags(conn, it, rows):
    pv = preview_answers(conn, it["form_id"], rows)
    conn.execute("UPDATE staged_items SET warnings_json = ?, blockers_json = ? WHERE item_id = ?", (_j(pv["warnings"]), _j(pv["blockers"]), it["item_id"]))
    if it["kind"] == "PLACEMENT":
        keyed = placements.keyed(rows)
        roll = next((r["roll_no"].upper() for r in keyed if r.get("roll_no")), it["roll_no"])
        ay = next((r["ay_id"] for r in keyed if r.get("ay_id")), it["ay_id"])
        conn.execute("UPDATE staged_items SET roll_no = ?, ay_id = ?, class_id = ? WHERE item_id = ?", (roll, ay, placements.student_class(conn, roll), it["item_id"]))
    return pv


def _clean_edits(edits) -> List[Dict[str, Any]]:
    if edits is None:
        return []
    return [edits] if isinstance(edits, dict) else list(edits)


# ---------------------------------------------------------------- decisions
def approve(conn, user: User, item_id: int, edits=None, note: Optional[str] = None) -> Dict[str, Any]:
    """Approve as it is, or (edits given) edit and approve. Only now is the live record written."""
    it = _load(conn, item_id)
    if not can_decide(conn, user, it):
        raise HTTPException(403, "You are not the approver for this response")
    _need_state(it, "PENDING", "RETURNED")
    conn.execute("SAVEPOINT approving")
    try:
        rows, changes = _apply_edits(it["form_id"], it["answers"], _clean_edits(edits))
        if changes:
            _save_answers(conn, it, rows)
            event(conn, item_id, "edited", user.id, None, changes)
        pv = _refresh_flags(conn, it, rows)
        if pv["blockers"]:
            raise HTTPException(400, "It cannot be approved yet: " + "; ".join(pv["blockers"]))
        submission_id = None
        if it["kind"] == "FORM":
            res = ingest.ingest_row(conn, it["form_id"], rows[0])
            if res["status"] == "error":
                raise HTTPException(400, "It cannot be approved yet: " + "; ".join(res["errors"]))
            submission_id = res.get("submission_id")
        else:
            keyed = placements.keyed(rows)
            roll = next((r["roll_no"].upper() for r in keyed if r.get("roll_no")), "")
            ay = next((r["ay_id"] for r in keyed if r.get("ay_id")), None) or it["ay_id"]
            stats = placements.apply_rows(conn, user, {roll: keyed}, ay)
            if stats["errors"]:
                raise HTTPException(400, "It cannot be approved: " + stats["errors"][0]["message"])
        conn.execute("UPDATE staged_items SET status = 'APPROVED', decided_by = ?, decided_at = ?, submission_id = ?, assigned_emp_id = NULL, updated_at = CURRENT_TIMESTAMP WHERE item_id = ?",
                     (user.id, _now(), submission_id, item_id))
        event(conn, item_id, "approved_edited" if changes else "approved", user.id, note)
        audit(conn, user.id, "REVIEW_APPROVE", "staged_items", str(item_id), it["title"])
        conn.execute("RELEASE approving")
    except Exception:
        conn.execute("ROLLBACK TO approving")
        conn.execute("RELEASE approving")
        raise
    return {"status": "APPROVED", "edited": bool(changes), "changes": len(changes)}


def reject(conn, user: User, item_id: int, reason: Optional[str] = None, send_to: Optional[str] = None) -> Dict[str, Any]:
    """With a reason a form response goes back to the faculty member chosen (RETURNED); without one it is simply rejected.
    A placement record has no one to return it to, so it is rejected (the reason, if given, stays on it)."""
    it = _load(conn, item_id)
    if not can_decide(conn, user, it):
        raise HTTPException(403, "You are not the approver for this response")
    _need_state(it, "PENDING", "RETURNED")
    reason = (reason or "").strip() or None
    if reason and it["kind"] == "FORM":
        if not send_to:
            raise HTTPException(400, "Choose the faculty member this should be sent back to")
        if not conn.execute("SELECT 1 FROM faculty WHERE emp_id = ? AND status = 'Active'", (send_to,)).fetchone():
            raise HTTPException(400, "That faculty member was not found or is not active")
        conn.execute("UPDATE staged_items SET status = 'RETURNED', reason = ?, assigned_emp_id = ?, decided_by = ?, decided_at = ?, updated_at = CURRENT_TIMESTAMP WHERE item_id = ?",
                     (reason, send_to, user.id, _now(), item_id))
        event(conn, item_id, "returned", user.id, reason, {"to": send_to, "to_name": _faculty_name(conn, send_to)})
        audit(conn, user.id, "REVIEW_RETURN", "staged_items", str(item_id), f"to {send_to}")
        return {"status": "RETURNED", "assigned_to": _faculty_name(conn, send_to)}
    conn.execute("UPDATE staged_items SET status = 'REJECTED', reason = ?, assigned_emp_id = NULL, decided_by = ?, decided_at = ?, updated_at = CURRENT_TIMESTAMP WHERE item_id = ?",
                 (reason, user.id, _now(), item_id))
    event(conn, item_id, "rejected", user.id, reason)
    audit(conn, user.id, "REVIEW_REJECT", "staged_items", str(item_id), it["title"])
    return {"status": "REJECTED"}


def resubmit(conn, user: User, item_id: int, edits, note: Optional[str] = None) -> Dict[str, Any]:
    """The faculty member the item was returned to corrects it and sends it back for approval."""
    it = _load(conn, item_id)
    if not can_resubmit(user, it):
        raise HTTPException(403, "This was not returned to you")
    rows, changes = _apply_edits(it["form_id"], it["answers"], _clean_edits(edits))
    note = (note or "").strip() or None
    if not changes and not note:
        raise HTTPException(400, "Change what was asked, or say in a note why it is right as it stands")
    if changes:
        _save_answers(conn, it, rows)
        event(conn, item_id, "edited", user.id, None, changes)
    pv = _refresh_flags(conn, it, rows)
    if pv["blockers"]:
        raise HTTPException(400, "Please fix this first: " + "; ".join(pv["blockers"]))
    conn.execute("UPDATE staged_items SET status = 'PENDING', assigned_emp_id = NULL, updated_at = CURRENT_TIMESTAMP WHERE item_id = ?", (item_id,))
    event(conn, item_id, "resubmitted", user.id, note)
    audit(conn, user.id, "REVIEW_RESUBMIT", "staged_items", str(item_id), it["title"])
    return {"status": "PENDING", "changes": len(changes)}


def revoke(conn, user: User, item_id: int) -> Dict[str, Any]:
    """Take an approved response back out of the live data (it becomes pending again)."""
    it = _load(conn, item_id)
    if not can_decide(conn, user, it):
        raise HTTPException(403, "You are not the approver for this response")
    _need_state(it, "APPROVED")
    if it["kind"] == "FORM":
        if it["submission_id"]:
            row = conn.execute("SELECT newsletter_entry_id FROM form_submissions WHERE submission_id = ?", (it["submission_id"],)).fetchone()
            conn.execute("DELETE FROM form_submissions WHERE submission_id = ?", (it["submission_id"],))       # the detail rows go with it
            if row and row[0]:
                from database.db_manager import get_connection
                n = get_connection()
                try:
                    n.execute("DELETE FROM canonical_entries WHERE entry_id = ?", (row[0],))
                    n.commit()
                finally:
                    n.close()
    else:
        for t in ("placement_offers", "interview_experiences", "internship_experiences", "placement_profiles"):
            conn.execute(f"DELETE FROM {t} WHERE roll_no = ? AND ay_id = ?", (it["roll_no"], it["ay_id"]))
    conn.execute("UPDATE staged_items SET status = 'PENDING', submission_id = NULL, decided_by = NULL, decided_at = NULL, updated_at = CURRENT_TIMESTAMP WHERE item_id = ?", (item_id,))
    event(conn, item_id, "revoked", user.id, "Approval withdrawn; the record is out of the application until approved again")
    audit(conn, user.id, "REVIEW_REVOKE", "staged_items", str(item_id), it["title"])
    return {"status": "PENDING"}


def reopen(conn, user: User, item_id: int) -> Dict[str, Any]:
    it = _load(conn, item_id)
    if not can_decide(conn, user, it):
        raise HTTPException(403, "You are not the approver for this response")
    _need_state(it, "REJECTED")
    conn.execute("UPDATE staged_items SET status = 'PENDING', decided_by = NULL, decided_at = NULL, reason = NULL, updated_at = CURRENT_TIMESTAMP WHERE item_id = ?", (item_id,))
    event(conn, item_id, "reopened", user.id, "Brought back for review")
    return {"status": "PENDING"}


def bulk_approve(conn, user: User, ids: Optional[List[int]] = None, all_clean: bool = False, form_id: Optional[str] = None) -> Dict[str, Any]:
    """Approve many at once. all_clean = every pending response this person may decide that has nothing to look at."""
    if all_clean:
        found = list_items(conn, user, "review", {"form_id": form_id}, limit=100000)["items"]
        ids = [c["item_id"] for c in found if not c["warnings"] and not c["blockers"]]
    approved, skipped = 0, []
    for item_id in ids or []:
        try:
            approve(conn, user, int(item_id))
            approved += 1
        except HTTPException as e:
            skipped.append({"item_id": item_id, "reason": e.detail})
    return {"approved": approved, "skipped": skipped}
