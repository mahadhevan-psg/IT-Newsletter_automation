import os
from typing import List, Dict, Any, Optional
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls

class DOCXGenerator:
    def __init__(self, templates_dir: Optional[str] = None):
        self.templates_dir = templates_dir or os.path.join(os.path.dirname(__file__), "..", "..", "templates")

    def _set_cell_bg(self, cell, fill_hex: str):
        tcPr = cell._element.get_or_add_tcPr()
        shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>')
        tcPr.append(shd)

    def generate_section_docx(self, section: Dict[str, Any], subcategories: List[Dict[str, Any]], approved_entries: List[Dict[str, Any]], output_path: str) -> str:
        """
        Generates a section DOCX document populated with approved structured entries.
        """
        template_file = section.get("template_file") or os.path.join(self.templates_dir, f"{section['section_id']}_template.docx")
        if not os.path.exists(template_file):
            template_file = os.path.join(self.templates_dir, "research_section_template.docx")

        doc = Document(template_file)

        # Replace {{SECTION_CONTENT_BLOCK}} paragraph or append at end
        target_p = None
        for p in doc.paragraphs:
            if "{{SECTION_CONTENT_BLOCK}}" in p.text:
                target_p = p
                p.text = "" # Clear placeholder text
                break

        # Group entries by category
        cat_map = {c["category_id"]: c for c in subcategories}
        entries_by_cat: Dict[str, List[dict]] = {}
        for entry in approved_entries:
            cid = entry.get("category_id", "uncategorized")
            entries_by_cat.setdefault(cid, []).append(entry)

        # 1. Render Statistics Summary Component at top if entries exist
        if approved_entries:
            self._render_stats_card(doc, section["name"], len(approved_entries), entries_by_cat)

        # 2. Render Featured / Spotlight Cards first
        featured_entries = [e for e in approved_entries if e.get("featured_flag")]
        if featured_entries:
            self._render_featured_section(doc, featured_entries)

        # 3. Render Entries grouped by Subcategory
        for cat_id, cat_info in cat_map.items():
            cat_entries = entries_by_cat.get(cat_id, [])
            if not cat_entries:
                continue

            # Subcategory Heading
            p_cat = doc.add_paragraph()
            p_cat.paragraph_format.space_before = Pt(14)
            p_cat.paragraph_format.space_after = Pt(6)
            run_cat = p_cat.add_run(f"■  {cat_info['name']}")
            run_cat.font.name = "Arial"
            run_cat.font.size = Pt(14)
            run_cat.font.bold = True
            run_cat.font.color.rgb = RGBColor(31, 78, 120)

            # Render Entries Table or List
            self._render_category_table(doc, cat_entries)

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        doc.save(output_path)
        return output_path

    def _render_stats_card(self, doc: Document, section_name: str, total_entries: int, entries_by_cat: Dict[str, List[dict]]):
        table = doc.add_table(rows=1, cols=3)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        
        c0 = table.rows[0].cells[0]
        c1 = table.rows[0].cells[1]
        c2 = table.rows[0].cells[2]

        self._set_cell_bg(c0, "F2F4F7")
        self._set_cell_bg(c1, "EBF3F9")
        self._set_cell_bg(c2, "F2F4F7")

        p0 = c0.paragraphs[0]
        p0.add_run("Total Submissions").font.size = Pt(9)
        p0_val = c0.add_paragraph()
        r0 = p0_val.add_run(str(total_entries))
        r0.font.size = Pt(18)
        r0.font.bold = True
        r0.font.color.rgb = RGBColor(31, 78, 120)

        p1 = c1.paragraphs[0]
        p1.add_run("Active Categories").font.size = Pt(9)
        p1_val = c1.add_paragraph()
        r1 = p1_val.add_run(str(len(entries_by_cat)))
        r1.font.size = Pt(18)
        r1.font.bold = True
        r1.font.color.rgb = RGBColor(46, 117, 182)

        p2 = c2.paragraphs[0]
        p2.add_run("Section Status").font.size = Pt(9)
        p2_val = c2.add_paragraph()
        r2 = p2_val.add_run("VERIFIED")
        r2.font.size = Pt(14)
        r2.font.bold = True
        r2.font.color.rgb = RGBColor(84, 130, 53)

        doc.add_paragraph().paragraph_format.space_after = Pt(10)

    def _render_featured_section(self, doc: Document, featured_entries: List[dict]):
        p_feat_hdr = doc.add_paragraph()
        p_feat_hdr.paragraph_format.space_before = Pt(12)
        r_f = p_feat_hdr.add_run("★  SPOTLIGHT & FEATURED HIGHLIGHTS")
        r_f.font.name = "Arial"
        r_f.font.size = Pt(13)
        r_f.font.bold = True
        r_f.font.color.rgb = RGBColor(198, 89, 17)

        for entry in featured_entries:
            table = doc.add_table(rows=1, cols=1)
            table.alignment = WD_TABLE_ALIGNMENT.CENTER
            cell = table.rows[0].cells[0]
            self._set_cell_bg(cell, "FFF8F0")

            p_t = cell.paragraphs[0]
            r_title = p_t.add_run(entry.get("title", ""))
            r_title.font.name = "Arial"
            r_title.font.size = Pt(12)
            r_title.font.bold = True
            r_title.font.color.rgb = RGBColor(198, 89, 17)

            p_meta = cell.add_paragraph()
            p_meta.add_run(f"By: {entry.get('author_or_person', 'N/A')}  |  Date: {entry.get('event_date', 'N/A')}").font.size = Pt(9.5)
            if entry.get("organization_or_venue"):
                p_meta.add_run(f"  |  Venue: {entry.get('organization_or_venue')}").font.size = Pt(9.5)

            p_desc = cell.add_paragraph()
            p_desc.add_run(entry.get("description", "")).font.size = Pt(10)

            if entry.get("photo_url"):
                p_p = cell.add_paragraph()
                r_p = p_p.add_run(f"Photo Attachment: {entry.get('photo_url')}")
                r_p.font.size = Pt(9)
                r_p.font.italic = True
                r_p.font.color.rgb = RGBColor(31, 78, 120)

            doc.add_paragraph().paragraph_format.space_after = Pt(8)

    def _render_category_table(self, doc: Document, entries: List[dict]):
        table = doc.add_table(rows=1, cols=4)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        
        hdr_cells = table.rows[0].cells
        hdr_titles = ["Date", "Title & Contributor", "Venue / Organization / Grant", "Details & Impact"]
        widths = [Inches(0.9), Inches(2.2), Inches(1.8), Inches(2.1)]
        
        for i, title in enumerate(hdr_titles):
            cell = hdr_cells[i]
            cell.width = widths[i]
            self._set_cell_bg(cell, "1F4E78")
            p = cell.paragraphs[0]
            r = p.add_run(title)
            r.font.name = "Arial"
            r.font.size = Pt(9.5)
            r.font.bold = True
            r.font.color.rgb = RGBColor(255, 255, 255)

        for row_idx, entry in enumerate(entries):
            row_cells = table.add_row().cells
            bg = "F9FAFB" if row_idx % 2 == 1 else "FFFFFF"
            for c in row_cells:
                self._set_cell_bg(c, bg)

            # Cell 0: Date
            row_cells[0].paragraphs[0].add_run(entry.get("event_date", "")).font.size = Pt(9)

            # Cell 1: Title & Authors
            p1 = row_cells[1].paragraphs[0]
            r_t = p1.add_run(entry.get("title", ""))
            r_t.font.bold = True
            r_t.font.size = Pt(9.5)
            p1_sub = row_cells[1].add_paragraph()
            p1_sub.add_run(f"By: {entry.get('author_or_person', '')}").font.size = Pt(8.5)

            # Cell 2: Venue / Grant / Impact
            p2 = row_cells[2].paragraphs[0]
            if entry.get("organization_or_venue"):
                p2.add_run(entry.get("organization_or_venue")).font.size = Pt(9)
            if entry.get("grant_or_prize_amount"):
                p2_g = row_cells[2].add_paragraph()
                p2_g.add_run(f"Value: {entry.get('grant_or_prize_amount')}").font.size = Pt(8.5)
            if entry.get("impact_or_indexing"):
                p2_i = row_cells[2].add_paragraph()
                p2_i.add_run(f"Impact: {entry.get('impact_or_indexing')}").font.size = Pt(8.5)

            # Cell 3: Details & Links
            p3 = row_cells[3].paragraphs[0]
            p3.add_run(entry.get("description", "")[:150] + ("..." if len(entry.get("description", "")) > 150 else "")).font.size = Pt(9)
            if entry.get("evidence_url"):
                p3_l = row_cells[3].add_paragraph()
                p3_l.add_run(f"Link: {entry.get('evidence_url')}").font.size = Pt(8.5)

        doc.add_paragraph().paragraph_format.space_after = Pt(12)
