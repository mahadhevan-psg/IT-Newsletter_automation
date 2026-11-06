"""
The Excel sheets people fill in and upload to the IT Portal (apart from the Google Forms response sheets):

  Students  - tutors / Admin: who is in the class being uploaded (roll number and name - nothing else is kept here)
  Faculty   - Admin only: employee ID, name, email and a few details; each new person gets a temporary password

Each workbook has a "Data" sheet (header row only, ready to fill) and a "How to fill" sheet. The portal reads the first
sheet, so the instructions are never imported. The same builders serve the portal's "Download Excel template" links and
make_excel_templates.py (which writes the files to excel_templates/).
"""
import io
from typing import List, Sequence

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

STUDENT_HEADERS = ["Roll No", "Full Name"]
STUDENT_EXAMPLE = ["21IT001", "Asha K"]
STUDENT_HELP = [
    ("Roll No", "Required", "The student's roll number, letters and digits only. Stored in capitals; each roll number appears once.", "21IT001"),
    ("Full Name", "Required", "Name as in the college records.", "Asha K"),
]
STUDENT_NOTES = [
    "Only these two columns are kept. Marks, attendance, gender, residence and contact details stay in the college main database.",
    "The class is not in the sheet: a tutor's own class is used automatically; the Admin picks the class in the upload box on the portal.",
    "A roll number that already exists is updated; if it was in another class it is moved to the class you upload for.",
    "A tutor can only upload students of their own class; the Admin can upload for any class.",
    "Save as .xlsx (in Google Sheets: File > Download > Microsoft Excel). Delete nothing from the header row.",
]

FACULTY_HEADERS = ["Employee ID", "Full Name", "Email", "Phone", "Designation", "Qualification", "Date of Joining"]
FACULTY_EXAMPLE = ["EMP012", "Dr. A. Kumar", "kumar@example.edu", "9876543210", "Associate Professor", "Ph.D", "2015-06-01"]
FACULTY_HELP = [
    ("Employee ID", "Required", "Unique employee ID; this is the login ID. Stored in capitals.", "EMP012"),
    ("Full Name", "Required", "Name as it should appear in forms and the newsletter.", "Dr. A. Kumar"),
    ("Email", "Required", "Unique. Used to match a form submission to the right person.", "kumar@example.edu"),
    ("Phone", "Optional", "", "9876543210"),
    ("Designation", "Optional", "e.g. Professor, Associate Professor, Assistant Professor.", "Associate Professor"),
    ("Qualification", "Optional", "", "Ph.D"),
    ("Date of Joining", "Optional", "Format YYYY-MM-DD.", "2015-06-01"),
]
FACULTY_NOTES = [
    "Admin only. Roles (HoD, programme coordinator, tutor) are set afterwards in the portal, not in this sheet.",
    "A new employee ID gets a temporary password, shown once after the upload (download it as CSV and share it privately).",
    "An employee ID that already exists is updated; nothing is deleted if a person is missing from the sheet.",
    "Save as .xlsx (in Google Sheets: File > Download > Microsoft Excel). Delete nothing from the header row.",
]

_HEAD_FILL = PatternFill("solid", fgColor="1F4E78")
_HEAD_FONT = Font(bold=True, color="FFFFFF")


def _book(title: str, headers: Sequence[str], help_rows, notes: Sequence[str], example: Sequence[str]) -> Workbook:
    wb = Workbook()
    ws = wb.active
    ws.title = "Data"
    ws.append(list(headers))
    for i, h in enumerate(headers, 1):
        c = ws.cell(1, i)
        c.font, c.fill, c.alignment = _HEAD_FONT, _HEAD_FILL, Alignment(vertical="center")
        ws.column_dimensions[c.column_letter].width = max(len(h) + 6, 18)
    ws.freeze_panes = "A2"

    how = wb.create_sheet("How to fill")
    how.append([title])
    how["A1"].font = Font(bold=True, size=14)
    how.append([])
    how.append(["Column", "Needed?", "What to enter", "Example"])
    for c in how[3]:
        c.font, c.fill = _HEAD_FONT, _HEAD_FILL
    for row in help_rows:
        how.append(list(row))
    how.append([])
    how.append(["Example row"] + list(example))
    how.cell(how.max_row, 1).font = Font(bold=True)
    how.append([])
    for n in notes:
        how.append(["•  " + n])
    for col, width in zip("ABCD", (18, 12, 70, 24)):
        how.column_dimensions[col].width = width
    for row in how.iter_rows(min_row=4):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    return wb


def _bytes(wb: Workbook) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def students_workbook() -> bytes:
    return _bytes(_book("Students upload", STUDENT_HEADERS, STUDENT_HELP, STUDENT_NOTES, STUDENT_EXAMPLE))


def faculty_workbook() -> bytes:
    return _bytes(_book("Faculty upload (Admin only)", FACULTY_HEADERS, FACULTY_HELP, FACULTY_NOTES, FACULTY_EXAMPLE))
