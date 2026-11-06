"""Passwords, signed session tokens, and role / class-scope resolution for the portal and the student diary."""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass, field
from typing import Optional, Set

from fastapi import Depends, Header, HTTPException

from backend.demo.mode import enabled as demo_enabled
from database.master_db import db, HERE

TOKEN_TTL = 8 * 3600
ITERATIONS = 200_000
_fails = {}          # id -> (count, locked_until)  in-memory brute-force guard


def hash_password(pw: str) -> str:
    salt = secrets.token_hex(8)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), ITERATIONS).hex()
    return f"pbkdf2${ITERATIONS}${salt}${dk}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, iters, salt, dk = stored.split("$")
        calc = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), int(iters)).hex()
        return hmac.compare_digest(calc, dk)
    except Exception:
        return False


def _secret() -> bytes:
    env = os.environ.get("MASTER_SECRET")
    if env:
        return env.encode()
    path = os.path.join(HERE, ".master_secret")
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write(secrets.token_hex(32))
    with open(path) as f:
        return f.read().strip().encode()


def make_token(sub: str, typ: str) -> str:
    body = base64.urlsafe_b64encode(json.dumps({"sub": sub, "typ": typ, "exp": int(time.time()) + TOKEN_TTL}).encode()).decode()
    sig = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def parse_token(token: str) -> dict:
    try:
        body, sig = token.split(".")
        good = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, good):
            raise ValueError
        data = json.loads(base64.urlsafe_b64decode(body))
        if data["exp"] < time.time():
            raise ValueError
        return data
    except Exception:
        raise HTTPException(401, "Session expired - please sign in again")


@dataclass
class User:
    id: str
    name: str
    kind: str                                   # STAFF | STUDENT
    roles: Set[str] = field(default_factory=set)
    all_access: bool = False                    # Admin / HoD: every student and faculty
    class_ids: Set[int] = field(default_factory=set)   # classes this person may see (tutor + PC scope)
    tutor_class_ids: Set[int] = field(default_factory=set)
    must_change: bool = False
    tours_seen: Set[str] = field(default_factory=set)

    @property
    def is_admin(self):
        return "ADMIN" in self.roles

    def sees_class(self, class_id) -> bool:
        return self.all_access or class_id in self.class_ids

    def can_edit_class(self, class_id) -> bool:
        return self.is_admin or class_id in self.tutor_class_ids

    def public(self):
        return {"id": self.id, "name": self.name, "kind": self.kind, "roles": sorted(self.roles), "all_access": self.all_access,
                "class_ids": sorted(self.class_ids), "tutor_class_ids": sorted(self.tutor_class_ids), "must_change": self.must_change,
                "tours_seen": sorted(self.tours_seen)}


def _load_staff(conn, emp_id: str) -> Optional[User]:
    f = conn.execute("SELECT emp_id, full_name FROM faculty WHERE emp_id = ? AND status != 'Relieved'", (emp_id,)).fetchone()
    if not f:
        return None
    u = User(f["emp_id"], f["full_name"], "STAFF")
    tutor = [r[0] for r in conn.execute("SELECT class_id FROM classes WHERE tutor_id = ?", (emp_id,))]
    if tutor:
        u.roles.add("TUTOR")
        u.tutor_class_ids, u.class_ids = set(tutor), set(tutor)
    u.roles.add("FACULTY")
    for r in conn.execute("SELECT role, programme, grp FROM role_assignments WHERE emp_id = ?", (emp_id,)):
        u.roles.add(r["role"])
        if r["role"] == "PC":
            # A coordinator sees the whole programme: every class of UG (both groups, G1 and G2) or of PG.
            # The group on the role is only a label; the Students page lets them filter Both / G1 / G2.
            u.class_ids |= {x[0] for x in conn.execute("SELECT class_id FROM classes WHERE programme = ?", (r["programme"],))}
    u.all_access = bool(u.roles & {"ADMIN", "HOD"})
    return u


def load_user(conn, user_id: str, kind: str) -> Optional[User]:
    if kind == "STAFF":
        return _load_staff(conn, user_id)
    s = conn.execute("SELECT roll_no, full_name FROM students WHERE roll_no = ? AND status = 'Active'", (user_id,)).fetchone()
    return User(s["roll_no"], s["full_name"], "STUDENT", {"STUDENT"}) if s else None


def login(user_id: str, password: str) -> dict:
    uid = (user_id or "").strip()
    count, until = _fails.get(uid.upper(), (0, 0))
    if until > time.time():
        raise HTTPException(429, "Too many failed attempts. Try again in a few minutes.")
    with db() as conn:
        staff = conn.execute("SELECT emp_id FROM faculty WHERE upper(emp_id) = upper(?)", (uid,)).fetchone()
        stu = None if staff else conn.execute("SELECT roll_no FROM students WHERE upper(roll_no) = upper(?)", (uid,)).fetchone()
        kind, key = ("STAFF", staff["emp_id"]) if staff else ("STUDENT", stu["roll_no"]) if stu else (None, None)
        ok = False
        if kind:
            row = conn.execute("SELECT password_hash FROM users WHERE user_id = ?", (key,)).fetchone()
            if row:
                ok = verify_password(password or "", row["password_hash"])
            elif kind == "STUDENT" and (password or "").upper() == key.upper():
                # first sign-in: a student's initial password is their roll number; they must change it
                conn.execute("INSERT INTO users (user_id, user_type, password_hash, must_change) VALUES (?, 'STUDENT', ?, 1)",
                             (key, hash_password(key)))
                ok = True
        user = load_user(conn, key, kind) if ok else None
        if not user:
            n = count + 1
            _fails[uid.upper()] = (n, time.time() + 300 if n >= 5 else 0)
            raise HTTPException(401, "Wrong ID or password")
        _fails.pop(uid.upper(), None)
        conn.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE user_id = ?", (key,))
        row = conn.execute("SELECT must_change, tours_seen FROM users WHERE user_id = ?", (key,)).fetchone()
        user.must_change, user.tours_seen = bool(row[0]), _split(row[1])
    return {"token": make_token(key, kind), "user": user.public()}


TOURS = ("home", "portal", "diary", "studio")      # the guided tours: forms page, staff portal, student diary, newsletter studio


def _split(text) -> Set[str]:
    return {t for t in (text or "").split(",") if t in TOURS}


def mark_tour_seen(user: User, tour: str) -> Set[str]:
    """Called when someone finishes or skips a tour, so it is not pushed on them again (they can still replay it from Help)."""
    if tour not in TOURS:
        raise HTTPException(400, "Unknown tour")
    if demo_enabled():                      # shared demo logins: the next visitor should get the tour too
        return set(user.tours_seen)
    with db() as conn:
        row = conn.execute("SELECT tours_seen FROM users WHERE user_id = ?", (user.id,)).fetchone()
        seen = _split(row[0] if row else "") | {tour}
        conn.execute("UPDATE users SET tours_seen = ? WHERE user_id = ?", (",".join(sorted(seen)), user.id))
    return seen


def change_password(user: User, old: str, new: str):
    if demo_enabled():
        raise HTTPException(403, "Passwords cannot be changed in the demo, so that everyone can keep signing in with the demo accounts.")
    if len(new or "") < 8:
        raise HTTPException(400, "New password must be at least 8 characters")
    with db() as conn:
        row = conn.execute("SELECT password_hash FROM users WHERE user_id = ?", (user.id,)).fetchone()
        if not row or not verify_password(old or "", row["password_hash"]):
            raise HTTPException(400, "Current password is wrong")
        conn.execute("UPDATE users SET password_hash = ?, must_change = 0 WHERE user_id = ?", (hash_password(new), user.id))


def set_staff_password(conn, emp_id: str, pw: str):
    conn.execute("INSERT INTO users (user_id, user_type, password_hash, must_change) VALUES (?, 'STAFF', ?, 1) "
                 "ON CONFLICT(user_id) DO UPDATE SET password_hash = excluded.password_hash, must_change = 1",
                 (emp_id, hash_password(pw)))


# ---------------------------------------------------------------- FastAPI dependencies
def current_user(authorization: Optional[str] = Header(None)) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Please sign in")
    data = parse_token(authorization[7:])
    with db() as conn:
        user = load_user(conn, data["sub"], data["typ"])
        if not user:
            raise HTTPException(401, "Account is no longer active")
        row = conn.execute("SELECT must_change, tours_seen FROM users WHERE user_id = ?", (user.id,)).fetchone()
        user.must_change, user.tours_seen = bool(row and row[0]), _split(row[1] if row else "")
    return user


def staff_user(user: User = Depends(current_user)) -> User:
    if user.kind != "STAFF":
        raise HTTPException(403, "Staff only")
    return user


def admin_user(user: User = Depends(staff_user)) -> User:
    if not user.is_admin:
        raise HTTPException(403, "Admin only")
    return user


def editor_user(user: User = Depends(staff_user)) -> User:
    """Admin or a class tutor: may upload data and manage students."""
    if not (user.is_admin or user.tutor_class_ids):
        raise HTTPException(403, "Only tutors and the Admin can do this")
    return user
