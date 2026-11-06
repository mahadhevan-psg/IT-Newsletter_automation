"""Create one test login for every role, all with the same hardcoded password. FOR TESTING ONLY - never run on real data.

    python seed_test_logins.py

Works directly on the master database (database/master_system.db, or MASTER_DB_PATH), so the server need not be running.
Safe to run again: it resets these accounts to the passwords below. The real ADMIN account is left alone.
Sign in at the Portal with any staff ID, or at the Diary with a student roll number.
"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from backend.master.auth import hash_password
from database.master_db import db, init_master_db

PASSWORD = "Test@1234"

# emp_id, name, designation, roles, class the person is tutor of
STAFF = [
    ("ADMIN01", "Test Admin",             "Administrator",       [("ADMIN", None, None)],       None),
    ("HOD01",   "Test HoD",               "Professor & HoD",     [("HOD", None, None)],         None),
    ("PC01",    "Test PC (UG G1)",        "Associate Professor", [("PC", "UG", "G1")],          None),
    ("PC02",    "Test PC (UG G2)",        "Associate Professor", [("PC", "UG", "G2")],          None),
    ("PC03",    "Test PC (PG)",           "Associate Professor", [("PC", "PG", None)],          None),
    ("TUT01",   "Test Tutor (UG G2 Y1)",  "Assistant Professor", [],                            "UG-G2-1"),
    ("TUT02",   "Test Tutor (UG G2 Y2)",  "Assistant Professor", [],                            "UG-G2-2"),
    ("MULTI01", "Test Tutor + PC (UG G1)", "Professor",          [("PC", "UG", "G1")],          "UG-G1-1"),
    ("FAC01",   "Test Faculty",           "Assistant Professor", [],                            None),
]

# roll_no, name, programme, class code
STUDENTS = [
    ("22ITT01", "Test Student (UG G2 Y1)", "UG", "UG-G2-1"),
    ("22ITT02", "Test Student (UG G2 Y2)", "UG", "UG-G2-2"),
    ("22ITT03", "Test Student (UG G1 Y1)", "UG", "UG-G1-1"),
    ("23ITT04", "Test Student (PG Y1)",    "PG", "PG-1"),
]


def main():
    init_master_db()
    pw_hash = hash_password(PASSWORD)
    today = date.today().isoformat()
    with db() as conn:
        classes = {r["class_code"]: r["class_id"] for r in conn.execute("SELECT class_code, class_id FROM classes")}
        # A class is known by its tutor and semester, and its code follows the semester: find it by its tutor first
        tutor_of_code = {code: emp for emp, _, _, _, code in STAFF if code}

        def class_for(code):
            emp = tutor_of_code.get(code)
            row = conn.execute("SELECT class_id FROM classes WHERE tutor_id = ? AND status = 'Active'", (emp,)).fetchone() if emp else None
            return row[0] if row else classes[code]
        for emp, name, desig, roles, tutor_of in STAFF:
            conn.execute("INSERT INTO faculty (emp_id, full_name, email, designation, status) VALUES (?,?,?,?, 'Active') "
                         "ON CONFLICT(emp_id) DO UPDATE SET full_name = excluded.full_name, designation = excluded.designation, status = 'Active'",
                         (emp, name, f"{emp.lower()}@test.local", desig))
            conn.execute("DELETE FROM role_assignments WHERE emp_id = ?", (emp,))
            for role, prog, grp in roles:
                conn.execute("INSERT INTO role_assignments (emp_id, role, programme, grp) VALUES (?,?,?,?)", (emp, role, prog, grp))
            conn.execute("INSERT OR REPLACE INTO users (user_id, user_type, password_hash, must_change) VALUES (?, 'STAFF', ?, 0)", (emp, pw_hash))
            if tutor_of:
                cid = class_for(tutor_of)
                conn.execute("UPDATE classes SET tutor_id = ? WHERE class_id = ?", (emp, cid))
                if not conn.execute("SELECT 1 FROM class_tutor_history WHERE class_id = ? AND tutor_id = ? AND to_date IS NULL", (cid, emp)).fetchone():
                    conn.execute("UPDATE class_tutor_history SET to_date = ? WHERE class_id = ? AND to_date IS NULL", (today, cid))
                    conn.execute("INSERT INTO class_tutor_history (class_id, tutor_id, from_date) VALUES (?,?,?)", (cid, emp, today))
        for roll, name, prog, code in STUDENTS:
            conn.execute("INSERT INTO students (roll_no, full_name, programme, class_id, status) VALUES (?,?,?,?, 'Active') "
                         "ON CONFLICT(roll_no) DO UPDATE SET full_name = excluded.full_name, class_id = excluded.class_id, status = 'Active'",
                         (roll, name, prog, class_for(code)))
            if not conn.execute("SELECT 1 FROM student_class_history WHERE roll_no = ? AND class_id = ? AND to_date IS NULL", (roll, class_for(code))).fetchone():
                conn.execute("INSERT INTO student_class_history (roll_no, class_id, from_date, action, done_by) VALUES (?,?,?, 'Added', 'seed_test_logins')",
                             (roll, class_for(code), today))
            conn.execute("INSERT OR REPLACE INTO users (user_id, user_type, password_hash, must_change) VALUES (?, 'STUDENT', ?, 0)", (roll, pw_hash))

    print(f"Test logins (password for all: {PASSWORD})\n")
    print("PORTAL (staff)")
    for emp, name, _, roles, tutor_of in STAFF:
        what = [r[0] + (f" {r[1]}" if r[1] else "") + (f" {r[2]}" if r[2] else "") for r in roles]
        if tutor_of:
            what.insert(0, f"TUTOR {tutor_of}")
        print(f"  {emp:<9} {name:<26} {', '.join(what) or 'FACULTY only'}")
    print("\nDIARY (students)")
    for roll, name, _, code in STUDENTS:
        print(f"  {roll:<9} {name:<26} {code}")


if __name__ == "__main__":
    main()
