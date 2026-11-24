"""Keeps the newsletter studio's configuration in step with the published form definitions.

The studio reads config/form_mappings.json (which question fills which newsletter field, and which category is which) and
config/section_categories.json (the newsletter's sections and their categories). When the Admin publishes a change, write_files() regenerates
both from the definitions. Mappings of earlier questions (retired or renamed) are kept as 'legacy' so old responses still map.
"""
import copy
import json
import os
import re
from typing import Any, Dict

from backend.master import definitions as D

CONFIG = os.path.join(D.ROOT, "config")
MAPPINGS_FILE = os.path.join(CONFIG, "form_mappings.json")
STUDIO_TYPE = {"para": "textarea", "roster_roll": "textarea", "roster_any": "textarea", "date": "date", "choice": "select", "list": "select", "url": "url", "photo": "image"}


def _studio_type(q: Dict[str, Any]) -> str:
    if q.get("nl") == "photo_url" or "photo" in q["q"].lower() and q.get("type") in ("url", "photo"):
        return "image"
    if q.get("nl") == "description":
        return "textarea"
    return STUDIO_TYPE.get(q["type"], "text")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(text or "").lower()).strip("_")[:28]


def build_mappings(specs: Dict[str, Any], base: Dict[str, Any]) -> Dict[str, Any]:
    data = copy.deepcopy(base)
    forms = data.setdefault("forms", {})
    for fid, spec in specs["forms"].items():
        old = forms.get(fid, {})
        fm = {"Timestamp": "submission_timestamp", "Email Address": "submitter_email"}
        meta = {"Timestamp": {"canonical_tag": "submission_timestamp", "type": "text", "required": False, "description": "Added by Google Forms"},
                "Email Address": {"canonical_tag": "submitter_email", "type": "text", "required": False, "description": "Collected by Google Forms"}}
        tfs, per_cat, category_field, tags_of = {}, {c: {} for c in spec["categories"]}, None, {}
        live = [q for q in spec["questions"] if not q.get("legacy") and q["type"] != "section"]
        for q in live:
            tag = q.get("nl")
            if tag == "category_id":
                category_field = q["q"]
            elif tag:
                tags_of.setdefault(q["q"], {}).setdefault(tag, []).extend(q.get("cats") or spec["categories"])
        for title, by_tag in tags_of.items():
            if len(by_tag) == 1:
                fm[title] = next(iter(by_tag))
            else:
                for tag, cats in by_tag.items():
                    for c in cats:
                        per_cat[c][title] = tag
        for q in live:
            tag = q.get("nl")
            if q.get("tf"):
                tfs[q["q"]] = q["tf"]
            m = meta.setdefault(q["q"], {"canonical_tag": tag or "custom", "type": _studio_type(q), "required": bool(q.get("req")), "description": q.get("help", "")})
            if q.get("cats"):
                m["categories"] = sorted(set(m.get("categories", [])) | set(q["cats"]))
        known = set(meta)
        legacy = dict(old.get("legacy_field_mappings", {}))
        legacy.update({k: v for k, v in old.get("field_mappings", {}).items() if k not in known})
        legacy_tf = dict(old.get("legacy_transforms", {}))
        legacy_tf.update({k: v for k, v in old.get("transforms", {}).items() if k not in known})
        for q in spec["questions"]:                              # a retired question keeps its newsletter mapping, and so does an earlier label of a renamed one
            titles = [q["q"], *q.get("aliases", [])] if q.get("legacy") else q.get("aliases", [])
            for t in titles:
                if q.get("nl") and q["nl"] != "category_id" and t not in known:
                    legacy[t] = q["nl"]
        cmap, sec_of, short = dict(old.get("category_map", {})), {}, _slug(spec.get("form_type", fid)).lower()
        used_ids = {v for f in forms.values() for v in f.get("category_map", {}).values()}
        out_map = {}
        for name in spec["categories"]:
            cid = cmap.get(name) or f"cat_{short}_{_slug(name)}"
            n = 1
            while cid in used_ids and cmap.get(name) != cid:
                n += 1
                cid = f"cat_{short}_{_slug(name)}_{n}"
            out_map[name] = cid
            used_ids.add(cid)
            override = spec.get("category_config", {}).get(name, {}).get("section_id")
            if override and override != spec.get("section_id"):
                sec_of[name] = override
        for gone in spec.get("retired_categories", []):          # a retired category still maps old responses to its newsletter category
            if gone in cmap and gone not in out_map:
                legacy_cat = cmap[gone]
                out_map[gone] = legacy_cat
        for old_name, new_name in spec.get("category_aliases", {}).items():
            if new_name in out_map and old_name not in out_map:
                out_map[old_name] = out_map[new_name]
        new = {"form_name": spec["title"], "section_id": spec.get("section_id") or old.get("section_id"), "category_field": category_field, "category_map": out_map,
               "field_mappings": fm, "column_metadata": meta, "category_field_mappings": {c: m for c, m in per_cat.items() if m}}
        if sec_of:
            new["category_section_map"] = sec_of
        if tfs:
            new["transforms"] = tfs
        if legacy:
            new["legacy_field_mappings"] = legacy
        if legacy_tf:
            new["legacy_transforms"] = legacy_tf
        forms[fid] = new
    return data


def build_sections(specs: Dict[str, Any], current: Dict[str, Any], mappings: Dict[str, Any]) -> Dict[str, Any]:
    """The section list (from the definitions) with every form category sitting in its section."""
    doc = copy.deepcopy(specs.get("sections") or current)
    secs = {s["section_id"]: s for s in doc["sections"]}
    for fid, spec in specs["forms"].items():
        cmap = mappings["forms"][fid]["category_map"]
        for name in spec["categories"]:
            cid = cmap[name]
            target = spec.get("category_config", {}).get(name, {}).get("section_id") or spec.get("section_id")
            for s in secs.values():                                # move it if the Admin changed its section
                if s["section_id"] != target:
                    s["subcategories"] = [c for c in s.get("subcategories", []) if c["category_id"] != cid]
            if target in secs:
                subs = secs[target].setdefault("subcategories", [])
                hit = next((c for c in subs if c["category_id"] == cid), None)
                if hit:
                    hit["name"] = name
                else:
                    subs.append({"category_id": cid, "name": name})
    return doc


def write_files(specs: Dict[str, Any]) -> None:
    import sys
    if "pytest" in sys.modules and not os.environ.get("STUDIO_CONFIG_WRITE"):
        return                                                   # tests never touch the real configuration files
    if not os.path.isdir(CONFIG):
        return
    try:
        base = json.load(open(MAPPINGS_FILE, encoding="utf-8")) if os.path.exists(MAPPINGS_FILE) else {"forms": {}}
        cur_sections = json.load(open(D.SECTIONS_FILE, encoding="utf-8")) if os.path.exists(D.SECTIONS_FILE) else {"sections": []}
        mappings = build_mappings(specs, base)
        sections = build_sections(specs, cur_sections, mappings)
        with open(MAPPINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(mappings, f, indent=2, ensure_ascii=False)
        with open(D.SECTIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(sections, f, indent=2, ensure_ascii=False)
    except OSError:
        pass                                                     # a read-only config folder must not stop a publish; the studio keeps its earlier mappings
