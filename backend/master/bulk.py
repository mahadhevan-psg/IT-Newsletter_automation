"""Bulk upload of the five faculty forms from Excel (the Admin). Placement data has its own upload (placements.py).

The workbook is made from the PUBLISHED form definitions, so it always asks what the entry screen asks: one sheet per category (the
student participation form, whose categories share their questions, has a single sheet with a category column). Every row is checked like
an entry typed in the portal and goes through the same approval step, recorded as approved by the Admin who uploaded it - so a wrong one
can be taken out again with Revoke on the Review & submissions tab. A row that is already in the records is skipped.
"""
import io
import re
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from backend.master import blocks, entry, ingest
from backend.master.auth import User
from backend.master.common import clean_cell, norm_header, parse_date
from backend.review import service as review

BY = "Entered by (Employee ID)"
ENTRY_DATE = "Entry date (this category asks for none)"
HELP_SHEET = "How to fill"
FLAT_SHEET = "Entries"
ATTACHMENTS = ("file", "photo")
MAX_ROWS = 2000
_NOT_IN_SHEET_NAMES = re.compile(r"[\[\]:*?/\\]")
_HEAD = PatternFill("solid", fgColor="1F4E78")
_REQUIRED = PatternFill("solid", fgColor="9C2B2B")
_WHITE = Font(bold=True, color="FFFFFF")


def _spec(form_id: str) -> Dict[str, Any]:
    spec = ingest.specs()["forms"].get(form_id)
    if not spec:
        raise HTTPException(404, "Unknown form")
    return spec


def _is_flat(spec: Dict[str, Any]) -> bool:
    """One set of questions for every category."""
    return all(not q.get("cats") for q in spec["questions"])


def _category_question(spec: Dict[str, Any]) -> Dict[str, Any]:
    return next(q for q in spec["questions"] if q.get("key") == "category" and not q.get("legacy"))


def _asked(spec: Dict[str, Any], category: str) -> List[Dict[str, Any]]:
    qs = [q for q in blocks.questions_for(spec, category, legacy=False) if entry._shown(q)]
    return sorted(qs, key=lambda q: entry.ZONE_ORDER.get(q.get("zone"), 1))


def _date_question(spec: Dict[str, Any], category: str) -> Optional[Dict[str, Any]]:
    key = spec.get("category_config", {}).get(category, {}).get("date_key") or spec.get("date_key")
    return next((q for q in _asked(spec, category) if q.get("key") == key and entry._widget(q) == "date"), None)


def _sheets(spec: Dict[str, Any]) -> List[Tuple[str, Optional[str]]]:
    """[(sheet name, category)]; Excel allows 31 characters and none of []:*?/\\ in a sheet's name."""
    if _is_flat(spec):
        return [(FLAT_SHEET, None)]
    return [(f"{n} {_NOT_IN_SHEET_NAMES.sub(' ', name)}"[:31].strip(), name) for n, name in enumerate(spec["categories"], 1)]


def _columns(spec: Dict[str, Any], category: Optional[str]) -> List[Tuple[str, Optional[Dict[str, Any]], bool]]:
    """[(heading, question or None, required)] of one sheet."""
    first = category or spec["categories"][0]
    cols: List[Tuple[str, Optional[Dict[str, Any]], bool]] = [(BY, None, True)]
    if category is None:
        cols.append((_category_question(spec)["q"], None, True))
    cols += [(q["q"], q, bool(q.get("req")) and entry._widget(q) not in ATTACHMENTS) for q in _asked(spec, first)]
    if not _date_question(spec, first):
        cols.append((ENTRY_DATE, None, False))
    return cols


def _what(q: Optional[Dict[str, Any]], heading: str, spec: Dict[str, Any]) -> str:
    if heading == BY:
        return "The faculty member this entry belongs to, e.g. EMP001"
    if heading == ENTRY_DATE:
        return "YYYY-MM-DD. Left empty, today is used."
    if q is None:
        return "One of: " + "; ".join(spec["categories"])
    kind = entry._widget(q)
    text = {"date": "A date, YYYY-MM-DD", "number": "A number", "url": "A link starting with http:// or https://",
            "roster_roll": "Roll numbers, separated by commas (the first is the lead)", "roster_any": "One person per line or separated by semicolons: ID - Name (EXT for someone outside)",
            "faculty": "Employee ID", "file": "Files cannot go in Excel: paste a link to the document, or leave empty",
            "photo": "Photos cannot go in Excel: paste a link to the photo, or leave empty"}.get(kind, "Text")
    if kind in ("choice", "list"):
        text = "One of: " + "; ".join(q.get("choices") or [])
    if kind == "multi":
        text = "One or more of these, separated by semicolons: " + "; ".join(q.get("choices") or [])
    return text + (f". {q['help']}" if q.get("help") else "")


def template(form_id: str) -> bytes:
    spec = _spec(form_id)
    wb = Workbook()
    help_sheet = wb.active
    help_sheet.title = HELP_SHEET
    help_sheet.append([spec["title"]])
    help_sheet["A1"].font = Font(bold=True, size=14)
    for note in ("Fill one row per entry on the sheet of its category. Do not rename the sheets or the column headings; leave unused sheets empty.",
                 "Red headings must be filled in. Uploaded entries are saved as approved at once. A row that is already in the records is skipped."):
        help_sheet.append([note])
    help_sheet.append([])
    help_sheet.append(["Sheet", "Column", "Needed?", "What to enter"])
    for cell in help_sheet[help_sheet.max_row]:
        cell.font, cell.fill = _WHITE, _HEAD
    for sheet_name, category in _sheets(spec):
        ws = wb.create_sheet(sheet_name)
        for i, (heading, q, required) in enumerate(_columns(spec, category), 1):
            cell = ws.cell(1, i, heading)
            cell.font, cell.fill, cell.alignment = _WHITE, _REQUIRED if required else _HEAD, Alignment(vertical="center", wrap_text=True)
            letter = get_column_letter(i)
            ws.column_dimensions[letter].width = min(max(len(heading) + 4, 18), 48)
            choices = spec["categories"] if (q is None and category is None and heading != BY and heading != ENTRY_DATE) else (q or {}).get("choices")
            listed = ",".join(choices or [])
            if choices and (q is None or entry._widget(q) in ("choice", "list")) and len(listed) <= 250 and not any("," in c for c in choices):
                rule = DataValidation(type="list", formula1=f'"{listed}"', allow_blank=True)
                ws.add_data_validation(rule)
                rule.add(f"{letter}2:{letter}{MAX_ROWS + 1}")
            help_sheet.append([sheet_name if category is None else f"{sheet_name}  ({category})", heading, "Yes" if required else "No", _what(q, heading, spec)])
        ws.freeze_panes = "A2"
    for letter, width in zip("ABCD", (44, 48, 10, 90)):
        help_sheet.column_dimensions[letter].width = width
    for line in help_sheet.iter_rows(min_row=5):
        for cell in line:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _value(q: Dict[str, Any], text: str) -> str:
    """One cell as the answer the entry screen would have sent; raises HTTPException naming the field."""
    kind = entry._widget(q)
    if kind in ATTACHMENTS:
        if text and not text.lower().startswith(("http://", "https://")):
            raise HTTPException(400, f"'{q['q']}': paste a link (http...) or leave it empty")
        return text
    if kind == "date" and text:
        day = parse_date(text)
        if not day:
            raise HTTPException(400, f"'{q['q']}': enter a date like 2026-03-31")
        return day
    choices = q.get("choices") or []
    same = {c.strip().lower(): c for c in choices}
    if kind in ("choice", "list") and text:
        text = same.get(text.lower(), text)
    if kind == "multi" and text:
        text = [same.get(p.strip().lower(), p.strip()) for p in re.split(r"[;\n]|,\s*", text) if p.strip()]
    if kind == "roster_roll" and text:
        text = "\n".join(p.strip() for p in re.split(r"[;,\n]", text) if p.strip())
    return entry._clean(q, text)


def _flat_row(conn, spec: Dict[str, Any], category: str, said: Dict[str, str]) -> Tuple[Dict[str, str], str]:
    """(the stored row, the faculty member's ID) for one Excel row; said = {normalised heading: text}."""
    cell = lambda heading: said.get(norm_header(heading), "")
    who = ingest.resolve_faculty(conn, cell(BY))
    if not who:
        raise HTTPException(400, f"'{BY}': " + (f"no faculty member '{cell(BY)}'" if cell(BY) else "is empty"))
    me = conn.execute("SELECT emp_id, full_name, email, designation FROM faculty WHERE emp_id = ?", (who,)).fetchone()
    row: Dict[str, str] = {"Email Address": me["email"] or "", _category_question(spec)["q"]: category}
    missing = []
    for q in blocks.questions_for(spec, category, legacy=False):
        key = q.get("key")
        if q.get("submitter"):
            row[q["q"]] = f"{me['emp_id']} - {me['full_name']}"
        elif q.get("auto"):
            row[q["q"]] = me[q["auto"]] or ""
        elif key in entry.AUTO_YES:
            row[q["q"]] = "Yes"
        elif key == "is_landmark":
            row[q["q"]] = (q.get("choices") or ["No (Standard Entry)"])[0]
        elif entry._shown(q):
            value = _value(q, cell(q["q"]))
            if value:
                row[q["q"]] = value
            elif q.get("req") and entry._widget(q) not in ATTACHMENTS:
                missing.append(q["q"])
    if missing:
        raise HTTPException(400, "Please fill in: " + ", ".join(missing))
    asked = {q.get("key"): row.get(q["q"]) for q in _asked(spec, category)}
    if asked.get("agreement_effective") and asked.get("agreement_expiry") and asked["agreement_expiry"] < asked["agreement_effective"]:
        raise HTTPException(400, "The MoU expiry date is before its start date")
    # the entry's own day stands for "when it was entered", so the same file uploaded again is recognised
    date_q = _date_question(spec, category)
    given = cell(ENTRY_DATE)
    if given and not parse_date(given):
        raise HTTPException(400, f"'{ENTRY_DATE}': enter a date like 2026-03-31")
    day = (row.get(date_q["q"]) if date_q else None) or parse_date(given)
    if day:
        row = {"Timestamp": f"{parse_date(day)} 00:00:00", **row}
    return row, who


def upload(conn, user: User, form_id: str, content: bytes) -> Dict[str, Any]:
    spec = _spec(form_id)
    try:
        wb = load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    except Exception:
        raise HTTPException(400, "That file could not be read as an Excel workbook")
    sheets = {name.lower(): category for name, category in _sheets(spec)}
    if not any(ws.title.lower() in sheets for ws in wb.worksheets):
        raise HTTPException(400, f"This workbook has none of the sheets of '{spec['title']}'. Download the template from this card and fill that in.")
    total = added = duplicates = 0
    problems: List[Dict[str, Any]] = []
    canonical = {c.strip().lower(): c for c in spec["categories"]}
    for ws in wb.worksheets:
        if ws.title.lower() not in sheets:
            continue
        lines = ws.iter_rows(values_only=True)
        heads = [norm_header(str(h)) if h is not None else "" for h in next(lines, ())]
        for number, values in enumerate(lines, 2):
            said = {h: clean_cell(str(v)) for h, v in zip(heads, values) if h and v is not None and str(v).strip()}
            if not said:
                continue
            total += 1
            where = f"{ws.title} · row {number}"
            if total > MAX_ROWS:
                raise HTTPException(413, f"One upload can hold at most {MAX_ROWS} rows")
            conn.execute("SAVEPOINT bulk_row")
            try:
                category = sheets[ws.title.lower()]
                if category is None:
                    typed = said.get(norm_header(_category_question(spec)["q"]), "")
                    category = canonical.get(typed.lower())
                    if not category:
                        raise HTTPException(400, f"Unknown category '{typed}'" if typed else f"'{_category_question(spec)['q']}' is empty")
                row, who = _flat_row(conn, spec, category, said)
                if conn.execute("SELECT 1 FROM form_submissions WHERE source_row_hash = ?", (ingest.row_hash(form_id, row),)).fetchone():
                    duplicates += 1
                else:
                    notes = ingest.preview_row(conn, form_id, row)["warnings"]
                    item = review.stage_app_entry(conn, form_id, row, user)
                    conn.execute("UPDATE staged_items SET submitter_emp_id = ? WHERE item_id = ?", (who, item))
                    review.event(conn, item, "submitted", user.id, f"Bulk upload from Excel ({where})")
                    review.approve(conn, user, item, note="Bulk upload")
                    added += 1
                    if notes:
                        problems.append({"row": where, "messages": ["Added, but check: " + "; ".join(notes)]})
                conn.execute("RELEASE bulk_row")
            except Exception as e:                                    # one bad row never blocks the rest of the file
                conn.execute("ROLLBACK TO bulk_row")
                conn.execute("RELEASE bulk_row")
                problems.append({"row": where, "messages": [str(getattr(e, "detail", e))]})
    return {"rows": total, "added": added, "duplicates_skipped": duplicates, "needs_attention": problems}
