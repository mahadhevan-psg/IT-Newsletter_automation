import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from docx import Document
from PIL import Image
from backend.services.docx_generator import DOCXGenerator
from backend.services.front_matter_service import FrontMatterService, default_front_matter

NS_WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
TMP = tempfile.mkdtemp()


BLIP = "{http://schemas.openxmlformats.org/drawingml/2006/main}blip"


def photo(name, size=(800, 600), color=(40, 90, 160)):
    path = os.path.join(TMP, name)
    Image.new("RGB", size, color).save(path)
    return path


def entry(n, with_photo=True):
    return {"entry_id": f"E{n}", "category_id": "c", "featured_flag": 0, "title": f"Story {n}", "author_or_person": "A. Author",
            "organization_or_venue": "Venue", "event_date": "May 2026", "description": f"Body of story {n}. " * 20,
            "badge_tag": "", "evidence_url": "https://example.org", "photo_url": photo(f"p{n}.jpg") if with_photo else "",
            "photo_caption": "A caption" if with_photo else "", "display_order": n}


def front():
    fm = default_front_matter()
    fm["hod"] = {"name": "Dr. Head", "designation": "Head of the Department", "message": "First para.\nSecond para.", "photo": photo("hod.jpg", (600, 800))}
    fm["vision"] = ["v1", "v2", "v3", "v4", "v5"]
    fm["mission"] = ["m1", "m2", "m3", "m4", "m5"]
    fm["advisor"] = {"name": "Prof. Advisor", "designation": "Faculty Advisor", "photo": photo("adv.jpg")}
    fm["students"] = [{"name": f"Student {i}", "year": "III Year", "photo": photo(f"s{i}.jpg") if i != 3 else ""} for i in range(1, 5)]
    return fm


def anchors(doc):
    return doc.element.body.findall(f".//{NS_WP}anchor")


class FrontPagesTest(unittest.TestCase):
    def build(self, fn):
        doc = DOCXGenerator().new_document()
        fn(doc)
        path = os.path.join(TMP, "out.docx")
        doc.save(path)
        return Document(path)

    def test_cover_page_has_one_large_image_then_hod_desk_with_photo_left_and_message_right(self):
        fm = front()
        fm["cover"] = {"photo": photo("cover.jpg", (900, 1200))}
        doc = self.build(lambda d: DOCXGenerator().add_front_page(d, fm, {"volume": 1, "issue": 1}))
        self.assertEqual(len(anchors(doc)), 0)                         # nothing floats: photo and message sit in side-by-side cells
        body = doc.element.body
        before_table = []
        for el in body:
            if el.tag.endswith("}tbl"):
                break
            before_table.append(el)
        pics_before = sum(len(e.findall(f".//{BLIP}")) for e in before_table)
        self.assertEqual(pics_before, 1)                               # the cover image; the HOD photo is inside the table
        heading = next(p for p in doc.paragraphs if p.text == "THE HOD'S DESK")
        self.assertTrue(heading.paragraph_format.page_break_before)    # the HOD's Desk starts on its own page
        hod = doc.tables[0]
        self.assertEqual(len(hod.columns), 2)
        left, right = hod.cell(0, 0), hod.cell(0, 1)
        self.assertEqual(len(left._tc.findall(f".//{BLIP}")), 1)
        self.assertIn("Dr. Head", left.text)                           # name beneath the photo
        self.assertIn("First para.", right.text)                       # message to its right
        self.assertEqual(len(doc.tables[1].columns), 3)                # vision panel, a gap, mission panel
        self.assertEqual([p.text for p in doc.tables[1].cell(0, 0).paragraphs][:1], ["Vision"])
        self.assertEqual(sum(1 for p in doc.tables[1].cell(0, 2).paragraphs if p.style.name == "List Bullet"), 5)

    def test_without_cover_image_the_nameplate_heads_the_hod_page(self):
        doc = self.build(lambda d: DOCXGenerator().add_front_page(d, front(), {"volume": 1, "issue": 1}))
        heading = next(p for p in doc.paragraphs if p.text == "THE HOD'S DESK")
        self.assertFalse(heading.paragraph_format.page_break_before)

    def test_hod_without_photo_gets_full_width_message_and_signature(self):
        fm = front()
        fm["hod"]["photo"] = ""
        doc = self.build(lambda d: DOCXGenerator().add_front_page(d, fm, {"volume": 1, "issue": 1}))
        self.assertEqual(len(doc.tables), 1)                           # only the vision / mission panels
        self.assertTrue(any(p.text == "Dr. Head\nHead of the Department" for p in doc.paragraphs))

    def test_editorial_page_centres_advisor_and_lists_students_in_one_row(self):
        doc = self.build(lambda d: DOCXGenerator().add_editorial_page(d, front()))
        row = doc.tables[0].rows[0]
        self.assertEqual(len(row.cells), 4)
        text = [c.text for c in row.cells]
        self.assertIn("Student 1\nIII Year", text[0])
        self.assertEqual(len(row.cells[2]._tc.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}blip")), 0)  # no photo, no space
        self.assertEqual(len(row.cells[0]._tc.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}blip")), 1)

    def test_empty_front_matter_prints_nothing_extra(self):
        doc = self.build(lambda d: DOCXGenerator().add_editorial_page(d, default_front_matter()))
        self.assertEqual(len(doc.tables), 0)

    def test_alternating_layout_starts_left_then_right_and_skips_missing_photos(self):
        entries = [entry(1), entry(2), entry(3, with_photo=False), entry(4)]
        doc = self.build(lambda d: DOCXGenerator().add_section(d, {"name": "S"}, [], entries, mode="alternating"))
        sides = [a.find(f"{NS_WP}positionH/{NS_WP}align").text for a in anchors(doc)]
        self.assertEqual(sides, ["left", "right", "left"])        # the photo-less story does not consume a turn

    def test_each_section_restarts_on_the_left(self):
        def build(d):
            g = DOCXGenerator()
            g.add_section(d, {"name": "A"}, [], [entry(1)], mode="alternating")
            g.add_section(d, {"name": "B"}, [], [entry(2)], mode="alternating", page_break_before=True)
        doc = self.build(build)
        self.assertEqual([a.find(f"{NS_WP}positionH/{NS_WP}align").text for a in anchors(doc)], ["left", "left"])

    def test_centered_layout_puts_image_first_and_no_floats(self):
        doc = self.build(lambda d: DOCXGenerator().add_section(d, {"name": "S"}, [], [entry(1)], mode="centered"))
        self.assertEqual(len(anchors(doc)), 0)
        body = [p for p in doc.paragraphs if p.text.strip() or p._p.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}blip")]
        self.assertTrue(body[1]._p.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}blip"))   # after the masthead
        self.assertEqual(body[1].alignment, 1)                                                                   # centred
        self.assertEqual(body[2].text.strip(), "A caption")

    def test_no_photo_means_text_only_in_both_layouts(self):
        for mode in ("centered", "alternating"):
            doc = self.build(lambda d: DOCXGenerator().add_section(d, {"name": "S"}, [], [entry(1, with_photo=False)], mode=mode))
            self.assertEqual(len(doc.inline_shapes), 0)
            self.assertEqual(len(anchors(doc)), 0)

    def test_entries_are_kept_whole_and_rule_stays_with_the_entry_above(self):
        for mode in ("centered", "alternating"):
            doc = self.build(lambda d: DOCXGenerator().add_section(d, {"name": "S"}, [], [entry(1), entry(2)], mode=mode))
            paras = doc.paragraphs
            rule = next(i for i, p in enumerate(paras) if p.text == "" and p._p.pPr is not None and p._p.pPr.find(
                "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}pBdr") is not None)
            self.assertTrue(paras[rule - 1].paragraph_format.keep_with_next, mode)       # entry above is tied to its rule
            self.assertFalse(paras[rule].paragraph_format.keep_with_next, mode)          # ...and the chain ends there
            first = rule + 1
            self.assertTrue(paras[first].paragraph_format.keep_with_next, mode)          # the next entry's photo stays with its text

    def test_wrapped_photo_is_sized_to_its_text(self):
        short, long_ = entry(1), entry(2)
        short["description"] = "Short."
        long_["description"] = "word " * 600
        def height(e):
            doc = self.build(lambda d: DOCXGenerator().add_section(d, {"name": "S"}, [], [e], mode="alternating"))
            ext = anchors(doc)[0].find(f"{NS_WP}extent")
            return int(ext.get("cx")) / 914400, int(ext.get("cy")) / 914400
        (sw, sh), (lw, lh) = height(short), height(long_)
        self.assertAlmostEqual(sh, 1.4, delta=0.05)           # short text: the smallest photo, no empty space beside it
        self.assertAlmostEqual(lh, 3.0, delta=0.05)           # long text: the tallest, the rest runs full width beneath
        self.assertLess(sw, lw)

    def test_centered_caption_is_centred_with_its_photo(self):
        doc = self.build(lambda d: DOCXGenerator().add_section(d, {"name": "S"}, [], [entry(1)], mode="centered"))
        cap = next(p for p in doc.paragraphs if p.text.strip() == "A caption")
        self.assertEqual(cap.alignment, 1)

    def test_first_photo_of_a_section_starts_below_the_masthead(self):
        doc = self.build(lambda d: DOCXGenerator().add_section(d, {"name": "S"}, [], [entry(1), entry(2)], mode="alternating"))
        offsets = [int(a.find(f"{NS_WP}positionV/{NS_WP}posOffset").text) for a in anchors(doc)]
        self.assertGreater(offsets[0], 0)
        self.assertEqual(offsets[1], 0)

    def test_centered_layout_keeps_title_and_author_left_aligned(self):
        doc = self.build(lambda d: DOCXGenerator().add_section(d, {"name": "S"}, [], [entry(1)], mode="centered"))
        for text in ("Story 1", "By A. Author"):
            p = next(p for p in doc.paragraphs if p.text == text)
            self.assertIn(p.alignment, (None, 0), text)

    def test_front_page_reports_whether_it_added_anything_beyond_the_cover(self):
        g = DOCXGenerator()
        self.assertFalse(g.add_front_page(g.new_document(), default_front_matter(), {"volume": 1, "issue": 1}))
        self.assertTrue(g.add_front_page(g.new_document(), front(), {"volume": 1, "issue": 1}))
        fm = default_front_matter()
        fm["cover"] = {"photo": photo("cover2.jpg")}
        self.assertTrue(g.add_front_page(g.new_document(), fm, {"volume": 1, "issue": 1}))

    def test_front_matter_save_normalises_shape(self):
        from backend.services import front_matter_service as m
        out = m._clean({"vision": ["a"] * 9, "students": [{"name": " X "}] * 7})
        self.assertEqual(len(out["vision"]), 5)
        self.assertEqual(len(out["students"]), 4)
        self.assertEqual(out["students"][0]["name"], "X")
        self.assertEqual(out["hod"]["designation"], "Head of the Department")


if __name__ == "__main__":
    unittest.main()


def test_a_single_section_can_be_generated_in_every_layout_mode(tmp_path):
    """generate_section_docx is what the Studio's "Download section" calls; it must accept the fixed layouts."""
    for mode in (None, "centered", "alternating"):
        path = DOCXGenerator().generate_section_docx({"section_id": "s", "name": "S"}, [], [entry(1), entry(2, with_photo=False)],
                                                     str(tmp_path / f"{mode}.docx"), mode=mode)
        doc = Document(path)
        texts = [p.text for p in doc.paragraphs] + [c.text for t in doc.tables for r in t.rows for c in r.cells]
        assert any("Story 1" in t for t in texts) and any("Story 2" in t for t in texts), mode
