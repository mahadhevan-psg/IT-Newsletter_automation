import os
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn

TEMPLATES_DIR = os.path.dirname(__file__)

def set_cell_background(cell, fill_hex):
    tcPr = cell._element.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>')
    tcPr.append(shd)

def create_section_template(filename: str, title: str, accent_hex: str = "1F4E78"):
    doc = Document()
    
    # Page Margins
    sections = doc.sections
    for s in sections:
        s.top_margin = Inches(0.8)
        s.bottom_margin = Inches(0.8)
        s.left_margin = Inches(0.8)
        s.right_margin = Inches(0.8)

    # Section Header Title
    header_table = doc.add_table(rows=1, cols=1)
    header_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = header_table.rows[0].cells[0]
    set_cell_background(cell, accent_hex)
    cell.width = Inches(6.8)
    
    p = cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run = p.add_run(f"  {title.upper()}  ")
    run.font.name = "Arial"
    run.font.size = Pt(20)
    run.font.bold = True
    run.font.color.rgb = RGBColor(255, 255, 255)
    
    doc.add_paragraph().paragraph_format.space_after = Pt(12)

    # Placeholders Marker
    p_placeholders = doc.add_paragraph()
    r_ph = p_placeholders.add_run("{{SECTION_CONTENT_BLOCK}}")
    r_ph.font.name = "Arial"
    r_ph.font.size = Pt(10)
    r_ph.font.color.rgb = RGBColor(128, 128, 128)

    out_path = os.path.join(TEMPLATES_DIR, filename)
    doc.save(out_path)
    print(f"Created template: {out_path}")

def create_master_template():
    doc = Document()
    for s in doc.sections:
        s.top_margin = Inches(0.8)
        s.bottom_margin = Inches(0.8)
        s.left_margin = Inches(0.8)
        s.right_margin = Inches(0.8)

    # Cover Page
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_title.paragraph_format.space_before = Pt(72)
    run_t = p_title.add_run("IT CHRONICLES")
    run_t.font.name = "Arial"
    run_t.font.size = Pt(36)
    run_t.font.bold = True
    run_t.font.color.rgb = RGBColor(31, 78, 120)

    p_sub = doc.add_paragraph()
    p_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_s = p_sub.add_run("Department of Information Technology Newsletter")
    run_s.font.name = "Arial"
    run_s.font.size = Pt(16)
    run_s.font.italic = True
    run_s.font.color.rgb = RGBColor(89, 89, 89)

    doc.add_paragraph().paragraph_format.space_after = Pt(36)

    # Issue Info Table
    info_table = doc.add_table(rows=2, cols=2)
    info_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    info_table.rows[0].cells[0].paragraphs[0].add_run("Volume & Issue: {{issue_volume_issue}}").bold = True
    info_table.rows[0].cells[1].paragraphs[0].add_run("Academic Year: {{issue_academic_year}}").bold = True
    info_table.rows[1].cells[0].paragraphs[0].add_run("Semester: {{issue_semester}}").bold = True
    info_table.rows[1].cells[1].paragraphs[0].add_run("Publication Period: {{issue_period}}").bold = True

    doc.add_page_break()

    # Editorial Section
    p_ed = doc.add_paragraph()
    r_ed = p_ed.add_run("EDITORIAL & MESSAGES")
    r_ed.font.name = "Arial"
    r_ed.font.size = Pt(18)
    r_ed.font.bold = True
    r_ed.font.color.rgb = RGBColor(31, 78, 120)

    p_hod = doc.add_paragraph()
    p_hod.add_run("HOD Message: ").bold = True
    p_hod.add_run("{{issue_hod_message}}")

    doc.add_paragraph().paragraph_format.space_after = Pt(18)

    # Master Content Block
    doc.add_paragraph("{{MASTER_NEWSLETTER_CONTENT}}")

    out_path = os.path.join(TEMPLATES_DIR, "default_master_template.docx")
    doc.save(out_path)
    print(f"Created Master template: {out_path}")

if __name__ == "__main__":
    create_section_template("research_section_template.docx", "Research & Innovation", "1F4E78")
    create_section_template("faculty_section_template.docx", "Faculty Achievements", "2E75B6")
    create_section_template("student_section_template.docx", "Student Achievements", "548235")
    create_section_template("industry_section_template.docx", "Industry & Alumni Outreach", "C65911")
    create_section_template("departmental_section_template.docx", "Departmental Highlights", "70AD47")
    create_master_template()
