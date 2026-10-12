import os
from typing import List, Dict, Any, Optional

from database.db_manager import get_issue, get_sections_and_categories, get_entries, save_generation_record
from backend.services.docx_generator import DOCXGenerator, dedupe_entries
from backend.services.config_service import ConfigService


class NewsletterBuilder:
    """Master newsletter = a small cover, then each chosen section rendered from its layout."""

    def __init__(self, templates_dir: Optional[str] = None, output_dir: Optional[str] = None):
        self.output_dir = output_dir or os.path.join(os.path.dirname(__file__), "..", "..", "output")
        self.generator = DOCXGenerator()
        self.config = ConfigService()

    def assemble_newsletter(self, issue_id: str, selected_section_ids: Optional[List[str]] = None,
                            selected_entry_ids: Optional[List[str]] = None,
                            output_filename: Optional[str] = None) -> Dict[str, Any]:
        issue = get_issue(issue_id)
        if not issue:
            raise ValueError(f"Issue {issue_id} not found.")

        sections = get_sections_and_categories()
        if selected_section_ids:
            sections = [s for s in sections if s["section_id"] in selected_section_ids and s["enabled"]]

        doc = self.generator.new_document()
        self.generator.add_cover(doc, issue)

        assembled_entry_ids: List[str] = []
        layouts_used: Dict[str, Optional[str]] = {}
        included_sections = 0
        for sec in sections:
            entries = get_entries(issue_id=issue_id, section_id=sec["section_id"], approval_status="Approved")
            if selected_entry_ids is not None:
                entries = [e for e in entries if e["entry_id"] in selected_entry_ids]
            entries = dedupe_entries(entries)
            if not entries:
                continue   # a section with nothing approved is simply left out

            active = self.config.get_active_layout(sec["section_id"])
            layouts_used[sec["section_id"]] = active["name"] if active else None
            self.generator.add_section(doc, sec, sec.get("subcategories", []), entries,
                                       layout=active["layout"] if active else None, issue=issue,
                                       page_break_before=included_sections > 0)
            assembled_entry_ids.extend(e["entry_id"] for e in entries)
            included_sections += 1

        fname = output_filename or f"Master_Newsletter_{issue_id}.docx"
        out_path = os.path.join(self.output_dir, fname)
        os.makedirs(self.output_dir, exist_ok=True)
        doc.save(out_path)

        gen_id = save_generation_record(
            issue_id=issue_id, generation_type="Master", section_id=None,
            output_file=out_path, fmt="docx", entry_ids=assembled_entry_ids
        )
        return {
            "success": True,
            "generation_id": gen_id,
            "master_docx_path": out_path,
            "total_sections_included": included_sections,
            "total_entries_included": len(assembled_entry_ids),
            "layouts_used": layouts_used
        }
