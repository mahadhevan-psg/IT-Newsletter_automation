"""Connection + initialisation for the master database (students, faculty, submissions, placements)."""
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import date

HERE = os.path.dirname(__file__)
SCHEMA_PATH = os.path.join(HERE, "master_schema.sql")


def db_path() -> str:
    # read on every call so tests can point at a temporary file
    return os.environ.get("MASTER_DB_PATH") or os.path.join(HERE, "master_system.db")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")      # readers never block the writer
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


@contextmanager
def db():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def ay_for(d: date) -> str:
    """Academic year runs June-May: 2026-09-01 -> '2026-27', 2027-02-01 -> '2026-27'."""
    start = d.year if d.month >= 6 else d.year - 1
    return f"{start}-{(start + 1) % 100:02d}"


def ensure_ay(conn, ay_id: str) -> str:
    start = int(ay_id[:4])
    conn.execute(
        "INSERT OR IGNORE INTO academic_years (ay_id, start_date, end_date) VALUES (?, ?, ?)",
        (ay_id, f"{start}-06-01", f"{start + 1}-05-31"),
    )
    return ay_id


def audit(conn, actor, action, entity, key=None, details=None):
    conn.execute("INSERT INTO master_audit_log (actor, action, entity, entity_key, details) VALUES (?,?,?,?,?)",
                 (actor, action, entity, key, details))


# Student columns that used to be stored here; the college main database owns them now.
DROPPED_STUDENT_COLUMNS = ("email", "phone", "gender", "batch_start_year", "residence_type", "cgpa")


def drop_student_columns(conn):
    """Bring a database created before this change in line with the slimmer students table (idempotent)."""
    have = {r["name"] for r in conn.execute("PRAGMA table_info(students)")}
    for col in DROPPED_STUDENT_COLUMNS:
        if col in have:
            conn.execute(f"ALTER TABLE students DROP COLUMN {col}")


def migrate_classes(conn):
    """Classes are cohorts now, not ten fixed year slots: drop the one-class-per-year rule and add a status (idempotent)."""
    conn.execute("DROP INDEX IF EXISTS ux_class_slot")
    have = {r["name"] for r in conn.execute("PRAGMA table_info(classes)")}
    if "status" not in have:
        conn.execute("ALTER TABLE classes ADD COLUMN status TEXT NOT NULL DEFAULT 'Active' CHECK (status IN ('Active','Completed'))")


def repair_class_years(conn):
    """Every class's year and code must follow its semester (earlier versions let them drift apart)."""
    from backend.master import people
    for c in conn.execute("SELECT class_id, programme, grp, current_semester, year_no, class_code FROM classes ORDER BY class_id").fetchall():
        year = people.year_of(c["current_semester"])
        if year != c["year_no"]:
            code = people.next_class_code(conn, c["programme"], c["grp"], c["current_semester"], c["class_id"])
            conn.execute("UPDATE classes SET year_no = ?, class_code = ? WHERE class_id = ?", (year, code, c["class_id"]))


def add_entry_kind(conn):
    """Student submissions can now be plain participation: add the column to a database created before that."""
    have = {r["name"] for r in conn.execute("PRAGMA table_info(student_achievements)")}
    if have and "entry_kind" not in have:
        conn.execute("ALTER TABLE student_achievements ADD COLUMN entry_kind TEXT NOT NULL DEFAULT 'ACHIEVEMENT' "
                     "CHECK (entry_kind IN ('ACHIEVEMENT','PARTICIPATION'))")


def repair_publish_permission(conn):
    """Rows imported before 'unanswered' was told apart from 'No' carry 0 although the question was never answered."""
    conn.execute("UPDATE form_submissions SET publish_permission = NULL WHERE publish_permission = 0 AND NOT EXISTS "
                 "(SELECT 1 FROM json_each(raw_json) WHERE key LIKE '%Permission to Publish%' AND trim(ifnull(value, '')) <> '')")


def init_master_db():
    """Create tables, the 10 fixed classes and the first admin account (idempotent)."""
    from backend.master.auth import hash_password
    with db() as conn:
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            conn.executescript(f.read())
        drop_student_columns(conn)
        migrate_classes(conn)
        repair_class_years(conn)
        add_entry_kind(conn)
        repair_publish_permission(conn)
        cur_ay = ensure_ay(conn, ay_for(date.today()))
        conn.execute("UPDATE academic_years SET is_current = (ay_id = ?)", (cur_ay,))
        if conn.execute("SELECT COUNT(*) FROM classes").fetchone()[0] == 0:
            rows = [("UG", g, y) for g in ("G1", "G2") for y in (1, 2, 3, 4)] + [("PG", None, y) for y in (1, 2)]
            for prog, grp, year in rows:
                code = f"UG-{grp}-{year}" if prog == "UG" else f"PG-{year}"
                conn.execute(
                    "INSERT INTO classes (class_code, programme, grp, year_no, current_semester, ay_id) VALUES (?,?,?,?,?,?)",
                    (code, prog, grp, year, year * 2 - 1, cur_ay))
        if conn.execute("SELECT COUNT(*) FROM role_assignments WHERE role='ADMIN'").fetchone()[0] == 0:
            pw = os.environ.get("MASTER_ADMIN_PASSWORD") or secrets.token_urlsafe(9)
            conn.execute("INSERT OR IGNORE INTO faculty (emp_id, full_name, email, designation) VALUES ('ADMIN','System Administrator','admin@localhost','Administrator')")
            conn.execute("INSERT INTO role_assignments (emp_id, role) VALUES ('ADMIN','ADMIN')")
            conn.execute("INSERT OR REPLACE INTO users (user_id, user_type, password_hash, must_change) VALUES ('ADMIN','STAFF',?,1)",
                         (hash_password(pw),))
            note = os.path.join(os.path.dirname(os.path.abspath(db_path())), "INITIAL_ADMIN_PASSWORD.txt")
            with open(note, "w", encoding="utf-8") as f:
                f.write(f"Portal login  ID: ADMIN   Password: {pw}\nChange it after the first login, then delete this file.\n")
            print(f"[master-db] First admin created. ID=ADMIN, password saved in {note}")
