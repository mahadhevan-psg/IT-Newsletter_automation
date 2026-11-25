"""The newsletter's entries come from the local master database.

Every approved entry lives in the master database (form_submissions and its detail tables). This service keeps the newsletter in step with it:

  new records        become newsletter entries (approved by default: an editor only rejects what should stay out)
  changed records    have their newsletter text refreshed; the editor's own decisions (approved / rejected, featured, order) are kept
  removed records    (approval withdrawn) leave the newsletter

What goes where is decided by the published form definitions: each field's "In the newsletter as" setting (Form builder) names the
newsletter field it fills, and the form or category names the section. People are named from the master records. The newsletter's own
database only holds the editor's decisions and a copy of these fields, so there is nothing to import or map by hand.
"""
import json
from typing import Any, Dict, List, Optional

from backend.master import answers, blocks, ingest
from backend.master.common import norm_header, person_name
from backend.services.normalization_service import NormalizationService
from backend.services.validation_service import ValidationService
from database.db_manager import create_canonical_entry, get_connection, save_raw_response, sync_sections
from database.master_db import db

FORM_FOR_TYPE = {"STUDENT": "form_student", "RESEARCH": "form_research", "FACULTY": "form_faculty",
                 "DEPARTMENT": "form_departmental", "OUTREACH": "form_industry"}
MARK = "_master_submission"                    # in the entry's extra data: the record it comes from
# the newsletter fields a record fills (the editor's own fields - approval, featured, order, note - are never overwritten)
CONTENT = ("section_id", "category_id", "title", "author_or_person", "organization_or_venue", "event_date", "impact_or_indexing", "grant_or_prize_amount",
           "description", "photo_url", "photo_caption", "evidence_url", "badge_tag", "submitter_email")
MAPPED = ("organization_or_venue", "impact_or_indexing", "grant_or_prize_amount", "description", "photo_url", "photo_caption", "evidence_url", "badge_tag", "author_or_person")


class MasterSync:
    def __init__(self, normalizer: Optional[NormalizationService] = None):
        self.normalizer = normalizer or NormalizationService()         # holds the newsletter's category ids for each form category
        self.validator = ValidationService()

    def records(self, ay_id: Optional[str] = None) -> List[Dict[str, Any]]:
        sql = ("SELECT submission_id, form_type, ay_id, event_date, title, category, evidence_url, media_url, submitter_email, submitter_emp_id, "
               "is_landmark, publish_permission, raw_json, newsletter_entry_id FROM form_submissions")
        args: List[Any] = []
        if ay_id:
            sql += " WHERE ay_id = ?"
            args.append(ay_id)
        with db() as conn:
            return [dict(r) for r in conn.execute(sql + " ORDER BY submission_id", args)]

    # ------------------------------------------------------------------------------------------------ record -> newsletter fields
    def fields_of(self, conn, record: Dict[str, Any]) -> Dict[str, Any]:
        form_id = FORM_FOR_TYPE[record["form_type"]]
        spec = ingest.specs()["forms"][form_id]
        raw = json.loads(record["raw_json"] or "{}")
        category = record["category"]
        said = {norm_header(k): str(v).strip() for k, v in raw.items() if v is not None and str(v).strip()}
        mapped: Dict[str, str] = {}
        paragraphs: List[str] = []
        for q in sorted(blocks.questions_for(spec, category, legacy=True), key=lambda q: bool(q.get("legacy"))):     # the current wording wins
            value = next((said[n] for n in (norm_header(t) for t in (q["q"], *q.get("aliases", []))) if n in said), "")
            if not value:
                continue
            if q.get("nl") in MAPPED and q["nl"] not in mapped:
                mapped[q["nl"]] = value
            if q.get("type") == "para" and value not in paragraphs:
                paragraphs.append(value)

        cfg = spec.get("category_config", {}).get(category, {})
        self.normalizer._reload_if_changed()
        studio = self.normalizer.mappings.get(form_id, {})
        entry: Dict[str, Any] = {k: "" for k in CONTENT}
        entry.update({k: v for k, v in mapped.items() if k != "author_or_person"})
        entry.update({
            "section_id": cfg.get("section_id") or spec.get("section_id") or studio.get("section_id") or "sec_research",
            "category_id": studio.get("category_map", {}).get(category, "cat_gen"),
            "title": record["title"] or "Untitled Submission",
            "author_or_person": self._people(conn, record["submission_id"], record["form_type"], record["submitter_emp_id"]) or mapped.get("author_or_person", ""),
            "event_date": record["event_date"] or "",
            "evidence_url": record["evidence_url"] or mapped.get("evidence_url", ""),
            "photo_url": (record["media_url"] or mapped.get("photo_url", "")).split(", ")[0],
            "submitter_email": record["submitter_email"] or "",
        })
        # a category that asks for no description still has something to print: its first long answer
        entry["description"] = entry["description"] or next(iter(paragraphs), "")
        entry["badge_tag"] = entry["badge_tag"] or entry["impact_or_indexing"] or entry["grant_or_prize_amount"]
        extra = {k: str(v).strip() for k, v in raw.items() if str(v or "").strip() and norm_header(k) not in answers.HIDDEN_TITLES}
        extra[MARK] = record["submission_id"]
        entry["extra_fields"] = extra
        return entry

    @staticmethod
    def _people(conn, submission_id: int, form_type: str, submitter: Optional[str]) -> str:
        """The byline, from the master records."""
        names = lambda sql: [r[0] for r in conn.execute(sql, (submission_id,)) if r[0]]
        if form_type == "STUDENT":
            found = [r["full_name"] or r["name"] or person_name(r["roll_no"], conn) or r["roll_no"] or "" for r in conn.execute(
                "SELECT p.roll_no, p.name, s.full_name FROM student_achievement_participants p LEFT JOIN students s ON s.roll_no = p.roll_no WHERE p.submission_id = ? ORDER BY p.line_no", (submission_id,))]
        elif form_type == "RESEARCH":
            found = names("SELECT COALESCE(f.full_name, s.full_name, c.name) FROM research_contributors c LEFT JOIN faculty f ON f.emp_id = c.emp_id "
                          "LEFT JOIN students s ON s.roll_no = c.roll_no WHERE c.submission_id = ? ORDER BY c.author_order")
        elif form_type == "FACULTY":
            found = names("SELECT f.full_name FROM faculty_achievements a JOIN faculty f ON f.emp_id = a.emp_id WHERE a.submission_id = ?")
        else:
            found = names("SELECT f.full_name FROM submission_faculty sf JOIN faculty f ON f.emp_id = sf.emp_id WHERE sf.submission_id = ? ORDER BY sf.role DESC")
        if not found and submitter:
            row = conn.execute("SELECT full_name FROM faculty WHERE emp_id = ?", (submitter,)).fetchone()
            found = [row[0]] if row else []
        return ", ".join(dict.fromkeys(n for n in found if n))

    # ------------------------------------------------------------------------------------------------ keeping in step
    def sync(self, issue_id: str = "ISSUE_2026_V1I1", ay_id: Optional[str] = None) -> Dict[str, Any]:
        """Bring the newsletter in step with the master database. A record whose author answered "No" to a publish-permission question
        (older entries) stays out."""
        sync_sections()
        created = updated = removed = skipped = 0
        failed: List[Dict[str, Any]] = []
        newsletter = get_connection()
        try:
            have = {r["entry_id"]: dict(r) for r in newsletter.execute("SELECT * FROM canonical_entries")}
        finally:
            newsletter.close()
        records = self.records(ay_id)
        changes: List[tuple] = []
        links: List[tuple] = []
        with db() as conn:                                       # one connection for reading every record
            for record in records:
                if record["publish_permission"] == 0:
                    skipped += 1
                    continue
                try:
                    entry = self.fields_of(conn, record)
                    current = have.get(record["newsletter_entry_id"]) if record["newsletter_entry_id"] else None
                    if current is None:
                        links.append((self._create(entry, record, issue_id), record["submission_id"]))
                        created += 1
                        continue
                    extra = json.dumps(entry["extra_fields"], ensure_ascii=False)
                    if any((current.get(k) or "") != (entry[k] or "") for k in CONTENT) or json.loads(current.get("extra_data_json") or "{}") != json.loads(extra):
                        changes.append((*(entry[k] for k in CONTENT), extra, current["entry_id"]))
                        updated += 1
                except Exception as e:                          # one bad record never blocks the rest
                    failed.append({"submission_id": record["submission_id"], "error": str(e)})
            if links:
                conn.executemany("UPDATE form_submissions SET newsletter_entry_id = ? WHERE submission_id = ?", links)
        everything = None if ay_id else {r["submission_id"]: r for r in self.records()}
        removed = self._apply(changes, everything or None, issue_id)          # an empty master database (wrong path, new volume) removes nothing
        return {"success": True, "created": created, "updated": updated, "removed": removed, "skipped_no_permission": skipped, "failed": failed,
                "submissions_in_master": len(records)}

    @staticmethod
    def _apply(changes: List[tuple], records: Optional[Dict[int, Dict[str, Any]]], issue_id: str) -> int:
        """Write the refreshed entries; drop the entries whose record is gone from the master database (only when looking at all of it)."""
        conn = get_connection()
        removed = 0
        try:
            if changes:
                sets = ", ".join(f"{k} = ?" for k in (*CONTENT, "extra_data_json"))
                conn.executemany(f"UPDATE canonical_entries SET {sets} WHERE entry_id = ?", changes)
            if records is not None:
                linked = {r["newsletter_entry_id"] for r in records.values() if r["newsletter_entry_id"]}
                for row in conn.execute("SELECT entry_id, extra_data_json FROM canonical_entries WHERE issue_id = ?", (issue_id,)).fetchall():
                    try:
                        came_from_master = MARK in json.loads(row["extra_data_json"] or "{}")
                    except ValueError:
                        came_from_master = False
                    if came_from_master and row["entry_id"] not in linked:
                        conn.execute("DELETE FROM canonical_entries WHERE entry_id = ?", (row["entry_id"],))
                        removed += 1
            conn.commit()
        finally:
            conn.close()
        return removed

    def _create(self, entry: Dict[str, Any], record: Dict[str, Any], issue_id: str) -> str:
        form_id = FORM_FOR_TYPE[record["form_type"]]
        data = {**entry, "issue_id": issue_id, "approval_status": "Approved", "featured_flag": bool(record.get("is_landmark")), "display_order": 100}
        data["response_id"] = save_raw_response(form_id, issue_id, entry["submitter_email"], json.loads(record["raw_json"] or "{}"))
        problems = self.validator.validate_entry(data)
        if problems:
            data["rejection_reason"] = f"Validation warnings: {'; '.join(problems)}"
        return create_canonical_entry(data)
