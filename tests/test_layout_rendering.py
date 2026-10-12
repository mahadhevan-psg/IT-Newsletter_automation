import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from docx import Document
from backend.services.docx_generator import DOCXGenerator, dedupe_entries

ENTRY = {
    "entry_id": "E1", "category_id": "cat_x", "featured_flag": 0,
    "title": "Quantum Widgets", "author_or_person": "A. Author", "organization_or_venue": "Journal of Widgets",
    "event_date": "May 2026", "description": "Body text here.", "badge_tag": "Scopus Q1",
    "evidence_url": "https://example.org/paper", "photo_url": "", "photo_caption": "",
}


class LayoutRenderingTest(unittest.TestCase):
    def render(self, layout, entries=None):
        path = os.path.join(tempfile.mkdtemp(), "out.docx")
        DOCXGenerator().generate_section_docx({"section_id": "s", "name": "Research"}, [], entries or [ENTRY], path, layout=layout)
        return Document(path)

    def test_blocks_appear_in_layout_order_and_nothing_else(self):
        layout = [
            {"type": "text", "tag": "description", "style": {}},
            {"type": "headline", "tag": "title", "style": {}},
        ]
        texts = [p.text for p in self.render(layout).paragraphs if p.text.strip()]
        self.assertEqual(texts[1:], ["Body text here.", "Quantum Widgets"])   # [0] is the page header
        self.assertEqual(self.render(layout).tables, [])

    def test_unselected_fields_are_not_printed(self):
        layout = [{"type": "headline", "tag": "title", "style": {}}]
        text = "\n".join(p.text for p in self.render(layout).paragraphs)
        self.assertNotIn("A. Author", text)
        self.assertNotIn("Body text here.", text)
        self.assertNotIn("SPOTLIGHT", text)

    def test_style_from_layout_is_applied(self):
        layout = [{"type": "headline", "tag": "title", "style": {"fontSize": "2rem", "textColor": "#c65911", "textAlign": "center"}}]
        p = next(p for p in self.render(layout).paragraphs if p.text == "Quantum Widgets")
        self.assertEqual(p.runs[0].font.size.pt, 24)
        self.assertEqual(str(p.runs[0].font.color.rgb), "C65911")
        self.assertEqual(p.alignment, 1)

    def test_button_is_a_real_hyperlink_with_layout_text(self):
        layout = [{"type": "link", "tag": "evidence_url", "linkText": "Read the paper", "style": {"buttonStyle": "accent"}}]
        doc = self.render(layout)
        self.assertIn("Read the paper", doc.element.xml)
        self.assertIn("<w:hyperlink", doc.element.xml)

    def test_duplicates_collapse(self):
        self.assertEqual(len(dedupe_entries([ENTRY, dict(ENTRY, entry_id="E2")])), 1)


if __name__ == "__main__":
    unittest.main()
