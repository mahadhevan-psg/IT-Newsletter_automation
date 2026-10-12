import json
import os
import re
import uuid
from typing import Dict, Any, Tuple

CONFIG_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "config")

class NormalizationService:
    def __init__(self):
        self.mappings_file = os.path.join(CONFIG_DIR, "form_mappings.json")
        self.load_mappings()

    def load_mappings(self):
        if os.path.exists(self.mappings_file):
            try:
                with open(self.mappings_file, "r", encoding="utf-8") as f:
                    self.mappings = json.load(f).get("forms", {})
            except Exception as e:
                print("Error loading form mappings:", e)
                self.mappings = {}
        else:
            self.mappings = {}

    def reload_mappings(self):
        self.load_mappings()

    def normalize_response(self, form_key: str, raw_data: Dict[str, Any], issue_id: str = "ISSUE_2026_V1I1") -> Dict[str, Any]:
        """
        Maps raw Google Form question-value pairs to canonical entity fields.
        Preserves custom / extra questions in extra_fields and extra_data_json.
        """
        form_spec = self.mappings.get(form_key)
        if not form_spec:
            # Fallback for unknown form key
            form_spec = self._guess_form_spec(raw_data)

        section_id = form_spec.get("section_id", "sec_research")
        field_mappings = form_spec.get("field_mappings", {})
        category_field = form_spec.get("category_field")
        category_map = form_spec.get("category_map", {})

        canonical_entry = {
            "entry_id": f"ENTRY_{uuid.uuid4().hex[:8].upper()}",
            "issue_id": issue_id,
            "section_id": section_id,
            "category_id": "cat_gen",
            "title": "",
            "author_or_person": "",
            "organization_or_venue": "",
            "event_date": "",
            "impact_or_indexing": "",
            "grant_or_prize_amount": "",
            "description": "",
            "photo_url": "",
            "photo_caption": "",
            "evidence_url": "",
            "badge_tag": "",
            "featured_flag": False,
            "display_order": 100,
            "approval_status": "Draft",
            "submitter_email": "",
            "extra_fields": {}
        }

        # Map fields
        for raw_question, raw_value in raw_data.items():
            if raw_value is None or raw_value == "":
                continue
            str_val = str(raw_value).strip()
            q_clean = raw_question.strip()
            q_lower = q_clean.lower()

            # Check category selection question
            if category_field and q_lower == category_field.strip().lower():
                canonical_entry["category_id"] = category_map.get(str_val, "cat_gen")
                continue

            # Check spotlight / landmark question
            if "milestone" in q_lower or "spotlight" in q_lower or "landmark" in q_lower:
                if "yes" in str_val.lower() or "nominate" in str_val.lower():
                    canonical_entry["featured_flag"] = True

            # Check field mapping
            canonical_key = field_mappings.get(q_clean)
            if canonical_key and canonical_key in canonical_entry:
                canonical_entry[canonical_key] = self._clean_value(canonical_key, str_val)
            else:
                # Capture in extra_fields for full extensibility
                canonical_entry["extra_fields"][q_clean] = str_val
                if canonical_key:
                    canonical_entry["extra_fields"][canonical_key] = str_val

        # Fallback category detection if not set
        if canonical_entry["category_id"] == "cat_gen":
            for cat_text, cat_id in category_map.items():
                for v in raw_data.values():
                    if str(v).strip() == cat_text:
                        canonical_entry["category_id"] = cat_id
                        break

        # Fallback badge_tag from impact_or_indexing or grant_or_prize_amount if empty
        if not canonical_entry["badge_tag"]:
            if canonical_entry.get("impact_or_indexing"):
                canonical_entry["badge_tag"] = canonical_entry["impact_or_indexing"]
            elif canonical_entry.get("grant_or_prize_amount"):
                canonical_entry["badge_tag"] = canonical_entry["grant_or_prize_amount"]

        # Defaults & sanitization
        if not canonical_entry["title"]:
            canonical_entry["title"] = "Untitled Submission"
        if not canonical_entry["author_or_person"]:
            canonical_entry["author_or_person"] = canonical_entry.get("submitter_email", "Contributor")

        canonical_entry["extra_data_json"] = json.dumps(canonical_entry["extra_fields"])

        return canonical_entry

    def _clean_value(self, key: str, value: str) -> Any:
        if key in ["photo_url", "evidence_url"]:
            # Clean Drive / Cloud links
            return value
        elif key == "event_date":
            return value
        return value

    def _guess_form_spec(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        return self.mappings.get("form_research", {})
