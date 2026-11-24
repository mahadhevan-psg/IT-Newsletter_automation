"""Form definitions that the Admin can edit, with versions.

What a data-entry form asks (its categories and fields) is DATA, not code. The published definition of each form is stored in the
master database (table form_definitions). Everything that needs to know the questions (the entry screen, the review screen, the importer,
reports, profile pages, the newsletter mappings) reads them through ingest.specs(), which returns the published definitions, so a change the
Admin publishes reaches all of them at once.

The Admin works on a DRAFT copy: add, change, move, retire fields; add, rename, move, delete categories; add newsletter sections. Publishing
validates the draft, makes it the published version (the earlier one is archived and can be restored), and rewrites the newsletter studio's
mappings. Entries keep the answers they were saved with, so older data stays readable after any change: a retired field or category is only
hidden from new entries (its questions stay in the definition, marked legacy, so old answers still import and show).
"""
import copy
import json
import os
import re
import sqlite3
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SPEC_FILE = os.path.join(ROOT, "config", "master_forms.json")
SECTIONS_FILE = os.path.join(ROOT, "config", "section_categories.json")
FORM_IDS = ["form_student", "form_research", "form_faculty", "form_departmental", "form_industry"]
PLACEMENT = "placement"
SECTIONS = "_sections"
ALL_IDS = FORM_IDS + [PLACEMENT, SECTIONS]

# What a field can be (what the entry screen draws) and what a field can mean to the newsletter
FIELD_TYPES = {"text": "Short text", "para": "Long text", "number": "Number", "date": "Date", "choice": "Pick one (buttons)", "list": "Pick one (drop-down)", "url": "Link",
               "faculty": "Faculty member", "roster_roll": "Students (roll numbers)", "roster_any": "People (ID - name per line)", "photo": "Photo"}
NEWSLETTER_ROLES = {"title": "Heading", "author_or_person": "Byline (people)", "organization_or_venue": "Venue / organisation", "event_date": "Date",
                    "impact_or_indexing": "Tag line", "grant_or_prize_amount": "Highlight line", "description": "Description", "badge_tag": "Badge"}
DESCRIPTION_KEY = {"form_student": "abstract", "form_research": "abstract", "form_faculty": "description", "form_departmental": "overview", "form_industry": "summary_outcomes"}

_cache: Dict[str, Any] = {}
_gen = {"n": 0}


# ------------------------------------------------------------------------------------------------ reading the published definitions
def _read_file(path: str) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _ids(spec: Dict[str, Any]) -> Dict[str, Any]:
    """Give every question a stable id ('fid') the editor refers to; existing ones are kept."""
    used = {q["fid"] for q in spec["questions"] if q.get("fid")}
    for q in spec["questions"]:
        if q["type"] == "section" or q.get("fid"):
            continue
        base, n = q.get("key") or "q", 1
        fid = base
        while fid in used:
            n += 1
            fid = f"{base}.{n}"
        q["fid"] = fid
        used.add(fid)
    return spec


def _from_rows(rows) -> Dict[str, Any]:
    data = {"version": "3.0", "forms": {}, "placement": None, "sections": None}
    for form_id, spec_json in rows:
        spec = json.loads(spec_json)
        if form_id == PLACEMENT:
            data["placement"] = spec
        elif form_id == SECTIONS:
            data["sections"] = spec
        else:
            data["forms"][form_id] = spec
    return data


def current_specs() -> Dict[str, Any]:
    """The published definitions: {'forms': {...}, 'placement': {...}, 'sections': {...}}. Falls back to the shipped file when the database has none."""
    from database.master_db import db_path
    path = db_path()
    hit = _cache.get(path)
    if hit and hit[0] == _gen["n"]:
        return hit[1]
    data = None
    if os.path.exists(path):
        try:
            conn = sqlite3.connect(path)
            rows = conn.execute("SELECT form_id, spec_json FROM form_definitions WHERE status = 'published' ORDER BY form_id").fetchall()
            conn.close()
            if rows:
                data = _from_rows(rows)
        except sqlite3.Error:
            data = None
    if data is None or not data["forms"] or not data["placement"]:
        shipped = _read_file(SPEC_FILE)
        data = {"version": shipped.get("version"), "forms": {k: _ids(v) for k, v in shipped["forms"].items()}, "placement": shipped["placement"],
                "sections": _read_file(SECTIONS_FILE) if os.path.exists(SECTIONS_FILE) else {"sections": []}}
    _cache[path] = (_gen["n"], data)
    return data


def invalidate() -> None:
    _gen["n"] += 1


def invalidate_after_commit() -> None:
    from database.master_db import after_commit
    after_commit(invalidate)


def ensure_seeded(conn) -> None:
    """A database with no definitions yet starts from the shipped ones (version 1, published)."""
    if conn.execute("SELECT 1 FROM form_definitions LIMIT 1").fetchone():
        return
    shipped = _read_file(SPEC_FILE)
    docs = {fid: _ids(spec) for fid, spec in shipped["forms"].items()}
    docs[PLACEMENT] = shipped["placement"]
    docs[SECTIONS] = _read_file(SECTIONS_FILE) if os.path.exists(SECTIONS_FILE) else {"sections": []}
    for form_id, spec in docs.items():
        conn.execute("INSERT INTO form_definitions (form_id, version, status, spec_json, note, created_by, published_at) VALUES (?, 1, 'published', ?, 'Shipped definition', 'system', CURRENT_TIMESTAMP)",
                     (form_id, json.dumps(spec, ensure_ascii=False)))
    invalidate_after_commit()


# ------------------------------------------------------------------------------------------------ the draft
def _row(conn, form_id: str, status: str):
    return conn.execute("SELECT * FROM form_definitions WHERE form_id = ? AND status = ? ORDER BY version DESC LIMIT 1", (form_id, status)).fetchone()


def event(conn, form_id: Optional[str], action: str, actor: Optional[str], detail: Any = None):
    conn.execute("INSERT INTO definition_events (form_id, action, actor, detail_json) VALUES (?,?,?,?)", (form_id, action, actor, json.dumps(detail, ensure_ascii=False) if detail is not None else None))


def get_draft(conn, form_id: str, actor: Optional[str] = None) -> Dict[str, Any]:
    """The draft being edited (created from the published version when there is none)."""
    if form_id not in ALL_IDS:
        raise HTTPException(404, "Unknown form")
    row = _row(conn, form_id, "draft")
    if row:
        return json.loads(row["spec_json"])
    pub = _row(conn, form_id, "published")
    spec = json.loads(pub["spec_json"])
    nxt = conn.execute("SELECT COALESCE(MAX(version), 0) + 1 FROM form_definitions WHERE form_id = ?", (form_id,)).fetchone()[0]
    conn.execute("INSERT INTO form_definitions (form_id, version, status, spec_json, created_by) VALUES (?, ?, 'draft', ?, ?)", (form_id, nxt, json.dumps(spec, ensure_ascii=False), actor))
    return spec


def save_draft(conn, form_id: str, spec: Dict[str, Any], actor: Optional[str] = None):
    get_draft(conn, form_id, actor)
    conn.execute("UPDATE form_definitions SET spec_json = ?, created_by = COALESCE(?, created_by) WHERE form_id = ? AND status = 'draft'", (json.dumps(spec, ensure_ascii=False), actor, form_id))


def has_draft(conn, form_id: str) -> bool:
    return _row(conn, form_id, "draft") is not None


def discard_draft(conn, form_id: str, actor: Optional[str] = None):
    conn.execute("DELETE FROM form_definitions WHERE form_id = ? AND status = 'draft'", (form_id,))
    event(conn, form_id, "draft_discarded", actor)


def history(conn, form_id: str) -> List[Dict[str, Any]]:
    return [dict(r) for r in conn.execute("SELECT def_id, version, status, note, created_by, created_at, published_at FROM form_definitions WHERE form_id = ? ORDER BY version DESC", (form_id,))]


# ------------------------------------------------------------------------------------------------ editing a form's draft (pure functions on the spec)
def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(text or "").lower()).strip("_")[:32] or "field"


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def active(spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [q for q in spec["questions"] if q["type"] != "section" and not q.get("legacy")]


def _find(spec: Dict[str, Any], fid: str) -> Dict[str, Any]:
    q = next((q for q in spec["questions"] if q.get("fid") == fid), None)
    if not q:
        raise HTTPException(404, "That field no longer exists")
    return q


def _labels_in(spec: Dict[str, Any], cat: Optional[str], skip: Optional[Dict[str, Any]] = None) -> set:
    return {norm(q["q"]) for q in active(spec) if q is not skip and (not q.get("cats") or cat is None or cat in q["cats"])}


def _check_label(spec, label: str, cats: Optional[List[str]], skip=None):
    label = (label or "").strip()
    if not label:
        raise HTTPException(400, "A field needs a name")
    for c in (cats or spec["categories"]):
        if norm(label) in _labels_in(spec, c, skip):
            raise HTTPException(400, f"'{label}' is already a field in {c}. Use another name.")


def _clean_choices(kind: str, choices) -> Optional[List[str]]:
    if kind not in ("choice", "list"):
        return None
    items = [str(c).strip() for c in (choices or []) if str(c).strip()]
    if len(set(i.lower() for i in items)) < 2:
        raise HTTPException(400, "A pick-one field needs at least two choices")
    return list(dict.fromkeys(items))


def add_field(spec: Dict[str, Any], label: str, kind: str = "text", categories: Optional[List[str]] = None, required: bool = False, choices=None,
              help: str = "", newsletter: Optional[str] = None, profile: bool = False, after: Optional[str] = None) -> Dict[str, Any]:
    """A new field in the given categories (None = every category of the form). It is stored in the entry's answers; if it has a newsletter role it also feeds the newsletter."""
    if kind not in FIELD_TYPES:
        raise HTTPException(400, "Unknown field type")
    if newsletter and newsletter not in NEWSLETTER_ROLES:
        raise HTTPException(400, "Unknown newsletter role")
    cats = [c for c in (categories or []) if c in spec["categories"]] or None
    if categories and not cats:
        raise HTTPException(400, "Choose at least one category")
    _check_label(spec, label, cats)
    used = {q.get("fid") for q in spec["questions"]}
    key = "x_" + slug(label)
    fid, n = key, 1
    while fid in used or any(q.get("key") == key for q in spec["questions"]):
        n += 1
        key = f"x_{slug(label)}_{n}"
        fid = key
    q = {"q": label.strip(), "type": kind, "req": bool(required), "key": key, "fid": fid, "zone": "block" if cats else "common"}
    if cats:
        q["cats"] = cats
    if choices or kind in ("choice", "list"):
        q["choices"] = _clean_choices(kind, choices)
    if help:
        q["help"] = help.strip()
    if newsletter:
        q["nl"] = newsletter
    if profile:
        q["profile"] = True
    qs = spec["questions"]
    idx = next((i for i, x in enumerate(qs) if x.get("fid") == after), None) if after else None
    if idx is None:                                  # at the end of the category's own fields, before the closing questions
        idx = next((i for i, x in enumerate(qs) if x.get("zone") == "closing"), len(qs))
        pos = [i for i, x in enumerate(qs) if x.get("zone") == q["zone"] and not x.get("legacy")]
        idx = (max(pos) + 1) if pos else idx
    else:
        idx += 1
    qs.insert(idx, q)
    return q


def update_field(spec: Dict[str, Any], fid: str, changes: Dict[str, Any]) -> Dict[str, Any]:
    q = _find(spec, fid)
    if "label" in changes and changes["label"].strip() != q["q"]:
        _check_label(spec, changes["label"], q.get("cats"), skip=q)
        old = q["q"]
        q["aliases"] = list(dict.fromkeys([old, *q.get("aliases", [])]))         # the earlier label still imports old sheets
        q["q"] = changes["label"].strip()
    if "required" in changes:
        q["req"] = bool(changes["required"])
    if "help" in changes:
        q["help"] = (changes["help"] or "").strip() or None
        if not q["help"]:
            q.pop("help")
    if "type" in changes and changes["type"] != q["type"]:
        simple = {"text", "para", "number", "date", "url", "choice", "list"}
        if changes["type"] not in FIELD_TYPES:
            raise HTTPException(400, "Unknown field type")
        if q["type"] not in simple or changes["type"] not in simple:
            raise HTTPException(400, "A field that picks people or photos cannot change into another kind. Add a new field and retire this one.")
        q["type"] = changes["type"]                    # answers already given stay as they were; the new type applies to new entries
    if "choices" in changes or q["type"] in ("choice", "list"):
        if q["type"] in ("choice", "list"):
            q["choices"] = _clean_choices(q["type"], changes.get("choices", q.get("choices")))
        else:
            q.pop("choices", None)
    if "newsletter" in changes:
        role = changes["newsletter"] or None
        if role and role not in NEWSLETTER_ROLES:
            raise HTTPException(400, "Unknown newsletter role")
        if role:
            q["nl"] = role
        else:
            q.pop("nl", None)
    if "profile" in changes:
        q["profile"] = bool(changes["profile"])
    return q


def move_field(spec: Dict[str, Any], fid: str, direction: int, category: Optional[str] = None) -> None:
    """Up (-1) or down (+1) among the fields shown for the category (or the form's common fields)."""
    qs = spec["questions"]
    q = _find(spec, fid)
    group = [x for x in qs if x["type"] != "section" and not x.get("legacy") and x.get("zone") == q.get("zone") and (not category or not x.get("cats") or category in x["cats"])]
    i = group.index(q)
    j = i + (1 if direction > 0 else -1)
    if 0 <= j < len(group):
        a, b = qs.index(group[i]), qs.index(group[j])
        qs[a], qs[b] = qs[b], qs[a]


def retire_field(spec: Dict[str, Any], fid: str, category: Optional[str] = None) -> str:
    """Remove a field from new entries but keep it in the definition (old answers stay readable and old sheets still import). A field shared by
    several categories is only taken out of the given one."""
    q = _find(spec, fid)
    if q.get("nl") == "title" and not any(x is not q and x.get("nl") == "title" and (not x.get("cats") or set(x["cats"]) & set(q.get("cats") or spec["categories"])) for x in active(spec)):
        raise HTTPException(400, "This is the heading of its category: change it to another field first")
    if category and q.get("cats") and len(q["cats"]) > 1 and category in q["cats"]:
        q["cats"] = [c for c in q["cats"] if c != category]
        return f"Removed from {category}"
    q["legacy"] = True
    return "Retired"


def delete_field(spec: Dict[str, Any], fid: str) -> None:
    q = _find(spec, fid)
    if q.get("nl") == "title":
        raise HTTPException(400, "The heading field cannot be deleted")
    spec["questions"].remove(q)


def restore_field(spec: Dict[str, Any], fid: str) -> None:
    q = _find(spec, fid)
    q.pop("legacy", None)
    try:
        _check_label(spec, q["q"], q.get("cats"), skip=q)
    except HTTPException:
        q["legacy"] = True
        raise


def _cat_q(spec: Dict[str, Any]) -> Dict[str, Any]:
    return next(q for q in spec["questions"] if q.get("key") == "category" and not q.get("legacy"))


def _new_cat_fields(spec: Dict[str, Any], form_id: str, name: str):
    """A new category starts with the three things every entry needs: a heading, a date and a description."""
    desc_key = DESCRIPTION_KEY.get(form_id, "description")
    for label, key, kind, nl, req in (("Title", "title", "text", "title", True), ("Date", spec["date_key"], "date", "event_date", True), ("Description", desc_key, "para", "description", False)):
        existing = next((q for q in spec["questions"] if q.get("key") == key and not q.get("legacy") and q.get("cats") is not None and q["q"] == label), None)
        if existing and name not in existing["cats"]:
            existing["cats"].append(name)
            continue
        if not existing:
            idx = next((i for i, x in enumerate(spec["questions"]) if x.get("zone") == "closing"), len(spec["questions"]))
            pos = [i for i, x in enumerate(spec["questions"]) if x.get("zone") == "block" and not x.get("legacy")]
            q = {"q": label, "type": kind, "req": req, "key": key, "zone": "block", "cats": [name], "nl": nl}
            used = {x.get("fid") for x in spec["questions"]}
            fid, n = key, 1
            while fid in used:
                n += 1
                fid = f"{key}.{n}"
            q["fid"] = fid
            spec["questions"].insert((max(pos) + 1) if pos else idx, q)


def add_category(spec: Dict[str, Any], form_id: str, name: str, section_id: Optional[str] = None) -> str:
    name = (name or "").strip()
    if not name:
        raise HTTPException(400, "A category needs a name")
    if norm(name) in {norm(c) for c in spec["categories"]}:
        raise HTTPException(400, f"'{name}' already exists")
    spec["categories"].append(name)
    _cat_q(spec)["choices"] = list(spec["categories"])
    spec.setdefault("category_config", {})[name] = {"section_id": section_id} if section_id else {}
    spec["retired_categories"] = [c for c in spec.get("retired_categories", []) if c != name]
    _new_cat_fields(spec, form_id, name)
    return name


def rename_category(spec: Dict[str, Any], old: str, new: str) -> None:
    new = (new or "").strip()
    if old not in spec["categories"]:
        raise HTTPException(404, "That category no longer exists")
    if not new:
        raise HTTPException(400, "A category needs a name")
    if new != old and norm(new) in {norm(c) for c in spec["categories"]}:
        raise HTTPException(400, f"'{new}' already exists")
    spec["categories"] = [new if c == old else c for c in spec["categories"]]
    _cat_q(spec)["choices"] = list(spec["categories"])
    for q in spec["questions"]:
        if q.get("cats"):
            q["cats"] = [new if c == old else c for c in q["cats"]]
    cfg = spec.get("category_config", {})
    if old in cfg:
        cfg[new] = cfg.pop(old)
    for b in spec.get("layout", {}).get("blocks", []):
        if b["category"] == old:
            b["category"] = new
    aliases = spec.setdefault("category_aliases", {})                 # answers saved under the old name still belong to this category
    aliases[old] = new
    for k, v in list(aliases.items()):
        if v == old:
            aliases[k] = new


def delete_category(spec: Dict[str, Any], name: str) -> None:
    if name not in spec["categories"]:
        raise HTTPException(404, "That category no longer exists")
    if len(spec["categories"]) == 1:
        raise HTTPException(400, "A form needs at least one category")
    spec["categories"] = [c for c in spec["categories"] if c != name]
    _cat_q(spec)["choices"] = list(spec["categories"])
    for q in spec["questions"]:
        if q.get("cats") and name in q["cats"]:
            q["cats"] = [c for c in q["cats"] if c != name]
            if not q["cats"]:
                q["legacy"] = True                                    # nothing asks it any more, but its old answers still import
    spec.get("category_config", {}).pop(name, None)
    spec.setdefault("retired_categories", []).append(name)


def move_category(spec: Dict[str, Any], name: str, direction: int) -> None:
    cats = spec["categories"]
    i = cats.index(name)
    j = i + (1 if direction > 0 else -1)
    if 0 <= j < len(cats):
        cats[i], cats[j] = cats[j], cats[i]
        _cat_q(spec)["choices"] = list(cats)


def set_category_meta(spec: Dict[str, Any], name: str, tile: Optional[str] = None, keywords: Optional[str] = None, section_id: Optional[str] = None) -> None:
    if name not in spec["categories"]:
        raise HTTPException(404, "That category no longer exists")
    cfg = spec.setdefault("category_config", {}).setdefault(name, {})
    for k, v in (("tile", tile), ("keywords", keywords), ("section_id", section_id)):
        if v is not None:
            if v:
                cfg[k] = v
            else:
                cfg.pop(k, None)


# ------------------------------------------------------------------------------------------------ newsletter sections
def sections_add(doc: Dict[str, Any], name: str) -> Dict[str, Any]:
    name = (name or "").strip()
    if not name:
        raise HTTPException(400, "A section needs a name")
    if norm(name) in {norm(s["name"]) for s in doc["sections"]}:
        raise HTTPException(400, f"'{name}' already exists")
    sid = "sec_" + slug(name)
    used = {s["section_id"] for s in doc["sections"]}
    n = 1
    while sid in used:
        n += 1
        sid = f"sec_{slug(name)}_{n}"
    sec = {"section_id": sid, "name": name, "display_order": max([s.get("display_order", 0) for s in doc["sections"]] + [0]) + 1, "enabled": True, "template_file": "", "subcategories": []}
    doc["sections"].append(sec)
    return sec


def sections_rename(doc, section_id: str, name: str):
    s = next((s for s in doc["sections"] if s["section_id"] == section_id), None)
    if not s:
        raise HTTPException(404, "Unknown section")
    if not name.strip():
        raise HTTPException(400, "A section needs a name")
    s["name"] = name.strip()


def sections_move(doc, section_id: str, direction: int):
    secs = sorted(doc["sections"], key=lambda s: s.get("display_order", 0))
    i = next(i for i, s in enumerate(secs) if s["section_id"] == section_id)
    j = i + (1 if direction > 0 else -1)
    if 0 <= j < len(secs):
        secs[i]["display_order"], secs[j]["display_order"] = secs[j].get("display_order", j), secs[i].get("display_order", i)
        if secs[i]["display_order"] == secs[j]["display_order"]:
            secs[j]["display_order"] += 1


def sections_toggle(doc, section_id: str, enabled: bool):
    s = next((s for s in doc["sections"] if s["section_id"] == section_id), None)
    if not s:
        raise HTTPException(404, "Unknown section")
    s["enabled"] = bool(enabled)


def sections_delete(conn, doc, section_id: str):
    forms_using = []
    for fid in FORM_IDS:
        spec = json.loads((_row(conn, fid, "draft") or _row(conn, fid, "published"))["spec_json"])
        if spec.get("section_id") == section_id or any(c.get("section_id") == section_id for c in spec.get("category_config", {}).values()):
            forms_using.append(spec["title"])
    if forms_using:
        raise HTTPException(400, "Move these forms' categories to another section first: " + ", ".join(forms_using))
    doc["sections"] = [s for s in doc["sections"] if s["section_id"] != section_id]


# ------------------------------------------------------------------------------------------------ checking and publishing
def problems(spec: Dict[str, Any], form_id: str) -> List[str]:
    out = []
    if form_id in (PLACEMENT, SECTIONS):
        return out
    if not spec["categories"]:
        out.append("The form has no categories")
    for c in spec["categories"]:
        qs = [q for q in active(spec) if not q.get("cats") or c in q["cats"]]
        labels = [norm(q["q"]) for q in qs]
        if len(labels) != len(set(labels)):
            out.append(f"{c}: two fields have the same name")
        if not any(q.get("nl") == "title" or q.get("key") == "title" for q in qs) and not spec.get("category_config", {}).get(c, {}).get("title_from"):
            out.append(f"{c}: it needs a heading field (a field used in the newsletter as 'Heading')")
        for q in qs:
            if q["type"] in ("choice", "list") and len(q.get("choices") or []) < 2:
                out.append(f"{c}: '{q['q']}' needs at least two choices")
    return out


def impact(conn, form_id: str, spec: Dict[str, Any]) -> Dict[str, Any]:
    """What publishing touches: entries per category, and which categories / fields were dropped from the published version."""
    pub = json.loads(_row(conn, form_id, "published")["spec_json"])
    ftype = spec.get("form_type")
    counts = {r[0]: r[1] for r in conn.execute("SELECT category, COUNT(*) FROM form_submissions WHERE form_type = ? GROUP BY 1", (ftype,))}
    gone = [c for c in pub["categories"] if c not in spec["categories"]]
    new = [c for c in spec["categories"] if c not in pub["categories"]]
    pubq = {q["fid"]: q for q in active(pub) if q.get("fid")}
    cur = {q["fid"]: q for q in active(spec) if q.get("fid")}
    return {"entries_by_category": counts, "removed_categories": [{"name": c, "entries": counts.get(c, 0)} for c in gone], "new_categories": new,
            "added_fields": [q["q"] for f, q in cur.items() if f not in pubq], "retired_fields": [{"label": q["q"], "entries": sum(counts.values())} for f, q in pubq.items() if f not in cur],
            "renamed_fields": [{"from": pubq[f]["q"], "to": q["q"]} for f, q in cur.items() if f in pubq and pubq[f]["q"] != q["q"]]}


def publish(conn, form_id: str, actor: Optional[str], note: str = "") -> Dict[str, Any]:
    row = _row(conn, form_id, "draft")
    if not row:
        raise HTTPException(400, "There are no changes to publish")
    spec = json.loads(row["spec_json"])
    bad = problems(spec, form_id)
    if bad:
        raise HTTPException(400, "Fix this before publishing: " + "; ".join(bad))
    imp = impact(conn, form_id, spec) if form_id in FORM_IDS else {}
    conn.execute("UPDATE form_definitions SET status = 'archived' WHERE form_id = ? AND status = 'published'", (form_id,))
    conn.execute("UPDATE form_definitions SET status = 'published', note = ?, published_at = CURRENT_TIMESTAMP, created_by = COALESCE(?, created_by) WHERE def_id = ?", (note or None, actor, row["def_id"]))
    event(conn, form_id, "published", actor, {"version": row["version"], "note": note, "impact": imp})
    invalidate_after_commit()
    _write_studio_files_after_commit(conn)
    return {"version": row["version"], "impact": imp}


def _write_studio_files_after_commit(conn) -> None:
    """Rewrite the newsletter studio's mappings from what was just published, once the publish is committed."""
    from backend.master import studio_sync
    from database.master_db import after_commit
    snapshot = current_specs_from(conn)
    after_commit(lambda: studio_sync.write_files(snapshot))


def current_specs_from(conn) -> Dict[str, Any]:
    rows = conn.execute("SELECT form_id, spec_json FROM form_definitions WHERE status = 'published' ORDER BY form_id").fetchall()
    return _from_rows([(r[0], r[1]) for r in rows])


def restore(conn, form_id: str, version: int, actor: Optional[str]) -> None:
    """Make an earlier version the draft (publish it to bring it back)."""
    row = conn.execute("SELECT spec_json FROM form_definitions WHERE form_id = ? AND version = ? AND status != 'draft'", (form_id, version)).fetchone()
    if not row:
        raise HTTPException(404, "That version does not exist")
    get_draft(conn, form_id, actor)
    conn.execute("UPDATE form_definitions SET spec_json = ? WHERE form_id = ? AND status = 'draft'", (row["spec_json"], form_id))
    event(conn, form_id, "restored_to_draft", actor, {"version": version})


def reset_to_shipped(conn, form_id: str, actor: Optional[str]) -> None:
    shipped = _read_file(SPEC_FILE)
    spec = _ids(shipped["forms"][form_id]) if form_id in shipped["forms"] else shipped["placement"]
    get_draft(conn, form_id, actor)
    conn.execute("UPDATE form_definitions SET spec_json = ? WHERE form_id = ? AND status = 'draft'", (json.dumps(spec, ensure_ascii=False), form_id))
    event(conn, form_id, "reset_to_shipped_draft", actor)


# ------------------------------------------------------------------------------------------------ what the editor screen shows
LOCKED_KEYS = {"category", "is_landmark", "authorization_confirmed", "publish_permission"}


def editor_view(conn, form_id: str) -> Dict[str, Any]:
    """The draft (or, with no draft, the published definition) as the editor needs it, plus the problems that would stop a publish."""
    drafting = has_draft(conn, form_id)
    spec = json.loads((_row(conn, form_id, "draft") or _row(conn, form_id, "published"))["spec_json"])
    pub = _row(conn, form_id, "published")
    if form_id == PLACEMENT:
        fields = [{"fid": q.get("key"), "key": q.get("key"), "label": q["q"], "type": q["type"], "required": bool(q.get("req")), "help": q.get("help"), "choices": q.get("choices"),
                   "section": q["type"] == "section"} for q in spec["questions"]]
        return {"form_id": form_id, "title": spec["title"], "placement": True, "fields": fields, "has_draft": drafting, "version": pub["version"]}
    fields = []
    for q in spec["questions"]:
        if q["type"] == "section":
            continue
        fields.append({"fid": q["fid"], "key": q.get("key"), "label": q["q"], "type": q["type"], "required": bool(q.get("req")), "help": q.get("help"), "choices": q.get("choices"),
                       "newsletter": q.get("nl") if q.get("nl") in NEWSLETTER_ROLES else None, "profile": bool(q.get("profile")), "zone": q.get("zone"), "cats": q.get("cats"),
                       "retired": bool(q.get("legacy")), "locked": bool(q.get("key") in LOCKED_KEYS or q.get("submitter") or q.get("derived") or q.get("key") == "category")})
    from . import blocks, entry                       # lazy: these import this module
    by_fid = {q["fid"]: q for q in spec["questions"] if q["type"] != "section"}
    for f in fields:
        q = by_fid[f["fid"]]
        f["display"], f["widget"], f["shown"] = entry.display_label(q), entry._widget(q), entry._shown(q)
    cats = []
    secs = (json.loads((_row(conn, SECTIONS, "published"))["spec_json"]))["sections"]
    for name in spec["categories"]:
        cfg = spec.get("category_config", {}).get(name, {})
        live = blocks.questions_for(spec, name, legacy=False)
        everything = blocks.questions_for(spec, name, legacy=True)
        shown = sorted((q for q in live if entry._shown(q)), key=lambda q: entry.ZONE_ORDER.get(q.get("zone"), 1))   # same order as the entry screen
        cats.append({"name": name, "tile": cfg.get("tile"), "keywords": cfg.get("keywords"), "section_id": cfg.get("section_id") or spec.get("section_id"),
                     "fids": [q["fid"] for q in shown], "automatic": [q["fid"] for q in live if not entry._shown(q)],
                     "retired_fids": [q["fid"] for q in everything if q.get("legacy") and entry._shown(q)]})
    return {"form_id": form_id, "title": spec["title"], "form_type": spec.get("form_type"), "section_id": spec.get("section_id"), "categories": cats, "retired_categories": spec.get("retired_categories", []),
            "fields": fields, "sections": [{"section_id": s["section_id"], "name": s["name"], "enabled": s.get("enabled", True), "order": s.get("display_order", 0)} for s in sorted(secs, key=lambda s: s.get("display_order", 0))],
            "has_draft": drafting, "version": pub["version"], "problems": problems(spec, form_id), "types": FIELD_TYPES, "roles": NEWSLETTER_ROLES}


def apply_op(conn, form_id: str, op: str, p: Dict[str, Any], actor: str) -> None:
    """One editing step on the draft."""
    spec = get_draft(conn, form_id, actor)
    if form_id == PLACEMENT:
        raise HTTPException(400, "The placement form is edited with the placement steps")
    if op == "add_field":
        add_field(spec, p.get("label", ""), p.get("type", "text"), p.get("categories"), p.get("required", False), p.get("choices"), p.get("help", ""), p.get("newsletter"), p.get("profile", False), p.get("after"))
    elif op == "update_field":
        update_field(spec, p["fid"], p.get("changes", {}))
    elif op == "move_field":
        move_field(spec, p["fid"], int(p.get("direction", 1)), p.get("category"))
    elif op == "retire_field":
        retire_field(spec, p["fid"], p.get("category"))
    elif op == "restore_field":
        restore_field(spec, p["fid"])
    elif op == "delete_field":
        delete_field(spec, p["fid"])
    elif op == "add_category":
        add_category(spec, form_id, p.get("name", ""), p.get("section_id"))
    elif op == "rename_category":
        rename_category(spec, p["name"], p.get("new_name", ""))
    elif op == "delete_category":
        delete_category(spec, p["name"])
    elif op == "move_category":
        move_category(spec, p["name"], int(p.get("direction", 1)))
    elif op == "category_meta":
        set_category_meta(spec, p["name"], p.get("tile"), p.get("keywords"), p.get("section_id"))
    else:
        raise HTTPException(400, "Unknown change")
    save_draft(conn, form_id, spec, actor)
    event(conn, form_id, "draft_" + op, actor, {k: v for k, v in p.items() if k != "changes"} | ({"changes": p["changes"]} if p.get("changes") else {}))


def sections_apply(conn, op: str, p: Dict[str, Any], actor: str) -> Dict[str, Any]:
    """Section changes take effect at once (a new published version of the section list)."""
    row = _row(conn, SECTIONS, "published")
    doc = json.loads(row["spec_json"])
    if op == "add":
        sections_add(doc, p.get("name", ""))
    elif op == "rename":
        sections_rename(doc, p["section_id"], p.get("name", ""))
    elif op == "move":
        sections_move(doc, p["section_id"], int(p.get("direction", 1)))
    elif op == "toggle":
        sections_toggle(doc, p["section_id"], bool(p.get("enabled")))
    elif op == "delete":
        sections_delete(conn, doc, p["section_id"])
    else:
        raise HTTPException(400, "Unknown change")
    conn.execute("UPDATE form_definitions SET status = 'archived' WHERE def_id = ?", (row["def_id"],))
    conn.execute("INSERT INTO form_definitions (form_id, version, status, spec_json, note, created_by, published_at) VALUES (?, ?, 'published', ?, ?, ?, CURRENT_TIMESTAMP)",
                 (SECTIONS, conn.execute("SELECT COALESCE(MAX(version), 0) + 1 FROM form_definitions WHERE form_id = ?", (SECTIONS,)).fetchone()[0], json.dumps(doc, ensure_ascii=False), f"{op} section", actor))
    event(conn, SECTIONS, "section_" + op, actor, p)
    invalidate_after_commit()
    _write_studio_files_after_commit(conn)
    return {"sections": doc["sections"]}
