import os
import json
from typing import List, Dict, Any, Optional
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT

from database.db_manager import get_issue, get_sections_and_categories, get_entries, save_generation_record
from backend.services.docx_generator import DOCXGenerator

class NewsletterBuilder:
    def __init__(self, templates_dir: Optional[str] = None, output_dir: Optional[str] = None):
        self.templates_dir = templates_dir or os.path.join(os.path.dirname(__file__), "..", "..", "templates")
        self.output_dir = output_dir or os.path.join(os.path.dirname(__file__), "..", "..", "output")
        self.generator = DOCXGenerator(self.templates_dir)

    def assemble_newsletter(self, issue_id: str, selected_section_ids: Optional[List[str]] = None, selected_entry_ids: Optional[List[str]] = None, output_filename: Optional[str] = None) -> Dict[str, Any]:
        """
        Assembles selected section content and approved entries into a single Master Newsletter DOCX.
        """
        issue = get_issue(issue_id)
        if not issue:
            raise ValueError(f"Issue {issue_id} not found.")

        sections = get_sections_and_categories()
        if selected_section_ids:
            sections = [s for s in sections if s["section_id"] in selected_section_ids and s["enabled"]]

        # Load master template
        master_template_path = os.path.join(self.templates_dir, "default_master_template.docx")
        doc = Document(master_template_path)

        # Replace issue level metadata placeholders
        meta = json.loads(issue.get("metadata_json", "{}")) if isinstance(issue.get("metadata_json"), str) else issue.get("metadata_json", {})
        ed_msg = meta.get("editorial_message", {})

        placeholders_map = {
            "{{issue_volume_issue}}": f"Vol. {issue['volume']} Issue {issue['issue']}",
            "{{issue_academic_year}}": issue["academic_year"],
            "{{issue_semester}}": issue["semester"],
            "{{issue_period}}": issue["publication_period"],
            "{{issue_hod_message}}": ed_msg.get("hod_message", "Welcome to IT Chronicles.")
        }

        for p in doc.paragraphs:
            for key, val in placeholders_map.items():
                if key in p.text:
                    p.text = p.text.replace(key, val)

        for t in doc.tables:
            for row in t.rows:
                for cell in row.cells:
                    for p in cell.paragraphs:
                        for key, val in placeholders_map.items():
                            if key in p.text:
                                p.text = p.text.replace(key, val)

        # Find master content block placeholder
        master_p = None
        for p in doc.paragraphs:
            if "{{MASTER_NEWSLETTER_CONTENT}}" in p.text:
                master_p = p
                p.text = ""
                break

        # Render each selected section
        assembled_entry_ids = []
        for sec in sections:
            # Fetch approved entries for section
            sec_entries = get_entries(issue_id=issue_id, section_id=sec["section_id"], approval_status="Approved")
            
            if selected_entry_ids is not None:
                sec_entries = [e for e in sec_entries if e["entry_id"] in selected_entry_ids]

            if not sec_entries:
                # Omit empty optional section per architectural requirement
                continue

            # Record included entries
            assembled_entry_ids.extend([e["entry_id"] for e in sec_entries])

            # Section Header Title
            p_hdr = doc.add_paragraph()
            p_hdr.paragraph_format.space_before = Pt(20)
            p_hdr.paragraph_format.space_after = Pt(8)
            r_hdr = p_hdr.add_run(sec["name"].upper())
            r_hdr.font.name = "Arial"
            r_hdr.font.size = Pt(18)
            r_hdr.font.bold = True
            r_hdr.font.color.rgb = RGBColor(31, 78, 120)

            # Render Stats & Content
            self.generator._render_stats_card(doc, sec["name"], len(sec_entries), {})
            
            featured = [e for e in sec_entries if e.get("featured_flag")]
            if featured:
                self.generator._render_featured_section(doc, featured)

            cat_map = {c["category_id"]: c for c in sec.get("subcategories", [])}
            entries_by_cat = {}
            for e in sec_entries:
                entries_by_cat.setdefault(e.get("category_id", "uncategorized"), []).append(e)

            for cat_id, cat_info in cat_map.items():
                c_entries = entries_by_cat.get(cat_id, [])
                if not c_entries:
                    continue
                
                p_cat = doc.add_paragraph()
                p_cat.paragraph_format.space_before = Pt(12)
                p_cat.paragraph_format.space_after = Pt(4)
                r_c = p_cat.add_run(f"■  {cat_info['name']}")
                r_c.font.name = "Arial"
                r_c.font.size = Pt(13)
                r_c.font.bold = True
                r_c.font.color.rgb = RGBColor(31, 78, 120)

                self.generator._render_category_table(doc, c_entries)

            doc.add_page_break()

        # Save assembled master DOCX
        fname = output_filename or f"Master_Newsletter_{issue_id}.docx"
        out_docx_path = os.path.join(self.output_dir, fname)
        os.makedirs(self.output_dir, exist_ok=True)
        doc.save(out_docx_path)

        # Audit Record
        gen_id = save_generation_record(
            issue_id=issue_id,
            generation_type="Master",
            section_id=None,
            output_file=out_docx_path,
            fmt="docx",
            entry_ids=assembled_entry_ids
        )

        return {
            "success": True,
            "generation_id": gen_id,
            "master_docx_path": out_docx_path,
            "total_sections_included": len(sections),
            "total_entries_included": len(assembled_entry_ids)
        }
