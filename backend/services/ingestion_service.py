import csv
import io
import json
from typing import Dict, Any, List, Optional
from database.db_manager import save_raw_response, create_canonical_entry, get_entries
from backend.services.normalization_service import NormalizationService
from backend.services.validation_service import ValidationService

def entry_key(e: Dict[str, Any]):
    """Identity of a submission: same title, people, date and sub-section means the same entry."""
    norm = lambda v: " ".join(str(v or "").lower().split())
    return (norm(e.get("title")), norm(e.get("author_or_person")), norm(e.get("event_date")), norm(e.get("category_id")))


class IngestionService:
    def __init__(self):
        self.normalizer = NormalizationService()
        self.validator = ValidationService()

    def process_single_submission(self, form_id: str, raw_data: Dict[str, Any], issue_id: str = "ISSUE_2026_V1I1", submitter_email: Optional[str] = None) -> Dict[str, Any]:
        """
        Preserves raw form submission and ingests it into normalized canonical database.
        """
        email = submitter_email or raw_data.get("Email Address") or raw_data.get("submitter_email") or ""
        
        # 1. Map Raw -> Canonical Field Entity
        canonical_entry = self.normalizer.normalize_response(form_id, raw_data, issue_id=issue_id)

        # 2. The same submission imported twice must not become two entries
        key = entry_key(canonical_entry)
        for existing in get_entries(issue_id=issue_id, section_id=canonical_entry.get("section_id")):
            if entry_key(existing) == key:
                return {"success": True, "duplicate": True, "entry_id": existing["entry_id"],
                        "response_id": existing.get("response_id"), "validation_errors": [], "canonical_entry": existing}

        # 3. Preserve the raw form submission
        response_id = save_raw_response(form_id, issue_id, email, raw_data)
        canonical_entry["response_id"] = response_id
        canonical_entry["submitter_email"] = email

        # 4. Validate Entry
        validation_errors = self.validator.validate_entry(canonical_entry)
        if validation_errors:
            canonical_entry["approval_status"] = "Draft"
            canonical_entry["rejection_reason"] = f"Validation warnings: {'; '.join(validation_errors)}"

        # 5. Store Canonical Entry in DB
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

    def process_excel_upload(self, form_id: str, file_bytes: bytes, issue_id: str = "ISSUE_2026_V1I1") -> List[Dict[str, Any]]:
        """
        Ingests batch responses directly from Excel (.xlsx) files.
        """
        try:
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
            sheet = wb.active
            headers = [str(cell.value).strip() if cell.value is not None else "" for cell in sheet[1]]
            results = []
            for row in sheet.iter_rows(min_row=2, values_only=True):
                raw_data = {}
                for idx, cell_val in enumerate(row):
                    if idx < len(headers) and headers[idx]:
                        raw_data[headers[idx]] = str(cell_val).strip() if cell_val is not None else ""
                if any(raw_data.values()):
                    res = self.process_single_submission(form_id, raw_data, issue_id=issue_id)
                    results.append(res)
            return results
        except Exception as e:
            # Fallback to CSV if reading fails
            return self.process_csv_upload(form_id, file_bytes.decode("utf-8", errors="ignore"), issue_id=issue_id)

