"""
Turns gform_scripts/new_forms.py (the IT Matrix forms) into the application's shipped configuration.

Run:  python gform_scripts/build_new_forms.py

It writes
  config/master_forms.json       questions (with the categories each belongs to), the response sheet's layout (common / section / closing
                                 columns), per-category settings (card description, date, title) and the placement diary
  config/form_mappings.json      the newsletter studio's mappings
  config/section_categories.json the newsletter's section categories

A new database starts from config/master_forms.json; an existing one takes it over only for forms the Admin never edited.
"""
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
CONFIG = os.path.join(ROOT, "config")
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import new_forms as N  # noqa: E402

VERSION = "3.4"
SECTION_IDS = {"form_research": "sec_research", "form_faculty": "sec_faculty", "form_departmental": "sec_departmental",
               "form_industry": "sec_industry", "form_student": "sec_student"}
# new category name -> the earlier name whose newsletter category it continues
RENAMED = {
    "Patents & Intellectual Property Rights (IPR)": "Patents & Intellectual Property",
    "Membership in Professional Body & Editorial Board Roles": "Professional Body & Editorial Board Roles",
    "Departmental Achievements / Awards / Recognitions": "Achievements / Awards / Recognitions",
    "Events / Programs Conducted": "Events / Programs",
    "Faculty Development Programmes (FDPs), Conferences, and Other Long-Term Programmes Organised": "Faculty Development / Professional Achievements",
    "Student Development, Outreach, and Social Initiatives Undertaken by the Department": "Student Development / Outreach / Social Initiatives",
    "Other Significant Highlights": "Other Significant Initiatives",
    "Hackathons / Coding Competitions": "Hackathons & Coding Competitions",
}


def _identity(q):
    return json.dumps({k: v for k, v in q.items() if k != "cats"}, sort_keys=True, ensure_ascii=False)


def build_form(fid, spec):
    """One form's configuration."""
    questions, index = [], {}                       # index: identity -> question (to merge identical questions of several categories)

    def add(q, cat=None):
        if cat is None:
            questions.append(copy.deepcopy(q))
            return
        ident = _identity(q)
        if ident in index:
            index[ident]["cats"].append(cat)
        else:
            c = copy.deepcopy(q)
            c["cats"] = [cat]
            index[ident] = c
            questions.append(c)

    cat_q = {**copy.deepcopy(spec["category_q"]), "zone": "category", "choices": [b["name"] for b in spec["blocks"]], "req": True}
    flat = spec.get("flat")
    layout = {"common": [], "blocks": [], "closing": []}
    for item in spec["common"]:
        if isinstance(item, str):
            layout["common"].append(item)
        else:
            layout["common"].append(N.printed_title(item))
            add({**item, "zone": "common"})
    if not flat:
        questions.append(cat_q)
    cfg = {}
    for b in spec["blocks"]:
        has_title = any(f["key"] == "title" for f in (spec.get("flat_fields") if flat else b["fields"]))
        if not flat:
            if not b["portal_only"]:                                      # a section the Google Form does not have yet has no columns in its sheet
                layout["blocks"].append({"category": b["name"], "gate": b["gate"], "fields": [N.printed_title(f) for f in b["fields"] if not f.get("portal_only")]})
            for f in b["fields"]:
                add({**f, "zone": "block"}, b["name"])
            if b["title_from"] and not has_title:
                add({**N.F("Title", "title", req=True, nl="title", derived=True, help="Made from the answers."), "zone": "block"}, b["name"])
        cfg[b["name"]] = {k: v for k, v in (("description", b["description"]), ("keywords", b["keywords"]), ("date_key", b["date_key"]), ("defaults", b["defaults"]), ("copy", b["copy"]),
                                            ("title_from", b["title_from"]), ("title_prefix", b["title_prefix"]), ("date_text_key", b["date_text_key"]),
                                            ("title_fallback", b["name"] if b["title_from"] else None)) if v}
    if flat:
        for f in spec["flat_fields"]:
            add({**f, "zone": "block"})
            if f["q"] == spec["category_after"]:
                questions.append(cat_q)
    for f in spec["closing"]:
        layout["closing"].append(N.printed_title(f))
        add({**f, "zone": "closing"})
    out = {"form_type": spec["form_type"], "date_key": spec["date_key"], "title": spec["title"], "description": spec["description"],
           "section_id": SECTION_IDS[fid], "categories": [b["name"] for b in spec["blocks"]], "category_config": cfg, "questions": questions}
    if not flat:
        out["layout"] = layout
    if spec.get("date_fallback"):
        out["date_fallback"] = spec["date_fallback"]
    return out


def placement():
    qs = copy.deepcopy(N.PLACEMENT)
    return {**N.PLACEMENT_META, "form_type": "PLACEMENT", "questions": qs}


def _load(name, default):
    path = os.path.join(CONFIG, name)
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else default


def studio_files(forms):
    """The newsletter studio's two files, keeping the newsletter category ids of the categories that continue under a new name."""
    from backend.master import studio_sync
    maps, sections = _load("form_mappings.json", {"forms": {}}), _load("section_categories.json", {"sections": []})
    base, dropped = copy.deepcopy(maps), set()
    for fid, spec in forms.items():
        old = maps["forms"].get(fid, {}).get("category_map", {})
        keep = {}
        for name in spec["categories"]:
            cid = old.get(name) or old.get(RENAMED.get(name, ""))
            if cid:
                keep[name] = cid
        dropped |= set(old.values()) - set(keep.values())
        base["forms"][fid] = {"section_id": spec["section_id"], "category_map": keep}
    mappings = studio_sync.build_mappings({"forms": forms}, base)
    used = {c for f in mappings["forms"].values() for c in f.get("category_map", {}).values()}
    for s in sections["sections"]:
        s["subcategories"] = [c for c in s.get("subcategories", []) if c["category_id"] not in dropped - used]
    return mappings, studio_sync.build_sections({"forms": forms}, sections, mappings)


def main():
    forms = {fid: build_form(fid, spec) for fid, spec in N.FORMS.items()}
    master = {"version": VERSION, "forms": forms, "placement": placement()}
    mappings, sections = studio_files(forms)
    for name, doc, indent in (("master_forms.json", master, 1), ("form_mappings.json", mappings, 2), ("section_categories.json", sections, 2)):
        with open(os.path.join(CONFIG, name), "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=indent, ensure_ascii=False)
    print("Wrote config/master_forms.json, config/form_mappings.json, config/section_categories.json")
    for fid, s in forms.items():
        print(f"  {fid}: {len(s['categories'])} categories, {sum(1 for q in s['questions'] if q['type'] != 'section')} questions")


if __name__ == "__main__":
    main()
