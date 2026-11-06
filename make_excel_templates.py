"""Write the upload templates (students, faculty) to excel_templates/.

    python make_excel_templates.py

The portal serves the same files from its "Download Excel template" links. The six Google Forms response sheets and the
placement sheet come from the forms themselves, so they are not generated here.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from backend.master import excel_templates as t

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "excel_templates")


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, data in (("1_Students_Upload.xlsx", t.students_workbook()), ("2_Faculty_Upload.xlsx", t.faculty_workbook())):
        path = os.path.join(OUT, name)
        with open(path, "wb") as f:
            f.write(data)
        print("wrote", path)


if __name__ == "__main__":
    main()
