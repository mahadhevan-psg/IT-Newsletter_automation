import csv
import io
import json
from typing import Dict, Any, List, Optional
from database.db_manager import save_raw_response, create_canonical_entry
from backend.services.normalization_service import NormalizationService
from backend.services.validation_service import ValidationService

class IngestionService:
    def __init__(self):
        self.normalizer = NormalizationService()
        self.validator = ValidationService()

    def process_single_submission(self, form_id: str, raw_data: Dict[str, Any], issue_id: str = "ISSUE_2026_V1I1", submitter_email: Optional[str] = None) -> Dict[str, Any]:
        """
        Preserves raw form submission and ingests it into normalized canonical database.
        """
        email = submitter_email or raw_data.get("Email Address") or raw_data.get("submitter_email") or ""
        
        # 1. Save Raw Response
        response_id = save_raw_response(form_id, issue_id, email, raw_data)

        # 2. Map Raw -> Canonical Field Entity
        canonical_entry = self.normalizer.normalize_response(form_id, raw_data, issue_id=issue_id)
        canonical_entry["response_id"] = response_id
        canonical_entry["submitter_email"] = email

        # 3. Validate Entry
        validation_errors = self.validator.validate_entry(canonical_entry)
        if validation_errors:
            canonical_entry["approval_status"] = "Draft"
            canonical_entry["rejection_reason"] = f"Validation warnings: {'; '.join(validation_errors)}"

        # 4. Store Canonical Entry in DB
        entry_id = create_canonical_entry(canonical_entry)
        canonical_entry["entry_id"] = entry_id

        return {
            "success": True,
            "entry_id": entry_id,
            "response_id": response_id,
            "validation_errors": validation_errors,
            "canonical_entry": canonical_entry
        }

    def process_csv_upload(self, form_id: str, csv_content: str, issue_id: str = "ISSUE_2026_V1I1") -> List[Dict[str, Any]]:
        """
        Ingests batch responses from Google Sheets / CSV file upload.
        """
        reader = csv.DictReader(io.StringIO(csv_content))
        results = []
        for row in reader:
            res = self.process_single_submission(form_id, row, issue_id=issue_id)
            results.append(res)
        return results
