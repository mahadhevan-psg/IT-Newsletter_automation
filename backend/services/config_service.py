import json
import os
import re
from typing import Dict, Any, List, Optional
from database.db_manager import add_or_update_section, delete_section, get_sections_and_categories, get_visual_template

CONFIG_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "config")

CANONICAL_FIELD_OPTIONS = [
    {"tag": "title", "label": "Title / Heading", "type": "text", "description": "Title of paper, event, project, award, or initiative"},
    {"tag": "author_or_person", "label": "Authors / Contributor(s)", "type": "text", "description": "Faculty, student, or team names"},
    {"tag": "organization_or_venue", "label": "Venue / Organization / Publisher", "type": "text", "description": "Journal, company, conference, or awarding body"},
    {"tag": "event_date", "label": "Date of Event / Award / Publication", "type": "date", "description": "Date or date range"},
    {"tag": "description", "label": "Description / Abstract / Highlights", "type": "textarea", "description": "Summary narrative of the activity"},
    {"tag": "photo_url", "label": "Photo Link (Cloud / Drive URL)", "type": "image", "description": "Direct image or Cloud/Drive link for photo"},
    {"tag": "photo_caption", "label": "Photo Caption & Persons in Image", "type": "text", "description": "Caption description for photo"},
    {"tag": "evidence_url", "label": "Evidence / Certificate / Document URL", "type": "url", "description": "Link to proof, certificate, paper or report"},
    {"tag": "badge_tag", "label": "Key Impact Badge / Metric Pill", "type": "text", "description": "Short badge tag (e.g., Scopus Q1, 1st Place)"},
    {"tag": "grant_or_prize_amount", "label": "Grant / Prize / Amount / DOI", "type": "text", "description": "Grant funding amount, prize money, or DOI"},
    {"tag": "impact_or_indexing", "label": "Impact Factor / Indexing / Level", "type": "text", "description": "Indexing level or target audience"},
    {"tag": "featured_flag", "label": "Landmark / Milestone Spotlight Flag", "type": "select", "description": "Nominate as featured landmark entry"},
    {"tag": "submitter_email", "label": "Submitter Email Address", "type": "text", "description": "Email address of form submitter"},
    {"tag": "submission_timestamp", "label": "Form Submission Timestamp", "type": "text", "description": "Google Form submission timestamp"},
    {"tag": "category_id", "label": "Subcategory Selector", "type": "select", "description": "Maps to subcategory within section"},
    {"tag": "custom", "label": "Custom Field Tag", "type": "text", "description": "Any custom tag not in standard canonical registry"}
]

class ConfigService:
    def __init__(self, normalizer=None):
        self.normalizer = normalizer
        self.mappings_file = os.path.join(CONFIG_DIR, "form_mappings.json")
        self.sections_file = os.path.join(CONFIG_DIR, "section_categories.json")
        self.section_layouts_file = os.path.join(CONFIG_DIR, "section_layouts.json")

    def _read_mappings(self) -> Dict[str, Any]:
        if os.path.exists(self.mappings_file):
            try:
                with open(self.mappings_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"version": "1.0", "forms": {}}

    def _save_mappings(self, data: Dict[str, Any]):
        os.makedirs(os.path.dirname(self.mappings_file), exist_ok=True)
        with open(self.mappings_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        if self.normalizer:
            self.normalizer.reload_mappings()

    def _read_sections(self) -> Dict[str, Any]:
        if os.path.exists(self.sections_file):
            try:
                with open(self.sections_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"version": "1.0", "sections": []}

    def _save_sections(self, data: Dict[str, Any]):
        os.makedirs(os.path.dirname(self.sections_file), exist_ok=True)
        with open(self.sections_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def get_canonical_field_options(self) -> List[Dict[str, Any]]:
        return CANONICAL_FIELD_OPTIONS

    def get_all_forms(self) -> List[Dict[str, Any]]:
        mappings_data = self._read_mappings()
        forms_dict = mappings_data.get("forms", {})
        
        # Load sections for friendly section names
        sec_dict = {s["section_id"]: s for s in get_sections_and_categories()}

        results = []
        for form_id, fspec in forms_dict.items():
            section_id = fspec.get("section_id", "")
            sec_info = sec_dict.get(section_id, {})
            section_name = sec_info.get("name", section_id)
            
            column_metadata = fspec.get("column_metadata", {})
            field_mappings = fspec.get("field_mappings", {})
            category_field = fspec.get("category_field", "")
            category_map = fspec.get("category_map", {})

            # Synthesize structured column list
            columns = []
            
            # If category_field is set, ensure it's listed as a column
            all_col_names = set(field_mappings.keys())
            if category_field:
                all_col_names.add(category_field)
            for col_meta_name in column_metadata.keys():
                all_col_names.add(col_meta_name)

            for col_name in all_col_names:
                meta = column_metadata.get(col_name, {})
                canonical_tag = field_mappings.get(col_name) or meta.get("canonical_tag")
                
                if col_name == category_field:
                    col_type = "select"
                    canonical_tag = "category_id"
                    req = True
                else:
                    col_type = meta.get("type") or self._infer_type(canonical_tag, col_name)
                    req = meta.get("required", False)
                    if not canonical_tag:
                        canonical_tag = self._infer_canonical_tag(col_name)

                columns.append({
                    "name": col_name,
                    "canonical_tag": canonical_tag or "custom",
                    "type": col_type,
                    "required": req,
                    "description": meta.get("description", "")
                })

            # Sort columns logically: category field & title first, timestamp/email first or last
            columns.sort(key=lambda c: (
                0 if c["name"] == category_field else
                1 if c["canonical_tag"] == "title" else
                2 if c["canonical_tag"] == "author_or_person" else
                9 if c["name"] in ["Timestamp", "Email Address"] else 5,
                c["name"]
            ))

            results.append({
                "form_id": form_id,
                "form_name": fspec.get("form_name", form_id),
                "section_id": section_id,
                "section_name": section_name,
                "category_field": category_field,
                "category_map": category_map,
                "columns": columns,
                "total_columns": len(columns),
                "raw_mappings": field_mappings
            })

        return results

    # ---- section -> layout assignment (layouts are shared; any section can use any layout)
    def _layout_map(self) -> Dict[str, str]:
        if os.path.exists(self.section_layouts_file):
            try:
                with open(self.section_layouts_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def get_section_layouts(self) -> Dict[str, str]:
        return self._layout_map()

    def set_section_layout(self, section_id: str, template_id: Optional[str]):
        data = self._layout_map()
        if template_id:
            data[section_id] = template_id
        else:
            data.pop(section_id, None)
        os.makedirs(os.path.dirname(self.section_layouts_file), exist_ok=True)
        with open(self.section_layouts_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def clear_layout_assignments(self, template_id: str):
        data = {k: v for k, v in self._layout_map().items() if v != template_id}
        with open(self.section_layouts_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def get_active_layout(self, section_id: str) -> Optional[Dict[str, Any]]:
        """Return {template_id, name, layout} for the layout assigned to a section, or None."""
        tid = self._layout_map().get(section_id)
        if not tid:
            return None
        tpl = get_visual_template(tid)
        if tpl and tpl.get("layout"):
            return {"template_id": tid, "name": tpl["name"], "layout": tpl["layout"]}
        return None

    def get_form(self, form_id: str) -> Optional[Dict[str, Any]]:
        forms = self.get_all_forms()
        return next((f for f in forms if f["form_id"] == form_id), None)

    def create_form(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Creates a new form configuration and binds or creates its corresponding section.
        """
        form_id = re.sub(r"[^a-zA-Z0-9_]", "_", payload.get("form_id", "").strip().lower())
        if not form_id:
            raise ValueError("Form ID is required")
        if not form_id.startswith("form_"):
            form_id = f"form_{form_id}"

        form_name = payload.get("form_name", f"Form {form_id}")
        section_id = payload.get("section_id", "").strip()
        section_name = payload.get("section_name", "").strip() or form_name
        
        if not section_id:
            section_id = f"sec_{form_id.replace('form_', '')}"

        # Check or create section in section_categories.json and DB
        sec_data = self._read_sections()
        sec_list = sec_data.get("sections", [])
        existing_sec = next((s for s in sec_list if s["section_id"] == section_id), None)

        category_map = payload.get("category_map", {})
        subcategories = []
        for cat_label, cat_id in category_map.items():
            subcategories.append({"category_id": cat_id, "name": cat_label})

        if not existing_sec:
            new_sec = {
                "section_id": section_id,
                "name": section_name,
                "display_order": len(sec_list) + 1,
                "enabled": True,
                "template_file": f"templates/{section_id}_section_template.docx",
                "subcategories": subcategories
            }
            sec_list.append(new_sec)
            sec_data["sections"] = sec_list
            self._save_sections(sec_data)
            add_or_update_section(section_id, section_name, len(sec_list), True, new_sec["template_file"], subcategories)
        elif subcategories:
            # Merge subcategories
            existing_cats = {c["category_id"]: c for c in existing_sec.get("subcategories", [])}
            for sc in subcategories:
                existing_cats[sc["category_id"]] = sc
            existing_sec["subcategories"] = list(existing_cats.values())
            self._save_sections(sec_data)
            add_or_update_section(section_id, existing_sec["name"], existing_sec.get("display_order", 10), True, existing_sec.get("template_file", ""), existing_sec["subcategories"])

        # Prepare field mappings and metadata
        columns = payload.get("columns", [])
        field_mappings = {}
        column_metadata = {}
        for col in columns:
            col_name = col.get("name", "").strip()
            if not col_name:
                continue
            canonical_tag = col.get("canonical_tag", "custom").strip()
            field_mappings[col_name] = canonical_tag
            column_metadata[col_name] = {
                "canonical_tag": canonical_tag,
                "type": col.get("type", "text"),
                "required": bool(col.get("required", False)),
                "description": col.get("description", "")
            }

        # Add to form_mappings.json
        mappings_data = self._read_mappings()
        mappings_data["forms"][form_id] = {
            "form_name": form_name,
            "section_id": section_id,
            "category_field": payload.get("category_field", ""),
            "category_map": category_map,
            "field_mappings": field_mappings,
            "column_metadata": column_metadata
        }
        self._save_mappings(mappings_data)

        return self.get_form(form_id)

    def update_form(self, form_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Updates an existing form's title, section, category field/map, and columns.
        """
        mappings_data = self._read_mappings()
        forms = mappings_data.get("forms", {})
        if form_id not in forms:
            raise ValueError(f"Form '{form_id}' not found")

        fspec = forms[form_id]
        if "form_name" in payload:
            fspec["form_name"] = payload["form_name"]
        if "section_id" in payload:
            fspec["section_id"] = payload["section_id"]
        if "category_field" in payload:
            fspec["category_field"] = payload["category_field"]
        if "category_map" in payload:
            fspec["category_map"] = payload["category_map"]

        if "columns" in payload:
            field_mappings = {}
            column_metadata = {}
            for col in payload["columns"]:
                col_name = col.get("name", "").strip()
                if not col_name:
                    continue
                canonical_tag = col.get("canonical_tag", "custom").strip()
                field_mappings[col_name] = canonical_tag
                column_metadata[col_name] = {
                    "canonical_tag": canonical_tag,
                    "type": col.get("type", "text"),
                    "required": bool(col.get("required", False)),
                    "description": col.get("description", "")
                }
            fspec["field_mappings"] = field_mappings
            fspec["column_metadata"] = column_metadata

        self._save_mappings(mappings_data)
        self._sync_subcategories(fspec.get("section_id", ""), fspec.get("category_map", {}))
        return self.get_form(form_id)

    def _sync_subcategories(self, section_id: str, category_map: Dict[str, str]):
        """Make sure every sub-section option of a form exists on its section."""
        if not section_id or not category_map:
            return
        sec_data = self._read_sections()
        sec = next((s for s in sec_data.get("sections", []) if s["section_id"] == section_id), None)
        if not sec:
            return
        existing = {c["category_id"]: c for c in sec.get("subcategories", [])}
        changed = False
        for label, cat_id in category_map.items():
            if cat_id not in existing:
                existing[cat_id] = {"category_id": cat_id, "name": label}
                changed = True
        if changed:
            sec["subcategories"] = list(existing.values())
            self._save_sections(sec_data)
            add_or_update_section(section_id, sec["name"], sec.get("display_order", 10), True, sec.get("template_file", ""), sec["subcategories"])

    def delete_form(self, form_id: str) -> bool:
        mappings_data = self._read_mappings()
        forms = mappings_data.get("forms", {})
        if form_id in forms:
            del forms[form_id]
            self._save_mappings(mappings_data)
            return True
        return False

    def add_or_update_column(self, form_id: str, col_payload: Dict[str, Any]) -> Dict[str, Any]:
        mappings_data = self._read_mappings()
        forms = mappings_data.get("forms", {})
        if form_id not in forms:
            raise ValueError(f"Form '{form_id}' not found")

        fspec = forms[form_id]
        field_mappings = fspec.setdefault("field_mappings", {})
        column_metadata = fspec.setdefault("column_metadata", {})

        col_name = col_payload.get("name", "").strip()
        if not col_name:
            raise ValueError("Column name is required")

        canonical_tag = col_payload.get("canonical_tag", "custom").strip()
        field_mappings[col_name] = canonical_tag
        column_metadata[col_name] = {
            "canonical_tag": canonical_tag,
            "type": col_payload.get("type") or self._infer_type(canonical_tag, col_name),
            "required": bool(col_payload.get("required", False)),
            "description": col_payload.get("description", "")
        }

        self._save_mappings(mappings_data)
        return self.get_form(form_id)

    def delete_column(self, form_id: str, col_name: str) -> Dict[str, Any]:
        mappings_data = self._read_mappings()
        forms = mappings_data.get("forms", {})
        if form_id not in forms:
            raise ValueError(f"Form '{form_id}' not found")

        fspec = forms[form_id]
        field_mappings = fspec.get("field_mappings", {})
        column_metadata = fspec.get("column_metadata", {})

        if col_name in field_mappings:
            del field_mappings[col_name]
        if col_name in column_metadata:
            del column_metadata[col_name]

        self._save_mappings(mappings_data)
        return self.get_form(form_id)

    def bulk_import_columns(self, form_id: str, raw_headers_text: str) -> Dict[str, Any]:
        """
        Takes raw comma-separated, tab-separated, or newline-separated Google Form headers,
        infers canonical tags & types, and updates the form columns.
        """
        # Split by comma or newline
        # A pasted Sheets header row is tab-separated; only split on commas for single-line input
        separator = r"[\r\n\t]+" if re.search(r"[\r\n\t]", raw_headers_text.strip()) else r","
        lines = [line.strip() for line in re.split(separator, raw_headers_text) if line.strip()]
        if not lines:
            raise ValueError("No valid column headers found in input")

        mappings_data = self._read_mappings()
        forms = mappings_data.get("forms", {})
        if form_id not in forms:
            raise ValueError(f"Form '{form_id}' not found")

        fspec = forms[form_id]
        field_mappings = fspec.setdefault("field_mappings", {})
        column_metadata = fspec.setdefault("column_metadata", {})

        for header in lines:
            header_clean = header.strip()
            if not header_clean:
                continue
            if header_clean in field_mappings and header_clean in column_metadata:
                continue # preserve existing mapping

            inferred_tag = self._infer_canonical_tag(header_clean)
            inferred_type = self._infer_type(inferred_tag, header_clean)
            
            field_mappings[header_clean] = inferred_tag
            column_metadata[header_clean] = {
                "canonical_tag": inferred_tag,
                "type": inferred_type,
                "required": False,
                "description": "Auto-imported from Google Form headers"
            }

        self._save_mappings(mappings_data)
        return self.get_form(form_id)

    def analyze_script(self, script: str) -> List[Dict[str, Any]]:
        """Parse an Apps Script and describe each form it builds: columns with detected tags, category question and options."""
        existing = {f["form_name"].strip().lower(): f["form_id"] for f in self.get_all_forms()}
        result = []
        for f in parse_form_script(script):
            columns, category_field, category_map = [], "", {}
            choice_questions = [q for q in f["questions"] if len(q["choices"]) >= 2]
            for q in f["questions"]:
                tag = self._infer_canonical_tag(q["name"])
                columns.append({"name": q["name"], "canonical_tag": tag, "required": q["required"],
                                "type": self._infer_type(tag, q["name"])})
            cat_col = next((c for c in columns if c["canonical_tag"] == "category_id"), None)
            if not cat_col:   # no obvious name: the first choice question that is not the spotlight yes/no
                q = next((q for q in choice_questions if self._infer_canonical_tag(q["name"]) != "featured_flag" and len(q["choices"]) > 2), None)
                cat_col = next((c for c in columns if q and c["name"] == q["name"]), None)
                if cat_col:
                    cat_col["canonical_tag"], cat_col["type"] = "category_id", "select"
            if cat_col:
                cat_col["required"] = True
                category_field = cat_col["name"]
                q = next(q for q in f["questions"] if q["name"] == category_field)
                category_map = {label: "cat_" + re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")[:24] for label in q["choices"]}
            result.append({"title": f["title"], "columns": columns, "category_field": category_field,
                           "category_map": category_map, "existing_form_id": existing.get(f["title"].strip().lower())})
        return result

    def _infer_canonical_tag(self, col_name: str) -> str:
        s = col_name.lower().strip()
        if "timestamp" in s:
            return "submission_timestamp"
        if "email" in s:
            return "submitter_email"
        if any(w in s for w in ["author", "team", "investigator", "faculty full name", "student name", "names of student", "convener", "coordinator",
                              "full name", "your name", "contributor", "presenter", "speaker", "team member", "faculty name"]):
            return "author_or_person"
        if any(w in s for w in ["title of publication", "title of award", "name of competition", "event title", "title of event", "paper title", "project title", "title"]):
            return "title"
        if any(w in s for w in ["photo caption", "persons in image", "caption"]):
            return "photo_caption"
        if any(w in s for w in ["evidence", "certificate", "proof", "report link", "flyer", "brochure", "paper link"]):
            return "evidence_url"
        if any(w in s for w in ["photo", "image", "picture", "drive url", "cloud url"]):
            return "photo_url"
        if any(w in s for w in ["badge", "metric", "level"]):
            return "badge_tag"
        if any(w in s for w in ["doi", "grant amount", "prize", "cash prize", "ctc", "rank", "position", "patent number"]):
            return "grant_or_prize_amount"
        if any(w in s for w in ["impact factor", "indexing", "scopus", "web of science", "q1", "q2"]):
            return "impact_or_indexing"
        if any(w in s for w in ["journal", "publisher", "agency", "organization", "company", "institute", "body", "host"]):
            return "organization_or_venue"
        if any(w in s for w in ["date", "duration"]):
            return "event_date"
        if any(w in s for w in ["abstract", "summary", "description", "highlights", "outcomes", "overview"]):
            return "description"
        if any(w in s for w in ["landmark", "milestone", "spotlight"]):
            return "featured_flag"
        if "category" in s:
            return "category_id"
        return re.sub(r"[^a-zA-Z0-9_]", "_", s)[:30] or "custom"

    def _infer_type(self, canonical_tag: Optional[str], col_name: str) -> str:
        tag = (canonical_tag or "").lower()
        col = col_name.lower()
        if tag == "description" or any(w in col for w in ["abstract", "summary", "description", "details", "overview"]):
            return "textarea"
        if tag == "photo_url" or any(w in col for w in ["photo", "image"]):
            return "image"
        if tag in ["evidence_url"] or any(w in col for w in ["link", "url", "proof", "doi"]):
            return "url"
        if tag == "event_date" or any(w in col for w in ["date"]):
            return "date"
        if tag == "featured_flag":
            return "select"
        if tag == "category_id":
            return "select"
        return "text"


# ---------------------------------------------------------------------------
# Reading the questions out of a Google Apps Script that builds a form
# ---------------------------------------------------------------------------
_STR = r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|`(?:[^`\\]|\\.)*`'
_SCRIPT_TOKENS = re.compile(
    r"(?P<form>FormApp\s*\.\s*create\(\s*(?P<form_arg>" + _STR + r")[^)]*\))"
    r"|(?P<item>\.\s*add(?P<kind>\w+?)Item\(\s*\))"
    r"|(?<!form)(?P<title>\.\s*setTitle\(\s*(?P<title_arg>" + _STR + r")\s*\))"
    r"|(?P<req>\.\s*setRequired\(\s*(?P<req_arg>true|false)\s*\))"
    r"|(?P<choices>\.\s*setChoiceValues\(\s*\[(?P<choices_arg>.*?)\]\s*\))",
    re.S,
)
_NON_QUESTIONS = {"PageBreak", "SectionHeader", "Image", "Video"}


def _unquote(s: str) -> str:
    body = s[1:-1]
    return re.sub(r"\\(.)", lambda m: {"n": " ", "t": " "}.get(m.group(1), m.group(1)), body)


def parse_form_script(script: str) -> List[Dict[str, Any]]:
    """Return [{title, questions: [{name, kind, required, choices}]}] for every form the script builds."""
    forms: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    item: Optional[Dict[str, Any]] = None
    # a script made of several functions: only code after the first FormApp.create belongs to a form
    for m in _SCRIPT_TOKENS.finditer(re.sub(r"//[^\n]*", "", script)):
        if m.group("form"):
            current = {"title": _unquote(m.group("form_arg")), "questions": []}
            forms.append(current)
            item = None
        elif current is None:
            continue
        elif m.group("item"):
            kind = m.group("kind")
            item = None if kind in _NON_QUESTIONS else {"name": "", "kind": kind, "required": False, "choices": []}
            if item:
                current["questions"].append(item)
        elif m.group("title") and item is not None and not item["name"]:
            item["name"] = _unquote(m.group("title_arg")).strip()
        elif m.group("req") and item is not None:
            item["required"] = m.group("req_arg") == "true"
        elif m.group("choices") and item is not None:
            item["choices"] = [_unquote(s) for s in re.findall(_STR, m.group("choices_arg"))]
    for f in forms:
        f["questions"] = [q for q in f["questions"] if q["name"]]
    return [f for f in forms if f["questions"]]
