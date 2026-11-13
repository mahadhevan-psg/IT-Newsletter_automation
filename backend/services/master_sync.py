"""
The newsletter reads its entries from the master database.

Every form submission lives in the master database (form_submissions and its detail tables). This service turns the
submissions that have not reached the newsletter yet into newsletter entries (approved by default: an editor only has to reject what should stay out)
and records the link on the submission (newsletter_entry_id), so running it again never creates a second entry.
Names of students and faculty are looked up from the master records, so the forms only need roll numbers / employee IDs.
"""
import json
from typing import Any, Dict, List, Optional

from backend.master.common import person_name
from backend.services.normalization_service import NormalizationService
from backend.services.validation_service import ValidationService
from database.db_manager import create_canonical_entry, save_raw_response
from database.master_db import db

FORM_FOR_TYPE = {"STUDENT": "form_student", "RESEARCH": "form_research", "FACULTY": "form_faculty",
                 "DEPARTMENT": "form_departmental", "OUTREACH": "form_industry"}


class MasterSync:
    def __init__(self, normalizer: Optional[NormalizationService] = None):
        self.normalizer = normalizer or NormalizationService()
        self.validator = ValidationService()

    def pending(self, ay_id: Optional[str] = None) -> List[Dict[str, Any]]:
        sql = ("SELECT submission_id, form_type, ay_id, event_date, submitter_email, is_landmark, publish_permission, raw_json "
               "FROM form_submissions WHERE newsletter_entry_id IS NULL")
        args: List[Any] = []
        if ay_id:
            sql += " AND ay_id = ?"
            args.append(ay_id)
        with db() as conn:
            return [dict(r) for r in conn.execute(sql + " ORDER BY submission_id", args)]

    def sync(self, issue_id: str = "ISSUE_2026_V1I1", ay_id: Optional[str] = None) -> Dict[str, Any]:
        """Create a newsletter entry for every submission that has none. A submission whose author answered "No" to
        the publish-permission question is left out and stays unlinked."""
        created, skipped, failed = 0, 0, []
        for sub in self.pending(ay_id):
            if sub["publish_permission"] == 0:
                skipped += 1
                continue
            try:
                entry_id = self._create_entry(sub, issue_id)
                with db() as conn:
                    conn.execute("UPDATE form_submissions SET newsletter_entry_id = ? WHERE submission_id = ?", (entry_id, sub["submission_id"]))
                created += 1
            except Exception as e:                              # one bad row never blocks the rest
                failed.append({"submission_id": sub["submission_id"], "error": str(e)})
        with db() as conn:
            total = conn.execute("SELECT COUNT(*) FROM form_submissions").fetchone()[0]
        return {"success": True, "created": created, "skipped_no_permission": skipped, "failed": failed, "submissions_in_master": total}

    def _create_entry(self, sub: Dict[str, Any], issue_id: str) -> str:
        form_id = FORM_FOR_TYPE[sub["form_type"]]
        raw = json.loads(sub["raw_json"])
        entry = self.normalizer.normalize_response(form_id, raw, issue_id=issue_id)
        if not entry.get("event_date") and sub.get("event_date"):
            entry["event_date"] = sub["event_date"]
        if sub.get("is_landmark"):
            entry["featured_flag"] = True
        if not entry.get("author_or_person") or entry["author_or_person"] == "Contributor":
            entry["author_or_person"] = self._people(sub["submission_id"], sub["form_type"]) or entry.get("author_or_person", "")
        email = sub.get("submitter_email") or ""
        entry["submitter_email"] = email
        entry["response_id"] = save_raw_response(form_id, issue_id, email, raw)
        problems = self.validator.validate_entry(entry)
        if problems:
            entry["rejection_reason"] = f"Validation warnings: {'; '.join(problems)}"
        return create_canonical_entry(entry)

    @staticmethod
    def _people(submission_id: int, form_type: str) -> str:
        """Names for the byline, from the master records, when the form row carried none."""
        with db() as conn:
            if form_type == "STUDENT":
                rows = conn.execute("SELECT roll_no, name FROM student_achievement_participants WHERE submission_id = ? ORDER BY line_no", (submission_id,)).fetchall()
                return ", ".join(r["name"] or person_name(r["roll_no"], conn) or r["roll_no"] or "" for r in rows)
            if form_type == "RESEARCH":
                rows = conn.execute("SELECT name, emp_id, roll_no FROM research_contributors WHERE submission_id = ? ORDER BY author_order", (submission_id,)).fetchall()
                return ", ".join(r["name"] or person_name(r["emp_id"] or r["roll_no"], conn) or "" for r in rows)
            row = conn.execute("SELECT f.full_name FROM submission_faculty sf JOIN faculty f ON f.emp_id = sf.emp_id WHERE sf.submission_id = ? LIMIT 1",
                               (submission_id,)).fetchone()
            if row:
                return row[0]
            row = conn.execute("SELECT f.full_name FROM faculty_achievements a JOIN faculty f ON f.emp_id = a.emp_id WHERE a.submission_id = ?",
                               (submission_id,)).fetchone()
            return row[0] if row else ""
