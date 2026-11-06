"""
Content of the pages that come before the sections: the HOD's Desk (with vision and mission)
and the editorial page. Stored as one JSON file; photos are uploaded into output/uploads.
"""
import json
import os
import re
import uuid
from typing import Dict, Any, Optional

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CONFIG_FILE = os.path.join(ROOT, "config", "front_matter.json")
UPLOAD_DIR = os.path.join(ROOT, "output", "uploads")
POINTS = 5
STUDENTS = 4
IMAGE_TYPES = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp")


def default_front_matter() -> Dict[str, Any]:
    return {
        "cover": {"photo": ""},
        "hod": {"name": "", "designation": "Head of the Department", "message": "", "photo": ""},
        "vision": [""] * POINTS,
        "mission": [""] * POINTS,
        "advisor": {"name": "", "designation": "Faculty Advisor", "photo": ""},
        "students": [{"name": "", "year": "", "photo": ""} for _ in range(STUDENTS)],
    }


def _text(v: Any) -> str:
    return str(v or "").strip()


def _clean(data: Dict[str, Any]) -> Dict[str, Any]:
    """Coerce whatever was posted into the fixed shape (5 bullets each, 4 students)."""
    base = default_front_matter()
    hod, adv = data.get("hod") or {}, data.get("advisor") or {}
    base["cover"]["photo"] = _text((data.get("cover") or {}).get("photo"))
    for key in base["hod"]:
        base["hod"][key] = _text(hod.get(key)) or base["hod"][key] if key == "designation" else _text(hod.get(key))
    for key in base["advisor"]:
        base["advisor"][key] = _text(adv.get(key)) or base["advisor"][key] if key == "designation" else _text(adv.get(key))
    for key in ("vision", "mission"):
        items = [_text(x) for x in (data.get(key) or [])][:POINTS]
        base[key] = items + [""] * (POINTS - len(items))
    students = (data.get("students") or [])[:STUDENTS]
    for i, s in enumerate(students):
        base["students"][i] = {k: _text((s or {}).get(k)) for k in ("name", "year", "photo")}
    return base


class FrontMatterService:
    def get(self) -> Dict[str, Any]:
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    return _clean(json.load(f))
            except Exception:
                pass
        return default_front_matter()

    def save(self, data: Dict[str, Any]) -> Dict[str, Any]:
        clean = _clean(data)
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(clean, f, indent=2, ensure_ascii=False)
        return clean

    def save_upload(self, filename: str, content: bytes) -> str:
        """Store a photo and return the path to keep in the front matter (relative to the project)."""
        ext = os.path.splitext(filename or "")[1].lower()
        if ext not in IMAGE_TYPES:
            raise ValueError("Please upload an image (jpg, png, gif, webp or bmp).")
        stem = re.sub(r"[^a-z0-9]+", "_", os.path.splitext(os.path.basename(filename))[0].lower()).strip("_")[:30] or "photo"
        name = f"{stem}_{uuid.uuid4().hex[:6]}{ext}"
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        with open(os.path.join(UPLOAD_DIR, name), "wb") as f:
            f.write(content)
        return f"output/uploads/{name}"

    @staticmethod
    def resolve_path(value: str) -> Optional[str]:
        """A stored photo value as something the image loader understands (URLs pass through)."""
        value = _text(value)
        if not value or value.startswith(("http://", "https://")) or os.path.isabs(value):
            return value or None
        return os.path.join(ROOT, value)
