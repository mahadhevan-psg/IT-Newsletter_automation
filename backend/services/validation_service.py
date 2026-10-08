import json
import os
import re
from typing import Dict, Any, List

CONFIG_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "config")

class ValidationService:
    def __init__(self):
        self.rules_file = os.path.join(CONFIG_DIR, "validation_rules.json")
        self.load_rules()

    def load_rules(self):
        if os.path.exists(self.rules_file):
            with open(self.rules_file, "r", encoding="utf-8") as f:
                self.rules = json.load(f).get("rules", {})
        else:
            self.rules = {}

    def validate_entry(self, entry: Dict[str, Any]) -> List[str]:
        """
        Validates canonical entry fields against validation rules.
        Returns a list of error messages (empty list if valid).
        """
        errors = []

        # Validate Title
        title = entry.get("title", "").strip()
        t_rule = self.rules.get("title", {})
        if t_rule.get("required") and not title:
            errors.append(t_rule.get("error_message", "Title is required."))
        elif title and len(title) < t_rule.get("min_length", 1):
            errors.append(f"Title is too short (minimum {t_rule.get('min_length')} characters).")

        # Validate Description
        desc = entry.get("description", "").strip()
        d_rule = self.rules.get("description", {})
        if d_rule.get("required") and not desc:
            errors.append(d_rule.get("error_message", "Description is required."))
        elif desc and len(desc) < d_rule.get("min_length", 1):
            errors.append(f"Description is too short (minimum {d_rule.get('min_length')} characters).")

        # Validate URLs
        for url_field in ["photo_url", "evidence_url"]:
            url_val = entry.get(url_field, "").strip()
            if url_val:
                if not (url_val.startswith("http://") or url_val.startswith("https://") or url_val.startswith("drive://")):
                    errors.append(f"{url_field.replace('_', ' ').title()} must be a valid HTTP/HTTPS link.")

        return errors
