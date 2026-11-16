"""
Turns gform_scripts/new_forms.py (the category-based forms) into the application's configuration.

Run:  python gform_scripts/build_new_forms.py

It writes
  config/master_forms.json       the master-database importer's view: questions (with the categories each belongs to), the response sheet's
                                 layout (common / category blocks / closing columns) and per-category settings
  config/form_mappings.json      the newsletter studio's mappings (merged: earlier headers stay understood)
  config/section_categories.json the newsletter's section categories (the department section gets its new categories)

The earlier version of each form is kept in gform_scripts/legacy_*.json; its questions stay in the configuration marked "legacy": true so sheets
exported from the old forms still import (they are not shown on screen or in templates).
"""
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
CONFIG = os.path.join(ROOT, "config")
sys.path.insert(0, HERE)

import new_forms as N  # noqa: E402

STUDIO_TYPE = {"para": "textarea", "roster_roll": "textarea", "roster_any": "textarea", "date": "date", "choice": "select", "list": "select", "url": "url"}
NEW_DEPT_IDS = {
    "Highlights": "cat_dept_highlights", "Achievements / Awards / Recognitions": "cat_dept_awards", "Events / Programs": "cat_dept_events",
    "Research / Publications / Innovation": "cat_dept_research", "Infrastructure / Laboratory Development": "cat_dept_infra_dev",
    "MoU / Industry Collaboration / Partnerships": "cat_dept_mou", "Faculty Development / Professional Achievements": "cat_dept_fdp",
    "Student Development / Outreach / Social Initiatives": "cat_dept_student_dev", "Accreditation / Quality Assurance / Institutional Initiatives": "cat_dept_accreditation",
    "Other Significant Initiatives": "cat_dept_other",
}


def _identity(q):
    return json.dumps({k: v for k, v in q.items() if k != "cats"}, sort_keys=True, ensure_ascii=False)


def build_form(fid, spec, legacy_spec):
    """One form's configuration."""
    questions, index = [], {}                       # index: identity -> question (to merge identical questions of several categories)

    def add(q, cat=None):
        if cat is None:
            questions.append(copy.deepcopy(q))
            return
        ident = _identity(q)
        if ident in index:
            index[ident].setdefault("cats", []).append(cat)
        else:
            c = copy.deepcopy(q)
            c["cats"] = [cat]
            index[ident] = c
            questions.append(c)

    layout = {"common": [], "blocks": [], "closing": []}
    sections_seen = False
    for item in spec["common"]:
        if isinstance(item, str):
            layout["common"].append(item)
        else:
            layout["common"].append(item["q"])
            add(item)
    cat_q = copy.deepcopy(spec["category_q"])
    cat_q["choices"] = [b["name"] for b in spec["blocks"]]
    cat_q.pop("req", None)
    cat_q["req"] = True
    questions.append(cat_q)
    cfg = {}
    for b in spec["blocks"]:
        has_title = any(f["key"] == "title" for f in b["fields"])
        layout["blocks"].append({"category": b["name"], "gate": b["gate"], "fields": [f["q"] for f in b["fields"]]})
        for f in b["fields"]:
            add(f, b["name"])
        if b["title_from"] and not has_title:
            add(N.F("Title", "title", req=True, nl="title", derived=True, help="Made from the overview; change it if you like."), b["name"])
        cfg[b["name"]] = {k: v for k, v in (("gate", b["gate"]), ("date_key", b["date_key"]), ("defaults", b["defaults"]), ("copy", b["copy"]),
                                            ("title_from", b["title_from"]), ("title_prefix", b["title_prefix"]), ("date_text_key", b["date_text_key"])) if v}
    inverse = {flat: sheet for sheet, flat in spec.get("closing_rename", {}).items()}
    for f in spec["closing"]:
        layout["closing"].append(inverse.get(f["q"], f["q"]))
        add(f)
    layout["closing_rename"] = spec.get("closing_rename", {})
    # the earlier version's questions stay understood (hidden): kept unless this version defines the very same question
    have = {(q["q"], q["key"]) for q in questions if not q.get("cats")}          # a category-specific question does not replace the global old one
    for q in legacy_spec["questions"]:
        if q["type"] == "section" or (q["q"], q.get("key")) in have:
            continue
        lq = copy.deepcopy(q)
        lq["legacy"] = True
        questions.append(lq)
    out = {"form_type": spec["form_type"], "date_key": spec["date_key"], "title": spec["title"], "description": spec["description"],
           "section_id": legacy_spec["section_id"], "categories": [b["name"] for b in spec["blocks"]], "category_config": cfg, "layout": layout, "questions": questions}
    if spec.get("date_fallback"):
        out["date_fallback"] = spec["date_fallback"]
    old_cat = next((q for q in legacy_spec["questions"] if q.get("key") == "category"), None)
    if old_cat:
        out["legacy_categories"] = [c for c in old_cat.get("choices", []) if c not in out["categories"]]
    return out


def studio_type(q):
    if q.get("nl") == "photo_url" or "photo link" in q["q"].lower():
        return "image"
    if q.get("nl") == "description":
        return "textarea"
    return STUDIO_TYPE.get(q["type"], "text")


def merge_mappings(master_forms, legacy_maps):
    data = copy.deepcopy(legacy_maps)
    for fid, spec in master_forms.items():
        old = data["forms"][fid]
        fm = {"Timestamp": "submission_timestamp", "Email Address": "submitter_email"}
        meta = {"Timestamp": {"canonical_tag": "submission_timestamp", "type": "text", "required": False, "description": "Added by Google Forms"},
                "Email Address": {"canonical_tag": "submitter_email", "type": "text", "required": False, "description": "Collected by Google Forms"}}
        tfs, per_cat = {}, {c: {} for c in spec["categories"]}
        category_field = None
        tags_of = {}                                   # title -> the newsletter fields it fills (in different categories)
        for q in spec["questions"]:
            if q.get("legacy") or q["type"] == "section":
                continue
            tag = q.get("nl")
            if tag == "category_id":
                category_field = q["q"]
            elif tag:
                tags_of.setdefault(q["q"], {}).setdefault(tag, []).extend(q.get("cats") or spec["categories"])
        for title, by_tag in tags_of.items():
            if len(by_tag) == 1:                       # the same newsletter field wherever the title appears: one global mapping
                fm[title] = next(iter(by_tag))
            else:                                      # different fields in different categories: the category decides
                for tag, cats in by_tag.items():
                    for c in cats:
                        per_cat[c][title] = tag
        for q in spec["questions"]:
            if q.get("legacy") or q["type"] == "section":
                continue
            tag = q.get("nl")
            if q.get("tf"):
                tfs[q["q"]] = q["tf"]
            m = meta.setdefault(q["q"], {"canonical_tag": tag or "custom", "type": studio_type(q), "required": bool(q.get("req")), "description": q.get("help", "")})
            if q.get("cats"):
                m.setdefault("categories", [])
                m["categories"] = sorted(set(m["categories"]) | set(q["cats"]))
        known = set(meta)
        legacy = dict(old.get("legacy_field_mappings", {}))
        legacy.update({k: v for k, v in old.get("field_mappings", {}).items() if k not in known})
        legacy_tf = dict(old.get("legacy_transforms", {}))
        legacy_tf.update({k: v for k, v in old.get("transforms", {}).items() if k not in known})
        cmap = dict(old.get("category_map", {}))
        for name in spec["categories"]:
            cmap.setdefault(name, NEW_DEPT_IDS.get(name) if fid == "form_departmental" else cmap.get(name))
        cmap = {name: cmap[name] for name in spec["categories"] if cmap.get(name)}          # only the form's current categories are offered
        new = {"form_name": spec["title"], "section_id": old.get("section_id"), "category_field": category_field, "category_map": cmap,
               "field_mappings": fm, "column_metadata": meta, "category_field_mappings": {c: m for c, m in per_cat.items() if m}}
        if tfs:
            new["transforms"] = tfs
        if legacy:
            new["legacy_field_mappings"] = legacy
        if legacy_tf:
            new["legacy_transforms"] = legacy_tf
        data["forms"][fid] = new
    return data


def main():
    legacy = json.load(open(os.path.join(HERE, "legacy_master_forms.json"), encoding="utf-8"))
    legacy_maps = json.load(open(os.path.join(HERE, "legacy_form_mappings.json"), encoding="utf-8"))
    sections = json.load(open(os.path.join(HERE, "legacy_section_categories.json"), encoding="utf-8"))
    forms = {fid: build_form(fid, spec, legacy["forms"][fid]) for fid, spec in N.FORMS.items()}
    placement = copy.deepcopy(legacy["placement"])
    for q in placement["questions"]:
        if q["q"] in N.PLACEMENT_RENAMES:
            new_title, extra = N.PLACEMENT_RENAMES[q["q"]]
            q["aliases"] = [q["q"], *q.get("aliases", []), *extra]
            q["q"] = new_title
        if q["q"] in N.PLACEMENT_CHOICES:
            q["choices"] = N.PLACEMENT_CHOICES[q["q"]]
    master = {"version": "2.0", "forms": forms, "placement": placement}
    with open(os.path.join(CONFIG, "master_forms.json"), "w", encoding="utf-8") as f:
        json.dump(master, f, indent=1, ensure_ascii=False)
    with open(os.path.join(CONFIG, "form_mappings.json"), "w", encoding="utf-8") as f:
        json.dump(merge_mappings(forms, legacy_maps), f, indent=2, ensure_ascii=False)
    dept = next(s for s in sections["sections"] if s["section_id"] == "sec_departmental")
    have = {c["category_id"] for c in dept["subcategories"]}
    for name, cid in NEW_DEPT_IDS.items():
        if cid not in have:
            dept["subcategories"].append({"category_id": cid, "name": name})
    with open(os.path.join(CONFIG, "section_categories.json"), "w", encoding="utf-8") as f:
        json.dump(sections, f, indent=2, ensure_ascii=False)
    print("Wrote config/master_forms.json, config/form_mappings.json, config/section_categories.json")
    for fid, s in forms.items():
        print(f"  {fid}: {len(s['categories'])} categories, {sum(1 for q in s['questions'] if not q.get('legacy') and q['type'] != 'section')} questions (+{sum(1 for q in s['questions'] if q.get('legacy'))} legacy)")


if __name__ == "__main__":
    main()
