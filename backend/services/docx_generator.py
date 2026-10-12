"""
Word output, driven entirely by the layout chosen in the Layout designer.

There is no built-in design here: no cover template, stats card, banners or card styling.
Each entry is written block by block exactly as the layout lists them, with the same
sizes, colours, alignment, photo shapes and button styles the designer canvas shows.
Page width matches the canvas paper (A4, 1" side margins = ~600px content width).
"""
import os
import re
import hashlib
import urllib.request
from typing import List, Dict, Any, Optional

from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import parse_xml, OxmlElement
from docx.oxml.ns import nsdecls, qn
from PIL import Image

# ---------------------------------------------------------------- palette (same values as the designer's CSS)
NAVY, AMBER, SLATE, GREEN = "1F4E78", "C65911", "5A6B7C", "15803D"
BODY, BYLINE, META, CAPTION = "334155", "475569", "64748B", "64748B"
RULE, CAPTION_BG, STAT_BG = "D9DEE4", "F8FAFC", "F8FAFC"
BADGE_FILL = {"navy": NAVY, "amber": AMBER, "slate": SLATE, "green": GREEN}
BUTTON_FILL = {"solid": NAVY, "accent": AMBER}
ASPECT = {"16:9": 16 / 9, "4:3": 4 / 3, "1:1": 1.0}

CONTENT_WIDTH_IN = 8.27 - 2.0          # A4 minus 1" margins, about 600 css px
FLOAT_IMAGE_IN = 220 / 96              # "beside text" photo width in the designer (220px)
FONT = "Calibri"

# The layout used when a section has not been given one (mirrors the designer's starting layout)
DEFAULT_LAYOUT: List[Dict[str, Any]] = [
    {"type": "badge", "tag": "badge_tag", "style": {"badgeColor": "navy"}},
    {"type": "headline", "tag": "title", "style": {"textAlign": "left"}},
    {"type": "byline", "tag": "author_or_person", "style": {}},
    {"type": "image", "tag": "photo_url", "captionTag": "photo_caption", "style": {"aspectRatio": "16:9", "float": "none"}},
    {"type": "text", "tag": "description", "style": {"textAlign": "left"}},
    {"type": "link", "tag": "evidence_url", "linkText": "View details", "style": {"buttonStyle": "solid"}},
]


# ---------------------------------------------------------------- helpers
def dedupe_entries(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Collapse identical submissions so one story never prints twice (a featured copy wins)."""
    norm = lambda v: " ".join(str(v or "").lower().split())
    seen: Dict[Any, Dict[str, Any]] = {}
    order: List[Any] = []
    for e in entries:
        key = (norm(e.get("title")), norm(e.get("author_or_person")), norm(e.get("event_date")), norm(e.get("category_id")))
        if key not in seen:
            seen[key] = e
            order.append(key)
        elif e.get("featured_flag") and not seen[key].get("featured_flag"):
            seen[key] = e
    return [seen[k] for k in order]


# Preset layouts describe headline / byline / venue as generic "text" blocks bound to a field
_TEXT_ROLE_BY_TAG = {"title": "headline", "author_or_person": "byline", "organization_or_venue": "meta"}


def normalize_layout(layout: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    out = []
    for b in layout or DEFAULT_LAYOUT:
        b = dict(b)
        if b.get("type") == "text" and b.get("tag") in _TEXT_ROLE_BY_TAG:
            b["type"] = _TEXT_ROLE_BY_TAG[b["tag"]]
        out.append(b)
    return out


def order_entries(entries: List[Dict[str, Any]], subcategories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Featured first, then by sub-section order, then the editor's display order."""
    cat_rank = {c["category_id"]: i for i, c in enumerate(subcategories or [])}
    return sorted(entries, key=lambda e: (0 if e.get("featured_flag") else 1,
                                          cat_rank.get(e.get("category_id"), 999),
                                          e.get("display_order") or 100))


def _hex(color: Any, default: Optional[str] = None) -> Optional[str]:
    m = re.fullmatch(r"#?([0-9a-fA-F]{6})", str(color or "").strip())
    return m.group(1).upper() if m else default


def _pt(size: Any, default: float) -> float:
    """CSS size ('1.45rem', '14px', '11pt') to points. 1rem = 16px = 12pt."""
    m = re.fullmatch(r"\s*([\d.]+)\s*(rem|em|px|pt)?\s*", str(size or ""))
    if not m:
        return default
    n, unit = float(m.group(1)), m.group(2) or "px"
    return {"rem": n * 12, "em": n * 12, "px": n * 0.75, "pt": n}[unit]


def _px(n: float) -> float:
    return n * 0.75


class _Sink:
    """Where paragraphs go: the document body, or a table cell (reusing the cell's empty first paragraph)."""
    def __init__(self, container):
        self.c = container
        self.reuse = hasattr(container, "_tc")

    def par(self):
        if self.reuse:
            self.reuse = False
            return self.c.paragraphs[0]
        return self.c.add_paragraph()


# ---------------------------------------------------------------- generator
class DOCXGenerator:
    def __init__(self, templates_dir: Optional[str] = None):
        # templates_dir is accepted for backward compatibility; no .docx template is used any more
        self.cache_dir = os.path.join(os.path.dirname(__file__), "..", "..", "output", "image_cache")
        os.makedirs(self.cache_dir, exist_ok=True)

    # ---- public API -----------------------------------------------------
    def new_document(self) -> Document:
        doc = Document()
        sec = doc.sections[0]
        sec.page_width, sec.page_height = Inches(8.27), Inches(11.69)
        sec.left_margin = sec.right_margin = Inches(1.0)
        sec.top_margin, sec.bottom_margin = Inches(0.8), Inches(0.8)
        normal = doc.styles["Normal"]
        normal.font.name = FONT
        normal.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
        normal.font.size = Pt(10.5)
        normal.paragraph_format.space_before = Pt(0)
        normal.paragraph_format.space_after = Pt(0)
        return doc

    def generate_section_docx(self, section: Dict[str, Any], subcategories: List[Dict[str, Any]],
                              approved_entries: List[Dict[str, Any]], output_path: str,
                              layout: Optional[List[Dict[str, Any]]] = None,
                              issue: Optional[Dict[str, Any]] = None) -> str:
        doc = self.new_document()
        self.add_section(doc, section, subcategories, approved_entries, layout, issue)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        doc.save(output_path)
        return output_path

    def add_section(self, doc: Document, section: Dict[str, Any], subcategories: List[Dict[str, Any]],
                    entries: List[Dict[str, Any]], layout: Optional[List[Dict[str, Any]]] = None,
                    issue: Optional[Dict[str, Any]] = None, page_break_before: bool = False) -> int:
        """Masthead (as on the designer's page) followed by every entry rendered from the layout."""
        blocks = normalize_layout(layout)
        entries = order_entries(dedupe_entries(entries), subcategories)
        self._masthead(doc, section.get("name", ""), issue, page_break_before)
        for i, entry in enumerate(entries):
            if i:
                self._rule(doc, 10, 10)
            self._render_entry(doc, entry, blocks)
        return len(entries)

    def add_cover(self, doc: Document, issue: Optional[Dict[str, Any]]):
        issue = issue or {}
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(2)
        r = p.add_run("IT CHRONICLES")
        r.font.size, r.font.bold, r.font.color.rgb = Pt(30), True, RGBColor.from_string(NAVY)
        sub = " · ".join(str(x) for x in [issue.get("department_name"), issue.get("cover_title")] if x)
        if sub:
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(2)
            r = p.add_run(sub)
            r.font.size, r.font.color.rgb = Pt(11), RGBColor.from_string(BYLINE)
        meta = " · ".join(x for x in [f"Vol. {issue['volume']} Issue {issue['issue']}" if issue.get("volume") else "",
                                     issue.get("academic_year"), issue.get("semester"), issue.get("publication_period")] if x)
        if meta:
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(18)
            r = p.add_run(meta)
            r.font.size, r.font.color.rgb = Pt(9.5), RGBColor.from_string(META)

    # ---- page furniture ---------------------------------------------------
    def _masthead(self, doc, section_name: str, issue: Optional[Dict[str, Any]], page_break_before: bool):
        p = doc.add_paragraph()
        p.paragraph_format.page_break_before = page_break_before
        p.paragraph_format.space_after = Pt(16)
        p.paragraph_format.tab_stops.add_tab_stop(Inches(CONTENT_WIDTH_IN), WD_TAB_ALIGNMENT.RIGHT)
        p._p.get_or_add_pPr().append(parse_xml(
            f'<w:pBdr {nsdecls("w")}>'
            f'<w:top w:val="single" w:sz="36" w:space="6" w:color="{NAVY}"/>'
            f'<w:bottom w:val="single" w:sz="12" w:space="4" w:color="{NAVY}"/></w:pBdr>'))
        left = "IT CHRONICLES" + (f" · {section_name.upper()}" if section_name else "")
        right = f"VOL. {issue['volume']} · ISSUE {issue['issue']}" if issue and issue.get("volume") else ""
        r = p.add_run(left)
        r.font.size, r.font.bold, r.font.color.rgb = Pt(8.5), True, RGBColor.from_string(NAVY)
        self._spacing(r, 1.5)
        if right:
            r2 = p.add_run("\t" + right)
            r2.font.size, r2.font.bold, r2.font.color.rgb = Pt(8.5), True, RGBColor.from_string(META)

    @staticmethod
    def _spacing(run, pts: float):
        el = OxmlElement("w:spacing")
        el.set(qn("w:val"), str(int(pts * 20)))
        run._element.get_or_add_rPr().append(el)

    def _rule(self, container, space_before: float = 6, space_after: float = 6, color: str = RULE):
        p = container.par() if isinstance(container, _Sink) else container.add_paragraph()
        p.paragraph_format.space_before = Pt(space_before)
        p.paragraph_format.space_after = Pt(space_after)
        p._p.get_or_add_pPr().append(parse_xml(
            f'<w:pBdr {nsdecls("w")}><w:bottom w:val="single" w:sz="6" w:space="1" w:color="{color}"/></w:pBdr>'))

    # ---- one entry ----------------------------------------------------------
    def _render_entry(self, doc, entry: Dict[str, Any], blocks: List[Dict[str, Any]]):
        sink = _Sink(doc)
        for idx, blk in enumerate(blocks):
            st = blk.get("style") or {}
            if blk.get("type") == "image" and st.get("float") == "left":
                path = self._image_for(entry, blk)
                if path:
                    # what follows sits beside the photo, as it wraps in the designer
                    self._beside_text(doc, entry, blk, path, blocks[idx + 1:])
                    return
                continue
            self._render_block(sink, entry, blk, CONTENT_WIDTH_IN)

    def _beside_text(self, doc, entry, image_blk, image_path: str, rest: List[Dict[str, Any]]):
        table = doc.add_table(rows=1, cols=2)
        table.alignment = WD_TABLE_ALIGNMENT.LEFT
        table.autofit = False
        table._tbl.tblPr.append(parse_xml(f'<w:tblLayout {nsdecls("w")} w:type="fixed"/>'))
        left_w, right_w = Inches(FLOAT_IMAGE_IN + 0.15), Inches(CONTENT_WIDTH_IN - FLOAT_IMAGE_IN - 0.15)
        c_img, c_txt = table.rows[0].cells
        c_img.width, c_txt.width = left_w, right_w
        table.columns[0].width, table.columns[1].width = left_w, right_w
        for cell, (l, r) in ((c_img, (0, 120)), (c_txt, (120, 0))):
            cell._element.get_or_add_tcPr().append(parse_xml(
                f'<w:tcMar {nsdecls("w")}><w:top w:w="0" w:type="dxa"/><w:left w:w="{l}" w:type="dxa"/>'
                f'<w:bottom w:w="0" w:type="dxa"/><w:right w:w="{r}" w:type="dxa"/></w:tcMar>'))
        self._render_block(_Sink(c_img), entry, image_blk, FLOAT_IMAGE_IN, resolved=image_path)
        sink = _Sink(c_txt)
        for blk in rest:
            self._render_block(sink, entry, blk, CONTENT_WIDTH_IN - FLOAT_IMAGE_IN - 0.3)

    # ---- blocks ---------------------------------------------------------------
    def _run(self, p, text: str, size_pt: float, bold: bool, color: str, style: Optional[Dict[str, Any]] = None, italic: bool = False):
        """Add a run; the layout's own font size / weight / colour win over the defaults."""
        st = style or {}
        r = p.add_run(text)
        r.font.size = Pt(_pt(st.get("fontSize"), size_pt) if st.get("fontSize") else size_pt)
        weight = str(st.get("fontWeight") or "")
        r.font.bold = (weight == "bold" or (weight.isdigit() and int(weight) >= 600)) if weight else bold
        r.font.color.rgb = RGBColor.from_string(_hex(st.get("textColor")) or color)
        r.font.italic = italic
        return r

    def _render_block(self, sink: _Sink, entry: Dict[str, Any], blk: Dict[str, Any], width_in: float, resolved: Optional[str] = None):
        btype = blk.get("type")
        st = blk.get("style") or {}
        tag = blk.get("tag") or ""
        val = str(entry.get(tag) or "").strip() if tag else ""
        align = WD_ALIGN_PARAGRAPH.CENTER if st.get("textAlign") == "center" else WD_ALIGN_PARAGRAPH.LEFT

        if btype == "divider":
            self._rule(sink, 6, 6, _hex(st.get("borderColor"), RULE))
            return
        if not val:
            return

        if btype == "badge":
            p = sink.par()
            p.paragraph_format.space_after = Pt(6)
            fill = _hex(st.get("bgColor")) or BADGE_FILL.get(st.get("badgeColor", "navy"), NAVY)
            r = self._run(p, f"  {val.upper()}  ", 8.25, True, "FFFFFF", {"textColor": st.get("textColor")})
            self._shade(r, fill)
        elif btype == "headline":
            p = sink.par()
            p.alignment = align
            p.paragraph_format.space_after = Pt(5)
            p.paragraph_format.line_spacing = 1.2
            self._run(p, val, _px(23), True, NAVY, st)
        elif btype == "byline":
            p = sink.par()
            p.paragraph_format.space_after = Pt(5)
            self._run(p, f"By {val}", _px(14), True, BYLINE, st)
        elif btype == "meta":
            p = sink.par()
            p.paragraph_format.space_after = Pt(6)
            date = str(entry.get("event_date") or "").strip()
            self._run(p, val + (f" · {date}" if date else ""), _px(13), False, META, st)
        elif btype == "text":
            p = sink.par()
            p.alignment = align
            p.paragraph_format.space_after = Pt(8)
            try:
                p.paragraph_format.line_spacing = float(st.get("lineHeight") or 1.6)
            except ValueError:
                p.paragraph_format.line_spacing = 1.6
            self._run(p, val, _px(14), False, BODY, st)
        elif btype == "stats":
            p = sink.par()
            p.paragraph_format.space_before = Pt(4)
            p.paragraph_format.space_after = Pt(8)
            p.paragraph_format.left_indent = Inches(0.12)
            pPr = p._p.get_or_add_pPr()
            pPr.append(parse_xml(f'<w:pBdr {nsdecls("w")}><w:left w:val="single" w:sz="24" w:space="8" w:color="{AMBER}"/></w:pBdr>'))
            pPr.append(parse_xml(f'<w:shd {nsdecls("w")} w:val="clear" w:color="auto" w:fill="{STAT_BG}"/>'))
            self._run(p, val, _px(24), True, AMBER)
            label = str(entry.get("badge_tag") or "").strip()
            if label and label != val:
                self._run(p, f"   {label}", _px(13), True, BYLINE)
        elif btype == "link":
            p = sink.par()
            p.paragraph_format.space_after = Pt(8)
            self._button(p, val, blk.get("linkText") or "View details", st)
        elif btype == "image":
            path = resolved or self._image_for(entry, blk)
            if not path:
                return
            p = sink.par()
            p.paragraph_format.space_after = Pt(0)
            try:
                p.add_run().add_picture(path, width=Inches(width_in))
            except Exception:
                return
            cap = str(entry.get(blk.get("captionTag") or "photo_caption") or "").strip()
            if cap:
                pc = sink.par()
                pc.paragraph_format.space_after = Pt(8)
                pc._p.get_or_add_pPr().append(parse_xml(f'<w:shd {nsdecls("w")} w:val="clear" w:color="auto" w:fill="{CAPTION_BG}"/>'))
                self._run(pc, f" {cap}", _px(12), False, CAPTION, italic=True)
            else:
                p.paragraph_format.space_after = Pt(8)

    # ---- inline pieces ---------------------------------------------------------
    @staticmethod
    def _shade(run, fill_hex: str):
        run._element.get_or_add_rPr().append(parse_xml(f'<w:shd {nsdecls("w")} w:val="clear" w:color="auto" w:fill="{fill_hex}"/>'))

    def _button(self, p, url: str, text: str, st: Dict[str, Any]):
        kind = st.get("buttonStyle", "solid")
        fill = _hex(st.get("bgColor")) or BUTTON_FILL.get(kind)
        color = _hex(st.get("textColor")) or ("FFFFFF" if fill else NAVY)
        if not url.startswith(("http://", "https://")):
            self._run(p, f"{text}: {url}", _px(13), True, NAVY)
            return
        r_id = p.part.relate_to(url, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink", is_external=True)
        link = OxmlElement("w:hyperlink")
        link.set(qn("r:id"), r_id)
        run = OxmlElement("w:r")
        rPr = OxmlElement("w:rPr")
        for tag, attrs in (("w:b", {}), ("w:color", {"w:val": color}), ("w:sz", {"w:val": str(int(_px(13) * 2))})):
            el = OxmlElement(tag)
            for k, v in attrs.items():
                el.set(qn(k), v)
            rPr.append(el)
        if not fill:   # outline style: border instead of fill
            bdr = OxmlElement("w:bdr")
            for k, v in (("w:val", "single"), ("w:sz", "12"), ("w:space", "2"), ("w:color", NAVY)):
                bdr.set(qn(k), v)
            rPr.append(bdr)
        else:
            shd = OxmlElement("w:shd")
            for k, v in (("w:val", "clear"), ("w:color", "auto"), ("w:fill", fill)):
                shd.set(qn(k), v)
            rPr.append(shd)
        run.append(rPr)
        t = OxmlElement("w:t")
        t.text = f"   {text}   "
        t.set(qn("xml:space"), "preserve")
        run.append(t)
        link.append(run)
        p._p.append(link)

    # ---- images ----------------------------------------------------------------
    def _image_for(self, entry: Dict[str, Any], blk: Dict[str, Any]) -> Optional[str]:
        src = self._resolve_image(str(entry.get(blk.get("tag") or "") or "").strip())
        if not src:
            return None
        return self._crop(src, ASPECT.get((blk.get("style") or {}).get("aspectRatio", "16:9"), 16 / 9))

    def _crop(self, path: str, ratio: float) -> str:
        """Centre-crop to the chosen shape (the designer shows the photo with object-fit: cover)."""
        out = os.path.join(self.cache_dir, f"crop_{hashlib.md5((path + str(ratio)).encode()).hexdigest()}.jpg")
        if os.path.exists(out):
            return out
        try:
            with Image.open(path) as img:
                img = img.convert("RGB")
                w, h = img.size
                if w / h > ratio:
                    nw = int(h * ratio)
                    box = ((w - nw) // 2, 0, (w - nw) // 2 + nw, h)
                else:
                    nh = int(w / ratio)
                    box = (0, (h - nh) // 2, w, (h - nh) // 2 + nh)
                img.crop(box).save(out, "JPEG", quality=88)
            return out
        except Exception:
            return path

    def _resolve_image(self, photo_url: Optional[str]) -> Optional[str]:
        """Local path, or download (Google Drive links supported) into a cache. None if unusable."""
        if not photo_url:
            return None
        if os.path.exists(photo_url):
            try:
                with Image.open(photo_url) as img:
                    img.verify()
                return photo_url
            except Exception:
                return None
        if not photo_url.startswith(("http://", "https://")):
            return None

        url = photo_url
        if "drive.google.com" in url:
            m = re.search(r"(?:/d/|id=)([a-zA-Z0-9_-]+)", url)
            if m:
                url = f"https://drive.google.com/uc?export=download&id={m.group(1)}"

        cached = os.path.join(self.cache_dir, f"img_{hashlib.md5(url.encode()).hexdigest()}.jpg")
        if os.path.exists(cached):
            try:
                with Image.open(cached) as img:
                    img.verify()
                return cached
            except Exception:
                pass
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = resp.read()
            with open(cached, "wb") as f:
                f.write(data)
            with Image.open(cached) as img:
                img.verify()
            return cached
        except Exception:
            return None
