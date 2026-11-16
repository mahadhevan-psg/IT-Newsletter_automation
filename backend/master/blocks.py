"""Response sheets of the category-based forms.

One response can hold several categories (a person answers YES or NO to each, fills the YES ones, then a few common questions).
The sheet therefore repeats titles - "Objectives and Rationale" appears in every category - so a row is understood by POSITION:

    common columns | gate, category fields | gate, category fields | ... | closing columns

Rows are read into dicts whose repeated titles are made unique ('Title', 'Title#2' ... see common.uniquify_headers) and whose key order is the
column order. expand() cuts such a row into one FLAT row per category answered: the common columns, that category's fields, the closing columns,
and the category's name under the form's category question. Flat rows look exactly like the single-category rows of the earlier forms, so the
importer, the review screen and the newsletter work on one entry (one category) at a time.

The layout lives in config/master_forms.json ("layout", "category_config"), generated from gform_scripts/new_forms.py.
"""
from typing import Any, Dict, List, Optional

from backend.master.common import base_title, norm_header

GATE = "do you want to submit"


def _spec(form_id: str) -> Dict[str, Any]:
    from backend.master import ingest
    return ingest.specs()["forms"][form_id]


def has_blocks(spec: Dict[str, Any]) -> bool:
    return bool(spec.get("layout"))


def sheet_headers(form_id: str) -> List[str]:
    """The response sheet's header row, column by column (what the Google Form writes; titles repeat)."""
    lay = _spec(form_id)["layout"]
    out = list(lay["common"])
    for b in lay["blocks"]:
        out.append(b["gate"])
        out.extend(b["fields"])
    out.extend(lay["closing"])
    return out


def questions_for(spec: Dict[str, Any], category: Optional[str], legacy: bool = True) -> List[Dict[str, Any]]:
    """The questions that apply to a response of this category (all the questions when the category is unknown). legacy=False leaves out the
    questions of the earlier form version (used for what is shown on screen)."""
    out = []
    for q in spec["questions"]:
        if q["type"] == "section" or (q.get("legacy") and not legacy):
            continue
        if q.get("cats") and category in spec["categories"] and category not in q["cats"]:
            continue
        out.append(q)
    return out


def category_title(spec: Dict[str, Any]) -> str:
    return next(q["q"] for q in spec["questions"] if q.get("key") == "category")


def category_of(spec: Dict[str, Any], by_norm: Dict[str, str]) -> Optional[str]:
    """The category named in a flat row (under the category question's title or an earlier title of it)."""
    for q in spec["questions"]:
        if q.get("key") == "category":
            for t in (q["q"], *q.get("aliases", [])):
                v = by_norm.get(norm_header(t))
                if v:
                    return v.strip()
    return None


def derive_title(vals: Dict[str, str], cfg: Dict[str, Any]) -> Optional[str]:
    """A title for an entry whose form has no title question: the first line of the first listed answer, shortened."""
    for key in cfg.get("title_from") or []:
        text = " ".join(str(vals.get(key) or "").split())
        if text:
            first = text.split(". ")[0] if len(text.split(". ")[0]) >= 12 else text
            if len(first) > 90:
                first = first[:87].rsplit(" ", 1)[0] + "..."
            return (cfg.get("title_prefix") or "") + first
    return None


def is_blocky(row: Dict[str, Any]) -> bool:
    return any(norm_header(base_title(k)).startswith(GATE) for k in row)


def _gate_category(spec: Dict[str, Any], gate_title: str, n: int) -> Optional[str]:
    g = norm_header(gate_title)
    best = None
    for name in spec["categories"]:
        if norm_header(name) and norm_header(name) in g and (best is None or len(name) > len(best)):
            best = name
    if best:
        return best
    return spec["categories"][n] if n < len(spec["categories"]) else None          # "Do you want to submit this category?": by order


def expand(form_id: str, row: Dict[str, Any]) -> List[Dict[str, str]]:
    """One response row -> one flat row per category answered (a row of the earlier single-category forms comes back as it is)."""
    spec = _spec(form_id)
    if not has_blocks(spec) or not is_blocky(row):
        return [dict(row)]
    keys = list(row.keys())
    gates = [i for i, k in enumerate(keys) if norm_header(base_title(k)).startswith(GATE)]
    widths = {b["category"]: len(b["fields"]) for b in spec["layout"]["blocks"]}
    rename = spec["layout"].get("closing_rename", {})
    cat_col = category_title(spec)
    top = {base_title(k): row[k] for k in keys[:gates[0]] if k}
    spans = []
    for n, gi in enumerate(gates):
        cat = _gate_category(spec, base_title(keys[gi]), n)
        end = gates[n + 1] if n + 1 < len(gates) else min(len(keys), gi + 1 + widths.get(cat, len(keys)))
        spans.append((cat, gi, end))
    closing = {}
    for k in keys[spans[-1][2]:]:
        t = base_title(k)
        closing[rename.get(t, t)] = row[k]
    out = []
    for cat, gi, end in spans:
        gate_value = str(row[keys[gi]] or "").strip().lower()
        fields = {base_title(k): row[k] for k in keys[gi + 1:end]}
        if cat is None or gate_value.startswith("no") or (not gate_value.startswith("yes") and not any(str(v or "").strip() for v in fields.values())):
            continue
        flat: Dict[str, str] = {}
        flat.update(top)
        flat[cat_col] = cat
        flat.update(fields)
        flat.update(closing)
        if not str(flat.get("Email Address") or "").strip():
            alt = next((v for k, v in flat.items() if norm_header(k) == "faculty email" and str(v or "").strip()), "")
            if alt:
                flat["Email Address"] = alt
        out.append(flat)
    return out


def expand_rows(form_id: str, rows: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    from backend.master import ingest
    if form_id not in ingest.specs()["forms"]:                 # a form the studio added itself: nothing to cut up
        return [dict(r) for r in rows]
    out: List[Dict[str, str]] = []
    for r in rows:
        out.extend(expand(form_id, r))
    return out


def response_key(form_id: str, flat: Dict[str, Any]) -> str:
    """Identity of one entry of a response: the submission time, the person and the category (a response holds one entry per category)."""
    n = {norm_header(k): str(v or "").strip() for k, v in flat.items()}
    return f"{n.get('timestamp', '')}|{n.get('email address', '').lower()}|{n.get(norm_header(category_title(_spec(form_id))), '')}"
