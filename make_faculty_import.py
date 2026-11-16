"""Builds excel_templates/IT_Faculty_Import.xlsx: the department's faculty, in the format of the Admin's Faculty upload (Data upload tab).
E-mail addresses were not on the source list, so each person gets a clearly fake placeholder (<id>@pending.invalid) until the real one is known:
upload this file again with the real e-mail in the Email column (same Employee ID) and only that detail changes; the login and password stay."""
import openpyxl

SG, SRG = "Assistant Professor (Sl. Gr.)", "Assistant Professor (Sr. Gr.)"
AP, ASSOC, PROF = "Assistant Professor", "Associate Professor", "Professor"
FACULTY = [
    ("C1940", "Dr. B. Vinoth Kumar", "Professor & Head"), ("C6608", "Dr. M. L. Valarmathi", PROF), ("C1954", "Dr. D. Karthika Renuka", PROF),
    ("C5213", "Dr. K. Anitha Kumari", PROF), ("C3043", "Dr. S. Sarathambekai", ASSOC), ("C5056", "Dr. R. Rekha", ASSOC),
    ("C5243", "Dr. R. Senthil Prabha", ASSOC), ("C5073", "Dr. B. Sangeetha", ASSOC), ("C3538", "Dr. T. Vairam", SG),
    ("C5507", "Dr. N. Hema Priya", SG), ("C5506", "Ms. S. Shymala Gowri", SG), ("C5517", "Ms. R. Padmashani", SG),
    ("C5251", "Ms. K. P. Thamilselvi", SRG), ("C6066", "Dr. D. Dharani", SRG), ("C6149", "Dr. S. Priya", SRG),
    ("C6419", "Ms. P. Shruti", AP), ("C6473", "Ms. E. Ramakalaivani", AP), ("C6543", "Ms. N. Deepika", AP),
    ("C6644", "Ms. N. Nirmala Devi", AP), ("C6671", "Ms. R. Logeswari Saranya", AP), ("C6676", "Ms. G. Suguna", AP),
    ("C6681", "Ms. A. Reveetha", AP), ("C6682", "Mr. N. Madesh", AP), ("C6683", "Mr. M. Pari", AP),
    ("C6684", "Mr. A. Mukilan", AP), ("C6685", "Ms. A. S. Rakseda Keerthi", AP), ("C6687", "Ms. A. Thanusavarthini", AP),
]


def build(path="excel_templates/IT_Faculty_Import.xlsx"):
    assert len({f[0] for f in FACULTY}) == len(FACULTY) == 27
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Faculty"
    ws.append(["Employee ID", "Full Name", "Email", "Phone", "Designation", "Qualification", "Date of Joining"])
    for emp, name, desig in FACULTY:
        ws.append([emp, name, f"{emp.lower()}@pending.invalid", None, desig, None, None])
    for col, w in zip("ABCDEFG", (14, 30, 30, 14, 32, 16, 16)):
        ws.column_dimensions[col].width = w
    wb.save(path)
    return path


if __name__ == "__main__":
    print(build())
