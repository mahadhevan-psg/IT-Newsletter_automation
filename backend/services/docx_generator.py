"""
Word output, driven entirely by the layout chosen in the Layout designer.

A layout is a 12-column grid: every element has a position (x, y) and size (w, h) in grid
cells, a link to a form column, and its own styling. Each entry becomes one borderless table
with 12 columns, and every element is a merged cell covering the same cells it covers on the
designer's canvas, so what is arranged on the canvas is what lands on the page.

There is no built-in design: no cover template, stats card, banners or card styling.
"""
import os
import re
import hashlib
import urllib.request
from typing import List, Dict, Any, Optional

from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ROW_HEIGHT_RULE, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import parse_xml, OxmlElement
from docx.oxml.ns import nsdecls, qn
from PIL import Image

try:
    from database.db_manager import get_raw_response
except Exception:   # the generator can be used without a database
    get_raw_response = None

# ---------------------------------------------------------------- palette (same values as the designer's CSS)
NAVY, AMBER, SLATE, GREEN = "1F4E78", "C65911", "5A6B7C", "15803D"
BODY, BYLINE, META, CAPTION = "334155", "475569", "64748B", "64748B"
RULE, CAPTION_BG, STAT_BG = "D9DEE4", "F8FAFC", "F8FAFC"
BADGE_FILL = {"navy": NAVY, "amber": AMBER, "slate": SLATE, "green": GREEN}
BUTTON_FILL = {"solid": NAVY, "accent": AMBER}
ASPECT = {"16:9": 16 / 9, "4:3": 4 / 3, "1:1": 1.0}

COLS = 12
ROW_PX = 28                            # height of one grid row in the designer (css px)
CANVAS_PX = 600                        # width of the designer page content (css px)
CONTENT_WIDTH_IN = 8.27 - 2.0          # A4 minus 1" margins
CELL_PAD_IN = 0.04
CAPTION_PX = 22
FONT = "Calibri"

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
        blocks = ensure_grid(layout)
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
        _p_border(p, f'<w:pBdr {nsdecls("w")}>'
                     f'<w:top w:val="single" w:sz="36" w:space="6" w:color="{NAVY}"/>'
                     f'<w:bottom w:val="single" w:sz="12" w:space="4" w:color="{NAVY}"/></w:pBdr>')
        left = "IT CHRONICLES" + (f" · {section_name.upper()}" if section_name else "")
        right = f"VOL. {issue['volume']} · ISSUE {issue['issue']}" if issue and issue.get("volume") else ""
        r = p.add_run(left)
        r.font.size, r.font.bold, r.font.color.rgb = Pt(8.5), True, RGBColor.from_string(NAVY)
        sp = OxmlElement("w:spacing")
        sp.set(qn("w:val"), "30")
        r._element.get_or_add_rPr().insert_element_before(sp, *_RPR_AFTER_SPACING)
        if right:
            r2 = p.add_run("\t" + right)
            r2.font.size, r2.font.bold, r2.font.color.rgb = Pt(8.5), True, RGBColor.from_string(META)

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

    def _fill_cell(self, cell, entry: Dict[str, Any], blk: Dict[str, Any], val: str):
        st = blk.get("style") or {}
        tcPr = cell._element.get_or_add_tcPr()
        if blk.get("type") == "stats":
            tcPr.insert_element_before(parse_xml(
                f'<w:tcBorders {nsdecls("w")}><w:left w:val="single" w:sz="24" w:space="0" w:color="{AMBER}"/></w:tcBorders>'), *_TCPR_AFTER_BORDERS[:0], *(("w:shd",) + _TCPR_AFTER_SHD))
            tcPr.insert_element_before(parse_xml(f'<w:shd {nsdecls("w")} w:val="clear" w:color="auto" w:fill="{STAT_BG}"/>'), *_TCPR_AFTER_SHD)
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
        """Add a run; the layout's own font size / weight / colour win over the defaults."""
        st = style or {}
        r = p.add_run(text)
        r.font.size = Pt(_pt(st.get("fontSize"), size_pt) if st.get("fontSize") else size_pt)
        weight = str(st.get("fontWeight") or "")
        r.font.bold = (weight == "bold" or (weight.isdigit() and int(weight) >= 600)) if weight else bold
        r.font.color.rgb = RGBColor.from_string(_hex(st.get("textColor")) or color)
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
            fill = _hex(st.get("bgColor")) or BADGE_FILL.get(st.get("badgeColor", "navy"), NAVY)
            r = self._run(p, f"  {val.upper()}  ", 8.25, True, "FFFFFF", {"textColor": st.get("textColor")})
            self._shade(r, fill)
        elif btype in ("headline", "label"):
            p = sink.par()
            p.alignment = align
            p.paragraph_format.line_spacing = 1.2
            self._run(p, val, _px(23) if btype == "headline" else _px(14), True, NAVY, st)
        elif btype == "byline":
            p = sink.par()
            p.alignment = align
            self._run(p, f"By {val}", _px(14), True, BYLINE, st)
        elif btype == "meta":
            p = sink.par()
            p.alignment = align
            date = str(entry.get("event_date") or "").strip()
            self._run(p, val + (f" · {date}" if date else ""), _px(13), False, META, st)
        elif btype == "text":
            p = sink.par()
            p.alignment = align
            try:
                p.paragraph_format.line_spacing = float(st.get("lineHeight") or 1.5)
            except ValueError:
                p.paragraph_format.line_spacing = 1.5
            self._run(p, val, _px(14), False, BODY, st)
        elif btype == "stats":
            p = sink.par()
            p.alignment = align
            self._run(p, val, _px(24), True, AMBER)
            label = str(entry.get("badge_tag") or "").strip()
            if label and label != val:
                self._run(p, f"   {label}", _px(13), True, BYLINE)
        elif btype == "link":
            p = sink.par()
            p.alignment = align
            self._button(p, val, blk.get("linkText") or "View details", st)
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
                _p_shade(pc, CAPTION_BG)
                self._run(pc, f" {cap}", _px(12), False, CAPTION, italic=True)

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
