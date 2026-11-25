"""Which questions of a form apply to an entry of a given category, the category named in a row, and a title for entries whose
category asks for none."""
from typing import Any, Dict, List, Optional

from backend.master.common import norm_header


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
