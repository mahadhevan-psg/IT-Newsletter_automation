"""Small parsing helpers shared by the importers (Excel reading, dates, numbers, 'ID - Name' lines)."""
import io
import re
from datetime import datetime
from typing import Any, Dict, List, Optional


def norm_header(s: Any) -> str:
    """'Roll Number / USN' and 'roll number  usn' are the same column."""
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()


def read_xlsx(content: bytes) -> List[Dict[str, str]]:
    """Rows of the first sheet as {header: text}. Every cell becomes text, like the newsletter importer does."""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    rows = wb.active.iter_rows(values_only=True)
    try:
        headers = [str(h).strip() if h is not None else "" for h in next(rows)]
    except StopIteration:
        return []
    out = []
    for row in rows:
        rec = {headers[i]: (str(v).strip() if v is not None else "") for i, v in enumerate(row) if i < len(headers) and headers[i]}
        if any(rec.values()):
            out.append(rec)
    return out


def clean_cell(v: str) -> str:
    return re.sub(r"[ T]00:00:00(\.0+)?$", "", str(v or "").strip())


_DATE_FORMATS = ["%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d %B %Y", "%d %b %Y",
                 "%B %d, %Y", "%b %d, %Y", "%d/%m/%Y %H:%M:%S", "%m/%d/%Y %H:%M:%S"]
_MONTH_FORMATS = ["%B %Y", "%b %Y", "%Y-%m"]


def parse_datetime(s: Any) -> Optional[datetime]:
    t = clean_cell(s) if not isinstance(s, datetime) else s.isoformat(sep=" ")
    if not t:
        return None
    t = re.sub(r"\.\d+$", "", t)
    for fmt in _DATE_FORMATS + _MONTH_FORMATS:
        try:
            return datetime.strptime(t, fmt)
        except ValueError:
            pass
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", t)
    return datetime(int(m[1]), int(m[2]), int(m[3])) if m else None


def parse_date(s: Any) -> Optional[str]:
    d = parse_datetime(s)
    return d.strftime("%Y-%m-%d") if d else None


def parse_num(s: Any) -> Optional[float]:
    """'₹15,00,000' -> 1500000, '12 lakhs' -> 1200000, '8.5 LPA' -> 8.5, 'NA' -> None."""
    t = str(s or "").lower().replace(",", "")
    m = re.search(r"-?\d+(\.\d+)?", t)
    if not m:
        return None
    n = float(m.group())
    if "crore" in t or re.search(r"\bcr\b", t):
        n *= 1e7
    elif "lakh" in t or "lac" in t:
        n *= 1e5
    return n


def parse_int(s: Any) -> Optional[int]:
    n = parse_num(s)
    return int(n) if n is not None else None


def truthy(s: Any) -> int:
    return 1 if re.match(r"\s*(yes|y|true|team|1)\b", str(s or ""), re.I) else 0


def ay_semester(d: datetime, year_no: int) -> int:
    """Semester a class was in on a date: Jun-Dec = odd semester, Jan-May = even."""
    return year_no * 2 - 1 if d.month >= 6 else year_no * 2


# "ID", "ID - Name" or "ID - Name - Role": students are now entered by roll number alone (names come from the college records)
LINE_RE = re.compile(r"^\s*([A-Za-z0-9]+)\s*(?:-\s*(.*?)(?:\s+-\s+(.+))?)?\s*$")


def parse_lines(text: str) -> List[Dict[str, str]]:
    """'ID - Name - Role' per line  ->  [{raw, id, name, extra}] (lines that do not fit still come back, with id '')."""
    out = []
    for line in re.split(r"\r?\n", str(text or "")):
        if not line.strip():
            continue
        m = LINE_RE.match(line)
        out.append({"raw": line.strip(), "id": m[1].upper() if m else "", "name": (m[2] or "").strip() if m else line.strip(), "extra": (m[3] or "").strip() if m else ""})
    return out


def person_name(ident: str, conn=None) -> Optional[str]:
    """Full name of a student (roll number) or faculty member (employee ID) from the master database, if known."""
    def look(c):
        for sql in ("SELECT full_name FROM students WHERE upper(roll_no) = upper(?)", "SELECT full_name FROM faculty WHERE upper(emp_id) = upper(?)"):
            row = c.execute(sql, (ident,)).fetchone()
            if row:
                return row[0]
        return None
    if conn is not None:
        return look(conn)
    try:
        from database.master_db import db
        with db() as c:
            return look(c)
    except Exception:
        return None


def names_only(value: str) -> str:
    """'21IT001', '21IT001 - Asha K' lines or a faculty-dropdown value -> plain names for the newsletter."""
    lines = parse_lines(value)
    if lines and all(l["id"] for l in lines):
        return ", ".join(l["name"] or person_name(l["id"]) or l["raw"] for l in lines)
    return value


def org_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(name or "").lower())


def make_xlsx(headers: List[str], example: Optional[List[str]] = None) -> bytes:
    """A one-sheet workbook with the header row (and one example row) for tutors to fill in."""
    import openpyxl
    from openpyxl.styles import Font
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    for c in ws[1]:
        c.font = Font(bold=True)
    if example:
        ws.append(example)
    for i, h in enumerate(headers, 1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = min(max(len(h) + 2, 14), 40)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# A student's class even after graduating: current class, else the last class they were in. Used to keep a
# tutor's view of their own placements after the students move on.
EFF_CLASS = ("COALESCE(s.class_id, (SELECT h.class_id FROM student_class_history h WHERE h.roll_no = s.roll_no "
             "AND h.class_id IS NOT NULL ORDER BY h.from_date DESC, h.id DESC LIMIT 1))")
