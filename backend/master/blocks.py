"""Response sheets of the category-based forms.

One response can hold several categories (the person picks a category, fills its section, then picks the next one or finishes). The sheet
repeats titles - "Target Audience" appears in several sections - so a row is understood by POSITION:

    common columns | "which category?", section fields | "which remaining category?", section fields | ... | closing columns

Rows are read into dicts whose repeated titles are made unique ('Title', 'Title#2' ... see common.uniquify_headers) and whose key order is the
column order. expand() cuts such a row into one FLAT row per section answered: the common columns, that section's fields, the closing columns,
and the category's name under the form's category question, so the importer, the review screen and the newsletter work on one entry at a time.

The layout lives in config/master_forms.json ("layout"), generated from gform_scripts/new_forms.py.
"""
from typing import Any, Dict, List, Optional

from backend.master.common import base_title, norm_header

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
    """The category named in a flat row (under the category question's title or an earlier title of it). A category the Admin renamed is
    recognised by its old name too."""
    for q in spec["questions"]:
        if q.get("key") == "category":
            for t in (q["q"], *q.get("aliases", [])):
                v = by_norm.get(norm_header(t))
                if v:
                    v = v.strip()
                    return spec.get("category_aliases", {}).get(v, v)
    return None


def derive_title(vals: Dict[str, str], cfg: Dict[str, Any]) -> Optional[str]:
    """A title for an entry whose form has no title question: the first line of the first listed answer, shortened (the category's name
    when none of those was answered)."""
    for key in cfg.get("title_from") or []:
        text = " ".join(str(vals.get(key) or "").split())
        if text:
            first = text.split(". ")[0] if len(text.split(". ")[0]) >= 12 else text
            if len(first) > 90:
                first = first[:87].rsplit(" ", 1)[0] + "..."
            return (cfg.get("title_prefix") or "") + first
    return cfg.get("title_fallback")


def _gates(spec: Dict[str, Any]) -> set:
    return {norm_header(b["gate"]) for b in spec["layout"]["blocks"]}


def is_blocky(spec: Dict[str, Any], row: Dict[str, Any]) -> bool:
    gates = _gates(spec)
    return any(norm_header(base_title(k)) in gates for k in row)


def expand(form_id: str, row: Dict[str, Any]) -> List[Dict[str, str]]:
    """One response row -> one flat row per section answered (a row that already holds one entry comes back as it is).
    The sheet has, in order: the common columns, then for every section a "which category ...?" column followed by that section's columns, then
    the closing columns."""
    spec = _spec(form_id)
    if not has_blocks(spec) or not is_blocky(spec, row):
        return [dict(row)]
    keys = list(row.keys())
    names = _gates(spec)
    gates = [i for i, k in enumerate(keys) if norm_header(base_title(k)) in names]
    cat_col = category_title(spec)
    top = {base_title(k): row[k] for k in keys[:gates[0]] if k}
    spans, end = [], gates[0]
    for gi, blk in zip(gates, spec["layout"]["blocks"]):
        end = min(len(keys), gi + 1 + len(blk["fields"]))
        spans.append((blk["category"], gi, end))
    rename = spec["layout"].get("closing_rename", {})                      # a closing column whose title a section also uses
    closing = {rename.get(base_title(k), base_title(k)): row[k] for k in keys[end:]}
    out = []
    for cat, gi, stop in spans:
        fields = {base_title(k): row[k] for k in keys[gi + 1:stop]}
        if cat not in spec["categories"] and cat not in spec.get("category_aliases", {}):
            continue
        if not any(str(v or "").strip() for v in fields.values()):
            continue
        flat: Dict[str, str] = {}
        flat.update(top)
        flat[cat_col] = spec.get("category_aliases", {}).get(cat, cat)
        flat.update(fields)
        flat.update(closing)
        if not str(flat.get("Email Address") or flat.get("Email") or "").strip():
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
