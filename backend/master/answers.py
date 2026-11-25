"""What an entry says, laid out the way the current forms ask it.

Submissions, Reports, My activities (and every person page) all show an entry through this module, which reads the PUBLISHED form
definitions. So the screens and downloads follow the data entry fields: when a field is added, renamed or retired in the Form builder, they
change with it, without any change here.
"""
import json
from typing import Any, Dict, Iterable, List, Optional

from backend.master import blocks, ingest
from backend.master.common import norm_header, parse_num

# never shown: filled in by the application, or no longer asked
HIDDEN_KEYS = {"category", "title", "is_landmark", "publish_permission", "authorization_confirmed"}
HIDDEN_TITLES = {"timestamp", "email address", "email", "accuracy and authorization confirmation", "permission to publish this submission",
                 "is this a landmark / milestone achievement?", "additional photos"}
MONEY_KEYS = {"funding_amount", "prize_amount", "budget_amount", "x_revenue"}
PEOPLE_LIST_KEYS = {"_participants", "_contributors"}                      # the people are listed (with names and classes) from their own table
ZONES = {"common": 0, "category": 1, "block": 1, "closing": 2}


def form_of(form_type: str) -> Optional[str]:
    return next((fid for fid, s in ingest.specs()["forms"].items() if s.get("form_type") == form_type), None)


def _asked(q: Dict[str, Any]) -> bool:
    return not (q.get("type") in ("section", "confirm") or q.get("key") in HIDDEN_KEYS or q.get("submitter") or q.get("auto") or q.get("derived"))


def questions(spec: Dict[str, Any], category: Optional[str]) -> List[Dict[str, Any]]:
    """The questions of a category in screen order; retired ones last (old entries still show what they answered)."""
    qs = [q for q in blocks.questions_for(spec, category, legacy=True) if _asked(q)]
    return sorted(qs, key=lambda q: (bool(q.get("legacy")), ZONES.get(q.get("zone"), 1)))


def _files(value: str) -> List[str]:
    return [v.strip() for v in str(value).split(", ") if v.strip().startswith(("media://", "http://", "https://"))]


def _inr(text: str) -> str:
    from backend.master.profiles import inr
    n = parse_num(text)
    return inr(n) if n is not None else text


def display(form_type: str, category: Optional[str], raw: Dict[str, Any]) -> Dict[str, List]:
    """{'facts': [[label, value]], 'notes': [[label, long text]], 'links': [{label, url}]} for one stored entry."""
    fid = form_of(form_type)
    spec = ingest.specs()["forms"].get(fid) if fid else None
    out: Dict[str, List] = {"facts": [], "notes": [], "links": []}
    by_norm = {norm_header(k): (k, str(v).strip()) for k, v in raw.items() if v is not None and str(v).strip()}
    used = set()
    for q in questions(spec, category) if spec else []:
        hit = next((by_norm[n] for n in (norm_header(t) for t in (q["q"], *q.get("aliases", []))) if n in by_norm and n not in used), None)
        if not hit:
            continue
        used.add(norm_header(hit[0]))
        value, label, kind = hit[1], q["q"], q.get("type")
        if q.get("key") in PEOPLE_LIST_KEYS:
            continue
        if kind in ("url", "file", "photo") or q.get("key") == "media_url":
            urls = _files(value)
            if urls:
                out["links"] += [{"label": label if len(urls) == 1 else f"{label} ({n})", "url": u} for n, u in enumerate(urls, 1)]
            else:
                out["facts"].append([label, value])
        elif kind in ("para", "roster_any"):
            out["notes"].append([label, value])
        else:
            out["facts"].append([label, _inr(value) if q.get("key") in MONEY_KEYS else value])
    # every question of the other categories is theirs, not this entry's; anything else the entry carries is kept, so nothing is lost
    known = {norm_header(t) for q in (spec["questions"] if spec else []) for t in (q.get("q", ""), *q.get("aliases", []))}
    for n, (title, value) in by_norm.items():
        if n not in used and n not in known and n not in HIDDEN_TITLES:
            urls = _files(value)
            if urls:
                out["links"] += [{"label": title, "url": u} for u in urls]
            else:
                out["facts"].append([title, value])
    extra = by_norm.get("additional photos")
    if extra:
        out["links"] += [{"label": f"Photo {n}", "url": u} for n, u in enumerate(_files(extra[1]), 2)]
    return out


def raw_of(conn, ids: Iterable[int]) -> Dict[int, tuple]:
    """{submission_id: (form_type, category, answers)} for a batch of submissions."""
    ids = list(ids)
    out: Dict[int, tuple] = {}
    for i in range(0, len(ids), 500):
        part = ids[i:i + 500]
        for r in conn.execute(f"SELECT submission_id, form_type, category, raw_json FROM form_submissions WHERE submission_id IN ({','.join('?' * len(part))})", part):
            try:
                raw = json.loads(r[3] or "{}")
            except ValueError:
                raw = {}
            out[r[0]] = (r[1], r[2], raw)
    return out


# ---------------------------------------------------------------- report columns
def report_columns(form_id: str) -> List[Dict[str, Any]]:
    """One downloadable column per data entry field of a form: {key, label, part, fields: {category or '*': [titles that hold it]}}."""
    spec = ingest.specs()["forms"].get(form_id)
    if not spec:
        return []
    cols: Dict[str, Dict[str, Any]] = {}
    for category in spec["categories"]:
        for q in questions(spec, category):
            if q.get("legacy") or q.get("key") in PEOPLE_LIST_KEYS:
                continue
            c = cols.setdefault(q["key"], {"labels": [], "categories": [], "titles": {}})
            if q["q"] not in c["labels"]:
                c["labels"].append(q["q"])
            if category not in c["categories"]:
                c["categories"].append(category)
            c["titles"].setdefault(category, []).extend(t for t in (q["q"], *q.get("aliases", [])) if t not in c["titles"].get(category, []))
    out = []
    for key, c in cols.items():
        label = " / ".join(c["labels"][:2]) + (" …" if len(c["labels"]) > 2 else "")
        one = len(c["categories"]) == 1 and len(spec["categories"]) > 1
        out.append({"key": f"f_{key.lstrip('_')}", "label": label, "part": c["categories"][0] if one else ("Details" if len(spec["categories"]) == 1 else "Asked in several categories"),
                    "titles": c["titles"]})
    return out


def value_for(column: Dict[str, Any], category: Optional[str], raw: Dict[str, Any]) -> Optional[str]:
    by_norm = {norm_header(k): str(v).strip() for k, v in raw.items() if v is not None and str(v).strip()}
    for title in column["titles"].get(category) or [t for ts in column["titles"].values() for t in ts]:
        v = by_norm.get(norm_header(title))
        if v:
            return v
    return None
