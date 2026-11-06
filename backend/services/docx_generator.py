"""
Word output, driven entirely by the layout chosen in the Layout designer.

A layout is a 12-column grid: every element has a position (x, y) and size (w, h) in grid
cells, a link to a form column, and its own styling. Each entry becomes one borderless table
with 12 columns, and every element is a merged cell covering the same cells it covers on the
designer's canvas, so what is arranged on the canvas is what lands on the page.

Two fixed layouts sit beside the canvas ("centered" and "alternating"), and the pages that come
before the sections (the HOD's Desk and the editorial page) are built from the front-matter content.
An element with no data leaves no hole in any of them: no photo means no photo space.
"""
import os
import re
import math
import hashlib
import urllib.request
from typing import List, Dict, Any, Optional

from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT, WD_LINE_SPACING
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ROW_HEIGHT_RULE, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import parse_xml, OxmlElement
from docx.oxml.ns import nsdecls, qn
from PIL import Image

try:
    from database.db_manager import get_raw_response
except Exception:   # the generator can be used without a database
    get_raw_response = None

# ---------------------------------------------------------------- palette (same values as the designer's CSS)
# Everything is printed in black, in Arial Narrow, at fixed sizes; only image captions are a slight grey
BLACK, GREY = "000000", "595959"
NAVY = AMBER = SLATE = GREEN = BODY = BYLINE = META = CAPTION = RULE = BLACK
SIZE_BODY, SIZE_MAIN, SIZE_SECTION, SIZE_SUB, SIZE_CAPTION = 12, 14, 16, 12, 9   # running text / main heading / section heading / sub heading (bold) / image caption
ASPECT = {"16:9": 16 / 9, "4:3": 4 / 3, "1:1": 1.0}

COLS = 12
ROW_PX = 28                            # height of one grid row in the designer (css px)
CANVAS_PX = 600                        # width of the designer page content (css px)
CONTENT_WIDTH_IN = 8.27 - 2.0          # A4 minus 1" margins
CELL_PAD_IN = 0.04
CAPTION_PX = 18
FONT = "Arial Narrow"

# default size (grid rows) of each element type
DEFAULT_H = {"badge": 1, "headline": 3, "byline": 1, "meta": 1, "text": 6, "image": 12, "link": 2, "stats": 2, "divider": 1, "label": 2}

DEFAULT_LAYOUT: List[Dict[str, Any]] = [
    {"type": "badge", "tag": "badge_tag", "x": 1, "y": 1, "w": 12, "h": 1, "style": {"badgeColor": "navy"}},
    {"type": "headline", "tag": "title", "x": 1, "y": 2, "w": 12, "h": 3, "style": {}},
    {"type": "byline", "tag": "author_or_person", "x": 1, "y": 5, "w": 12, "h": 1, "style": {}},
    {"type": "image", "tag": "photo_url", "x": 1, "y": 6, "w": 12, "h": 12, "style": {"showCaption": True}},
    {"type": "text", "tag": "description", "x": 1, "y": 18, "w": 12, "h": 6, "style": {}},
    {"type": "link", "tag": "evidence_url", "x": 1, "y": 24, "w": 6, "h": 2, "linkText": "View details", "style": {"buttonStyle": "solid"}},
]


# ---------------------------------------------------------------- layout model helpers
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


def _has_grid(b: Dict[str, Any]) -> bool:
    return all(isinstance(b.get(k), (int, float)) for k in ("x", "y", "w", "h"))


def ensure_grid(layout: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Layouts saved before the canvas existed are flat lists; stack them top to bottom (same rules as the designer)."""
    blocks = [dict(b) for b in (layout or DEFAULT_LAYOUT)]
    for b in blocks:
        if b.get("type") == "text" and b.get("tag") in _TEXT_ROLE_BY_TAG:
            b["type"] = _TEXT_ROLE_BY_TAG[b["tag"]]
        b["style"] = dict(b.get("style") or {})
    if all(_has_grid(b) for b in blocks):
        return blocks
    y = 1
    for i, b in enumerate(blocks):
        ratio = ASPECT.get(b["style"].get("aspectRatio", "16:9"), 16 / 9)
        if b.get("type") == "image" and b["style"].get("float") == "left":
            iw = 4
            ih = max(3, round(iw * CANVAS_PX / COLS / ratio / ROW_PX))
            b.update(x=1, y=y, w=iw, h=ih)
            ry = y
            for r in blocks[i + 1:]:
                r.update(x=iw + 1, y=ry, w=COLS - iw, h=DEFAULT_H.get(r.get("type"), 2))
                ry += r["h"]
            break
        h = round(COLS * CANVAS_PX / COLS / ratio / ROW_PX) if b.get("type") == "image" else DEFAULT_H.get(b.get("type"), 2)
        b.update(x=1, y=y, w=COLS, h=h)
        y += h
    return compact(blocks)


def _overlap(a, b) -> bool:
    return a["x"] < b["x"] + b["w"] and b["x"] < a["x"] + a["w"] and a["y"] < b["y"] + b["h"] and b["y"] < a["y"] + a["h"]


def compact(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Float every element up until it rests on another (identical to the designer's behaviour)."""
    placed: List[Dict[str, Any]] = []
    for b in sorted(blocks, key=lambda b: (b["y"], b["x"])):
        b["y"] = 1
        while True:
            hit = next((p for p in placed if _overlap(p, b)), None)
            if not hit:
                break
            b["y"] = hit["y"] + hit["h"]
        placed.append(b)
    return blocks


def normalize_layout(layout: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    return ensure_grid(layout)


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


_ALIGN = {"left": WD_ALIGN_PARAGRAPH.LEFT, "center": WD_ALIGN_PARAGRAPH.CENTER,
          "right": WD_ALIGN_PARAGRAPH.RIGHT, "justify": WD_ALIGN_PARAGRAPH.JUSTIFY}
_VALIGN = {"top": WD_CELL_VERTICAL_ALIGNMENT.TOP, "middle": WD_CELL_VERTICAL_ALIGNMENT.CENTER, "bottom": WD_CELL_VERTICAL_ALIGNMENT.BOTTOM}


_PPR_AFTER_PBDR = ("w:shd", "w:tabs", "w:suppressAutoHyphens", "w:kinsoku", "w:wordWrap", "w:overflowPunct", "w:topLinePunct",
                   "w:autoSpaceDE", "w:autoSpaceDN", "w:bidi", "w:adjustRightInd", "w:snapToGrid", "w:spacing", "w:ind",
                   "w:contextualSpacing", "w:mirrorIndents", "w:suppressOverlap", "w:jc", "w:textDirection", "w:textAlignment",
                   "w:textboxTightWrap", "w:outlineLvl", "w:divId", "w:cnfStyle", "w:rPr", "w:sectPr", "w:pPrChange")
_RPR_AFTER_SPACING = ("w:w", "w:kern", "w:position", "w:sz", "w:szCs", "w:highlight", "w:u", "w:effect", "w:bdr", "w:shd",
                      "w:fitText", "w:vertAlign", "w:rtl", "w:cs", "w:em", "w:lang", "w:eastAsianLayout", "w:specVanish", "w:oMath")
_TCPR_AFTER_BORDERS = ("w:shd", "w:noWrap", "w:tcMar", "w:textDirection", "w:tcFitText", "w:vAlign", "w:hideMark")
_TCPR_AFTER_SHD = _TCPR_AFTER_BORDERS[1:]


def _p_border(p, xml: str):
    p._p.get_or_add_pPr().insert_element_before(parse_xml(xml), *_PPR_AFTER_PBDR)


def _p_shade(p, fill_hex: str):
    p._p.get_or_add_pPr().insert_element_before(
        parse_xml(f'<w:shd {nsdecls("w")} w:val="clear" w:color="auto" w:fill="{fill_hex}"/>'), *_PPR_AFTER_PBDR[1:])


def _make_floating(inline, side: str, gap_in: float = 0.15, top_in: float = 0.0):
    """Turn a picture's <wp:inline> into a <wp:anchor> that text wraps around, on the left or right margin."""
    gap = int(gap_in * 914400)
    dist_l, dist_r = (0, gap) if side == "left" else (gap, 0)
    anchor = parse_xml(
        f'<wp:anchor {nsdecls("wp")} distT="0" distB="{int(0.05 * 914400)}" distL="{dist_l}" distR="{dist_r}" simplePos="0" '
        f'relativeHeight="251658240" behindDoc="0" locked="0" layoutInCell="1" allowOverlap="0">'
        f'<wp:simplePos x="0" y="0"/>'
        f'<wp:positionH relativeFrom="margin"><wp:align>{side}</wp:align></wp:positionH>'
        f'<wp:positionV relativeFrom="paragraph"><wp:posOffset>{int(top_in * 914400)}</wp:posOffset></wp:positionV>'
        f'<wp:wrapSquare wrapText="bothSides"/></wp:anchor>')
    anchor.insert(3, inline.find(qn("wp:extent")))     # extent follows positionV
    anchor.append(inline.find(qn("wp:docPr")))
    anchor.append(OxmlElement("wp:cNvGraphicFramePr"))
    anchor.append(inline.find(qn("a:graphic")))
    inline.getparent().replace(inline, anchor)


class _Sink:
    """Where paragraphs go: a table cell (reusing its empty first paragraph) or the document body."""
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
        self._raw_cache: Dict[str, Dict[str, Any]] = {}

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
        normal.font.size = Pt(SIZE_BODY)
        normal.paragraph_format.space_before = Pt(0)
        normal.paragraph_format.space_after = Pt(0)
        return doc

    def generate_section_docx(self, section: Dict[str, Any], subcategories: List[Dict[str, Any]],
                              approved_entries: List[Dict[str, Any]], output_path: str,
                              layout: Optional[List[Dict[str, Any]]] = None,
                              issue: Optional[Dict[str, Any]] = None, mode: Optional[str] = None) -> str:
        doc = self.new_document()
        self.add_section(doc, section, subcategories, approved_entries, layout, issue, mode=mode)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        doc.save(output_path)
        return output_path

    def add_section(self, doc: Document, section: Dict[str, Any], subcategories: List[Dict[str, Any]],
                    entries: List[Dict[str, Any]], layout: Optional[List[Dict[str, Any]]] = None,
                    issue: Optional[Dict[str, Any]] = None, page_break_before: bool = False,
                    mode: Optional[str] = None) -> int:
        """Masthead (as on the designer's page) followed by every entry, either from the canvas layout
        or, when `mode` is "centered" / "alternating", from one of the two fixed layouts."""
        blocks = ensure_grid(layout)
        entries = order_entries(dedupe_entries(entries), subcategories)
        self._masthead(doc, section.get("name", ""), issue, page_break_before)
        side = "left"                                  # every section starts with its image on the left
        for i, entry in enumerate(entries):
            if i:
                doc.paragraphs[-1].paragraph_format.keep_with_next = True      # the rule belongs to the entry above it, never alone on the next page
                self._rule(doc, 8, 8)
            if mode == "centered":
                self._render_centered(doc, entry)
            elif mode == "alternating":
                # the first photo of a section starts clear of the masthead; Word otherwise tucks it up against the header
                if self._render_wrapped(doc, entry, side, top_in=0.15 if i == 0 else 0.0):
                    side = "right" if side == "left" else "left"
            else:
                self._render_entry(doc, entry, blocks)
        return len(entries)

    def add_cover(self, doc: Document, issue: Optional[Dict[str, Any]]):
        """Nameplate: heavy rule, centred title, department and issue lines, light rule."""
        issue = issue or {}
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(4)
        _p_border(p, f'<w:pBdr {nsdecls("w")}><w:top w:val="single" w:sz="36" w:space="8" w:color="{BLACK}"/></w:pBdr>')
        r = self._run(p, "IT CHRONICLES", SIZE_SECTION, True, BLACK)
        sp = OxmlElement("w:spacing")
        sp.set(qn("w:val"), "80")
        r._element.get_or_add_rPr().insert_element_before(sp, *_RPR_AFTER_SPACING)
        sub = " · ".join(str(x) for x in [issue.get("department_name"), issue.get("cover_title")] if x)
        meta = " · ".join(x for x in [f"Vol. {issue['volume']} Issue {issue['issue']}" if issue.get("volume") else "",
                                     issue.get("academic_year"), issue.get("semester"), issue.get("publication_period")] if x)
        lines = [l for l in (sub, meta) if l]
        for line in lines:
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_after = Pt(2)
            self._run(p, line, SIZE_BODY, False, BLACK)
        last = doc.paragraphs[-1]                                                       # the title itself when there are no lines
        last.paragraph_format.space_after = Pt(14)
        _p_border(last, f'<w:pBdr {nsdecls("w")}><w:bottom w:val="single" w:sz="8" w:space="6" w:color="{BLACK}"/></w:pBdr>')

    # ---- front pages ------------------------------------------------------------
    def _heading(self, doc, text: str, size: float = SIZE_SECTION, space_before: float = 10, space_after: float = 6,
                 align=WD_ALIGN_PARAGRAPH.LEFT, style: str = "rule"):
        """Heading in one of three looks: "rule" (underlined), "bar" (heavy bar at the left) or "band" (heavy rule above, light below)."""
        p = doc.par() if isinstance(doc, _Sink) else doc.add_paragraph()
        p.alignment = align
        p.paragraph_format.space_before = Pt(space_before)
        p.paragraph_format.space_after = Pt(space_after)
        p.paragraph_format.keep_with_next = True
        borders = {
            "rule": f'<w:bottom w:val="single" w:sz="8" w:space="2" w:color="{BLACK}"/>',
            "bar": f'<w:left w:val="single" w:sz="36" w:space="8" w:color="{BLACK}"/>',
            "band": f'<w:top w:val="single" w:sz="24" w:space="4" w:color="{BLACK}"/><w:bottom w:val="single" w:sz="6" w:space="4" w:color="{BLACK}"/>',
        }[style]
        _p_border(p, f'<w:pBdr {nsdecls("w")}>{borders}</w:pBdr>')
        if style == "bar":
            p.paragraph_format.left_indent = Inches(0.15)
        r = self._run(p, text.upper() if style != "rule" else text, size, True, BLACK)
        if style != "rule":
            sp = OxmlElement("w:spacing")
            sp.set(qn("w:val"), "40")
            r._element.get_or_add_rPr().insert_element_before(sp, *_RPR_AFTER_SPACING)
        return p

    def _photo(self, value: Any, ratio: float) -> Optional[str]:
        """A front-matter photo cropped to `ratio` (width / height), or None when there is no usable picture."""
        from backend.services.front_matter_service import FrontMatterService
        src = self._resolve_image(FrontMatterService.resolve_path(value))
        return self._crop(src, ratio) if src else None

    @staticmethod
    def _frame(inline):
        """A thin black outline around a picture."""
        sp_pr = inline.find(".//" + qn("pic:spPr"))
        if sp_pr is not None:
            sp_pr.append(parse_xml(f'<a:ln {nsdecls("a")} w="12700"><a:solidFill><a:srgbClr val="{BLACK}"/></a:solidFill></a:ln>'))

    @staticmethod
    def _cell_box(cell, fill: str, pad_in: float):
        """Shade a table cell and give it inner padding."""
        tcPr = cell._element.get_or_add_tcPr()
        pad = int(pad_in * 1440)
        tcPr.insert_element_before(parse_xml(f'<w:shd {nsdecls("w")} w:val="clear" w:color="auto" w:fill="{fill}"/>'),
                                   *_TCPR_AFTER_SHD)
        tcPr.insert_element_before(parse_xml(
            f'<w:tcMar {nsdecls("w")}><w:top w:w="{pad}" w:type="dxa"/><w:left w:w="{pad}" w:type="dxa"/>'
            f'<w:bottom w:w="{pad}" w:type="dxa"/><w:right w:w="{pad}" w:type="dxa"/></w:tcMar>'),
            "w:textDirection", "w:tcFitText", "w:vAlign", "w:hideMark")

    def _float_in_paragraph(self, p, picture_path: str, width_in: float, side: str, top_in: float = 0.0, framed: bool = False):
        """Put a picture in `p` as a floating anchor that the paragraph's text wraps around."""
        run = p.add_run()
        inline = run.add_picture(picture_path, width=Inches(width_in))._inline
        if framed:
            self._frame(inline)
        _make_floating(inline, side, top_in=top_in)
        p._p.remove(run._r)
        p._p.insert(p._p.index(p._p.pPr) + 1 if p._p.pPr is not None else 0, run._r)

    def add_front_page(self, doc: Document, fm: Dict[str, Any], issue: Optional[Dict[str, Any]] = None) -> bool:
        """Cover page (nameplate and one large image), then the HOD's Desk page: the HOD's photo on the left with the
        name beneath it and the message to its right, followed by vision and mission in two shaded panels.
        Without a cover image the nameplate simply heads the HOD's Desk page."""
        self.add_cover(doc, issue)
        cover = self._photo((fm.get("cover") or {}).get("photo"), CONTENT_WIDTH_IN / 7.4)
        if cover:
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            self._frame(p.add_run().add_picture(cover, width=Inches(CONTENT_WIDTH_IN))._inline)

        hod = fm.get("hod") or {}
        message = [m.strip() for m in str(hod.get("message") or "").splitlines() if m.strip()]
        photo = self._photo(hod.get("photo"), 2.0 / 2.6)
        name, desig = str(hod.get("name") or "").strip(), str(hod.get("designation") or "").strip()
        has_hod = bool(message or photo or name)
        panels = [(t, [x for x in fm.get(k) or [] if str(x).strip()]) for t, k in (("Vision", "vision"), ("Mission", "mission"))]
        panels = [(t, pts) for t, pts in panels if pts]
        new_page = bool(cover)

        if has_hod:
            h = self._heading(doc, "The HOD's Desk", SIZE_SECTION, 6, 12, style="bar")
            h.paragraph_format.page_break_before = new_page
            new_page = False
            para = lambda sink: self._message_paragraph(sink)
            if photo:
                left_w = 2.4
                table = doc.add_table(rows=1, cols=2)
                table.autofit = False
                left, right = table.rows[0].cells
                left.width, right.width = Inches(left_w), Inches(CONTENT_WIDTH_IN - left_w)
                self._person(_Sink(left), hod.get("photo"), name, desig, 2.0, 2.6)
                sink = _Sink(right)
                for m in message:
                    self._run(para(sink), m, SIZE_BODY, False, BODY)
                for p in right.paragraphs:
                    p.paragraph_format.left_indent = Inches(0.1)
            else:
                for m in message:
                    self._run(para(_Sink(doc)), m, SIZE_BODY, False, BODY)
                if name or desig:
                    self._signature(doc, name, desig)

        if panels:
            gap = 0.25
            n = len(panels)
            table = doc.add_table(rows=1, cols=n * 2 - 1)
            table.autofit = False
            panel_w = (CONTENT_WIDTH_IN - gap * (n - 1)) / n
            for i, cell in enumerate(table.rows[0].cells):
                cell.width = Inches(panel_w if i % 2 == 0 else gap)
            spacer = doc.add_paragraph()                                              # air above the panels
            spacer.paragraph_format.space_after = Pt(0)
            spacer.paragraph_format.page_break_before = new_page
            table._tbl.addprevious(spacer._p)
            for i, (title, pts) in enumerate(panels):
                cell = table.rows[0].cells[i * 2]
                self._cell_box(cell, "F2F2F2", 0.1)
                self._heading(_Sink(cell), title, SIZE_SUB, 0, 6, style="rule")
                for pt in pts:
                    p = cell.add_paragraph(style="List Bullet")
                    p.paragraph_format.space_after = Pt(2)
                    self._run(p, pt, SIZE_BODY, False, BODY)
            self._keep_table_together(table)
        return bool(cover) or has_hod or bool(panels)

    @staticmethod
    def _message_paragraph(sink: _Sink):
        p = sink.par()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p.paragraph_format.line_spacing = 1.2
        p.paragraph_format.space_after = Pt(6)
        return p

    def _signature(self, doc, name: str, desig: str):
        """Name and designation under a short rule, at the right (used when the HOD has no photo)."""
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        p.paragraph_format.space_before = Pt(10)
        p.paragraph_format.left_indent = Inches(CONTENT_WIDTH_IN - 2.6)
        _p_border(p, f'<w:pBdr {nsdecls("w")}><w:top w:val="single" w:sz="8" w:space="4" w:color="{BLACK}"/></w:pBdr>')
        if name:
            self._run(p, name, SIZE_SUB, True, BLACK)
        if name and desig:
            p.add_run().add_break()
        if desig:
            self._run(p, desig, SIZE_CAPTION, False, GREY)

    def add_editorial_page(self, doc: Document, fm: Dict[str, Any]) -> bool:
        """Faculty advisor centred on top, then the student editors in one row, each with a caption."""
        adv = fm.get("advisor") or {}
        has = lambda d: any(str(d.get(k) or "").strip() for k in ("name", "photo"))
        students = [s for s in fm.get("students") or [] if has(s)]
        if not (has(adv) or students):
            return False
        p = self._heading(doc, "Editorial Board", SIZE_SECTION, 0, 18, WD_ALIGN_PARAGRAPH.CENTER, style="band")
        p.paragraph_format.page_break_before = True

        if has(adv):
            self._person(_Sink(doc), adv.get("photo"), adv.get("name"), adv.get("designation"), 2.0, 2.5)
            doc.add_paragraph().paragraph_format.space_after = Pt(10)

        if students:
            label = self._heading(doc, "Student Editors", SIZE_SUB, 6, 12, WD_ALIGN_PARAGRAPH.CENTER, style="rule")
            label.paragraph_format.left_indent = label.paragraph_format.right_indent = Inches(1.8)
            table = doc.add_table(rows=1, cols=len(students))
            table.alignment = WD_TABLE_ALIGNMENT.CENTER
            table.autofit = False
            width = CONTENT_WIDTH_IN / len(students)
            photo_w = min(1.45, width - 0.15)
            for cell, s in zip(table.rows[0].cells, students):
                cell.width = Inches(width)
                cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.BOTTOM      # captions line up even when a photo is missing
                self._person(_Sink(cell), s.get("photo"), s.get("name"), s.get("year"), photo_w, photo_w * 1.25)
            self._keep_table_together(table)
        return True

    def _person(self, sink: _Sink, photo: Any, name: Any, caption: Any, width_in: float, height_in: float):
        """Centred framed photo with the name (bold) and a grey caption line beneath; no photo means no photo space."""
        pic = self._photo(photo, width_in / height_in)
        if pic:
            p = sink.par()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_after = Pt(4)
            self._frame(p.add_run().add_picture(pic, width=Inches(width_in))._inline)
        name, caption = str(name or "").strip(), str(caption or "").strip()
        if name:
            p = sink.par()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            self._run(p, name, SIZE_SUB, True, BLACK)
        if caption:
            p = sink.par()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            self._run(p, caption, SIZE_CAPTION, False, GREY)

    @staticmethod
    def _clear_wrap(doc):
        """A hairline paragraph that ends text wrapping, so whatever follows starts below a floating picture."""
        p = doc.add_paragraph()
        pf = p.paragraph_format
        pf.space_before = pf.space_after = Pt(0)
        pf.line_spacing = Pt(1)
        pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        run = p.add_run()
        run.font.size = Pt(1)
        run.add_break()
        br = run._r.find(qn("w:br"))
        br.set(qn("w:type"), "textWrapping")
        br.set(qn("w:clear"), "all")
        return p

    @staticmethod
    def _keep_together(paragraphs):
        """Tie paragraphs to the next one, so an entry is never split across pages and a photo never lands apart from its text."""
        for p in paragraphs[:-1]:
            p.paragraph_format.keep_with_next = True
        for p in paragraphs:
            p.paragraph_format.keep_together = True

    @staticmethod
    def _keep_table_together(table):
        """Rows may not split, and every row but the last stays with the one below it."""
        rows = table.rows
        for i, row in enumerate(rows):
            row._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))
            if i < len(rows) - 1:
                for cell in row.cells:
                    for p in cell.paragraphs:
                        p.paragraph_format.keep_with_next = True

    # ---- the two fixed section layouts ---------------------------------------------
    def _entry_text_blocks(self, entry: Dict[str, Any]):
        """The entry's text elements in reading order, as (block, value); anything empty is left out."""
        spec = [("badge", "badge_tag"), ("headline", "title"), ("byline", "author_or_person"), ("meta", "organization_or_venue"),
                ("text", "description"), ("link", "evidence_url")]
        out = []
        for btype, tag in spec:
            style = {}
            if btype == "text":
                style.update(textAlign="justify", lineHeight="1.15")
            blk = {"type": btype, "tag": tag, "style": style}
            val = self._value(entry, blk)
            if val:
                out.append((blk, val))
        return out

    @staticmethod
    def _text_height(items, width_in: float) -> float:
        """Rough height in inches of the text blocks set in a column `width_in` wide (errs on the short side)."""
        sizes = {"headline": SIZE_MAIN}
        total = 0.0
        for blk, val in items:
            size = sizes.get(blk["type"], SIZE_BODY)
            per_line = max(8, width_in * 72 / (size * 0.42))          # Arial Narrow averages about 0.42 em per character
            total += math.ceil(len(val) / per_line) * size * 1.2 / 72 + 4 / 72
        return total

    def _render_centered(self, doc, entry: Dict[str, Any]):
        """Image centred (with its caption centred under it), then the content underneath. No image: just the content."""
        sink = _Sink(doc)
        start = len(doc.paragraphs)
        img = self._value(entry, {"tag": "photo_url"})
        if img:
            blk = {"type": "image", "style": {"textAlign": "center", "showCaption": True}}
            self._render_block(sink, entry, blk, img, 5.2, 5.2 / (16 / 9) + CAPTION_PX / 96 + 0.05)
        for blk, val in self._entry_text_blocks(entry):
            self._render_block(sink, entry, blk, val, CONTENT_WIDTH_IN, 0)
        added = doc.paragraphs[start:]
        for p in added:
            p.paragraph_format.space_after = Pt(4)
        self._keep_together(added)

    def _render_wrapped(self, doc, entry: Dict[str, Any], side: str, top_in: float = 0.0) -> bool:
        """Photo floated to `side` with the text wrapped around it; no photo gives full-width text.
        The photo is sized to the text it sits beside, so neither leaves empty space; text that runs
        past the photo continues across the full width beneath it. Returns True when a photo was placed,
        so the caller can alternate sides."""
        sink = _Sink(doc)
        items = self._entry_text_blocks(entry)
        for blk, _ in items:
            if blk["type"] == "text":
                blk["style"]["textAlign"] = "left"                    # justified text in a narrow column leaves ragged gaps
        src = self._resolve_image(self._value(entry, {"tag": "photo_url"}))
        pic, img_w = None, 2.4
        if src:
            img_h = 3.0
            for _ in range(2):                                         # width and height depend on each other; two passes settle it
                text_h = self._text_height(items, CONTENT_WIDTH_IN - img_w - 0.15)
                img_h = min(max(text_h, 1.4), 3.0)
                img_w = min(max(img_h * 4 / 3, 1.9), 3.0)
            pic = self._crop(src, img_w / img_h)
        start = len(doc.paragraphs)
        for blk, val in items:
            self._render_block(sink, entry, blk, val, CONTENT_WIDTH_IN, 0)
        added = doc.paragraphs[start:]
        for p in added:
            p.paragraph_format.space_after = Pt(4)
        if not pic:
            self._keep_together(added)
            return False
        if not added:
            added = [doc.add_paragraph()]
        self._float_in_paragraph(added[0], pic, img_w, side, top_in=top_in)
        for p in added:
            p.paragraph_format.keep_with_next = True
            p.paragraph_format.keep_together = True
        added[-1].paragraph_format.keep_with_next = True        # the hairline below keeps the photo's space with its entry
        self._clear_wrap(doc)
        return True

    # ---- page furniture ---------------------------------------------------
    def _masthead(self, doc, section_name: str, issue: Optional[Dict[str, Any]], page_break_before: bool):
        p = doc.add_paragraph()
        p.paragraph_format.page_break_before = page_break_before
        p.paragraph_format.space_after = Pt(16)
        p.paragraph_format.tab_stops.add_tab_stop(Inches(CONTENT_WIDTH_IN), WD_TAB_ALIGNMENT.RIGHT)
        _p_border(p, f'<w:pBdr {nsdecls("w")}>'
                     f'<w:top w:val="single" w:sz="36" w:space="6" w:color="{NAVY}"/>'
                     f'<w:bottom w:val="single" w:sz="12" w:space="4" w:color="{NAVY}"/></w:pBdr>')
        left = "IT CHRONICLES" + (f" · {section_name.upper()}" if section_name else "")
        right = f"VOL. {issue['volume']} · ISSUE {issue['issue']}" if issue and issue.get("volume") else ""
        r = p.add_run(left)
        r.font.size, r.font.bold, r.font.color.rgb = Pt(SIZE_SECTION), True, RGBColor.from_string(BLACK)
        sp = OxmlElement("w:spacing")
        sp.set(qn("w:val"), "30")
        r._element.get_or_add_rPr().insert_element_before(sp, *_RPR_AFTER_SPACING)
        if right:
            r2 = p.add_run("\t" + right)
            r2.font.size, r2.font.bold, r2.font.color.rgb = Pt(SIZE_SUB), True, RGBColor.from_string(BLACK)

    def _rule(self, container, space_before: float = 6, space_after: float = 6, color: str = RULE):
        p = container.par() if isinstance(container, _Sink) else container.add_paragraph()
        p.paragraph_format.space_before = Pt(space_before)
        p.paragraph_format.space_after = Pt(space_after)
        _p_border(p, f'<w:pBdr {nsdecls("w")}><w:bottom w:val="single" w:sz="6" w:space="1" w:color="{color}"/></w:pBdr>')

    # ---- values ---------------------------------------------------------------
    def _raw(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        rid = entry.get("response_id")
        if not rid or get_raw_response is None:
            return {}
        if rid not in self._raw_cache:
            try:
                self._raw_cache[rid] = get_raw_response(rid) or {}
            except Exception:
                self._raw_cache[rid] = {}
        return self._raw_cache[rid]

    def _value(self, entry: Dict[str, Any], blk: Dict[str, Any]) -> str:
        """The element's content: the entry's field for the linked column (falling back to the raw answer by header)."""
        if blk.get("type") == "label":
            return str(blk.get("text") or "").strip()
        tag = blk.get("tag") or ""
        val = entry.get(tag) if tag else None
        if (val is None or str(val).strip() == "") and blk.get("column"):
            val = self._raw(entry).get(blk["column"])
        return str(val or "").strip()

    # ---- one entry = one table ---------------------------------------------------
    def _render_entry(self, doc, entry: Dict[str, Any], layout: List[Dict[str, Any]]):
        items = []
        for b in layout:
            val = self._value(entry, b)
            if val or b.get("type") == "divider":
                items.append((dict(b), val))
        if not items:
            return
        blocks = compact([b for b, _ in items])       # elements with no data leave no hole
        rows = max(b["y"] + b["h"] - 1 for b in blocks)

        table = doc.add_table(rows=rows, cols=COLS)
        table.alignment = WD_TABLE_ALIGNMENT.LEFT
        table.autofit = False
        col_w = Inches(CONTENT_WIDTH_IN / COLS)
        for c in table.columns:
            c.width = col_w
        for row in table.rows:
            row.height = Pt(_px(ROW_PX))
            row.height_rule = WD_ROW_HEIGHT_RULE.AT_LEAST
            for cell in row.cells:
                cell.width = col_w

        cells = []
        for b, (_, val) in zip(blocks, items):
            first = table.cell(b["y"] - 1, b["x"] - 1)
            last = table.cell(b["y"] + b["h"] - 2, b["x"] + b["w"] - 2)
            cells.append((first.merge(last) if first is not last else first, b, val))
        for cell, b, val in cells:
            self._fill_cell(cell, entry, b, val)
        self._keep_table_together(table)

    def _fill_cell(self, cell, entry: Dict[str, Any], blk: Dict[str, Any], val: str):
        st = blk.get("style") or {}
        tcPr = cell._element.get_or_add_tcPr()
        tcPr.insert_element_before(parse_xml(
            f'<w:tcMar {nsdecls("w")}><w:top w:w="20" w:type="dxa"/><w:left w:w="60" w:type="dxa"/>'
            f'<w:bottom w:w="20" w:type="dxa"/><w:right w:w="60" w:type="dxa"/></w:tcMar>'), "w:textDirection", "w:tcFitText", "w:vAlign", "w:hideMark")
        cell.vertical_alignment = _VALIGN.get(st.get("vAlign", "top"), WD_CELL_VERTICAL_ALIGNMENT.TOP)
        box_w = blk["w"] * CONTENT_WIDTH_IN / COLS - 2 * CELL_PAD_IN
        box_h = blk["h"] * ROW_PX / 96
        self._render_block(_Sink(cell), entry, blk, val, box_w, box_h)
        for p in cell.paragraphs:
            p.paragraph_format.space_after = Pt(0)

    # ---- blocks ---------------------------------------------------------------
    def _run(self, p, text: str, size_pt: float, bold: bool, color: str, style: Optional[Dict[str, Any]] = None, italic: bool = False):
        """Add a run: black, at the fixed size for its role (a layout may still choose bold or regular)."""
        st = style or {}
        r = p.add_run(text)
        r.font.size = Pt(size_pt)
        weight = str(st.get("fontWeight") or "")
        r.font.bold = (weight == "bold" or (weight.isdigit() and int(weight) >= 600)) if weight else bold
        r.font.color.rgb = RGBColor.from_string(GREY if color == GREY else BLACK)
        r.font.italic = italic
        return r

    def _render_block(self, sink: _Sink, entry: Dict[str, Any], blk: Dict[str, Any], val: str, width_in: float, height_in: float):
        btype = blk.get("type")
        st = blk.get("style") or {}
        align = _ALIGN.get(st.get("textAlign", "left"), WD_ALIGN_PARAGRAPH.LEFT)

        if btype == "divider":
            self._rule(sink, 0, 0, _hex(st.get("borderColor"), RULE))
            return
        if not val:
            return

        if btype == "badge":
            p = sink.par()
            p.alignment = align
            self._run(p, val.upper(), SIZE_SUB, True, BLACK)
        elif btype in ("headline", "label"):
            p = sink.par()
            p.alignment = align
            p.paragraph_format.line_spacing = 1.2
            self._run(p, val, SIZE_MAIN if btype == "headline" else SIZE_SUB, True, BLACK, st)
        elif btype == "byline":
            p = sink.par()
            p.alignment = align
            self._run(p, f"By {val}", SIZE_SUB, True, BLACK, st)
        elif btype == "meta":
            p = sink.par()
            p.alignment = align
            date = str(entry.get("event_date") or "").strip()
            self._run(p, val + (f" · {date}" if date else ""), SIZE_BODY, False, BLACK, st)
        elif btype == "text":
            p = sink.par()
            p.alignment = align
            try:
                p.paragraph_format.line_spacing = float(st.get("lineHeight") or 1.5)
            except ValueError:
                p.paragraph_format.line_spacing = 1.5
            self._run(p, val, SIZE_BODY, False, BLACK, st)
        elif btype == "stats":
            p = sink.par()
            p.alignment = align
            self._run(p, val, SIZE_SUB, True, BLACK)
            label = str(entry.get("badge_tag") or "").strip()
            if label and label != val:
                self._run(p, f"   {label}", SIZE_SUB, True, BLACK)
        elif btype == "link":
            p = sink.par()
            p.alignment = align
            self._link(p, val)
        elif btype == "image":
            cap = str(entry.get("photo_caption") or "").strip() if st.get("showCaption", True) else ""
            img_h = height_in - (CAPTION_PX / 96 if cap else 0) - 0.02
            src = self._resolve_image(val)
            if not src or img_h <= 0.2:
                return
            path = self._crop(src, width_in / img_h)
            p = sink.par()
            p.alignment = align if st.get("textAlign") in ("center", "right") else WD_ALIGN_PARAGRAPH.LEFT
            try:
                p.add_run().add_picture(path, width=Inches(width_in))
            except Exception:
                return
            if cap:
                pc = sink.par()
                pc.alignment = align if st.get("textAlign") in ("center", "right") else WD_ALIGN_PARAGRAPH.LEFT
                self._run(pc, cap, SIZE_CAPTION, False, GREY)

    # ---- inline pieces ---------------------------------------------------------
    def _link(self, p, url: str, size_pt: float = SIZE_BODY):
        """The address itself as a clickable, underlined, black link (no button)."""
        if not url.startswith(("http://", "https://")):
            self._run(p, url, size_pt, False, BLACK)
            return
        r_id = p.part.relate_to(url, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink", is_external=True)
        link = OxmlElement("w:hyperlink")
        link.set(qn("r:id"), r_id)
        run = OxmlElement("w:r")
        rPr = OxmlElement("w:rPr")
        for tag, attrs in (("w:color", {"w:val": BLACK}), ("w:sz", {"w:val": str(int(size_pt * 2))}), ("w:u", {"w:val": "single"})):
            el = OxmlElement(tag)
            for k, v in attrs.items():
                el.set(qn(k), v)
            rPr.append(el)
        run.append(rPr)
        t = OxmlElement("w:t")
        t.text = url
        run.append(t)
        link.append(run)
        p._p.append(link)

    # ---- images ----------------------------------------------------------------
    def _crop(self, path: str, ratio: float) -> str:
        """Centre-crop to the box the element covers on the canvas (the designer shows object-fit: cover)."""
        ratio = round(ratio, 3)
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
