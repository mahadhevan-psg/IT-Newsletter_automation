"""Sets the ADMIN login's password to MASTER_ADMIN_PASSWORD from .env (or to the password you type after the command).

Why this exists: MASTER_ADMIN_PASSWORD is only used the FIRST time, when the database has no admin yet. A database that already has its
admin keeps that admin's password, so changing .env later changes nothing. Run this once to make the ADMIN password what .env says:

    python reset_admin_password.py                 uses MASTER_ADMIN_PASSWORD from .env
    python reset_admin_password.py "NewPassword1"  uses the password you give

The next sign-in as ADMIN asks for a new password, as for any new login. Stop the server first if it is running on the same database.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import envfile  # noqa: E402,F401  (reads .env)
from backend.master.auth import set_staff_password  # noqa: E402
from database.master_db import db, db_path, init_master_db  # noqa: E402


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    pw = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("MASTER_ADMIN_PASSWORD", "")
    if not pw:
        has_env = os.path.isfile(os.path.join(here, ".env"))
        print("No password found. " + ("MASTER_ADMIN_PASSWORD is missing or empty in .env." if has_env else
              "There is no .env file here (the app reads '.env', not '.env.example': copy it to '.env' and edit that one)."))
        print("Or pass it after the command:  python reset_admin_password.py \"YourPassword\"")
        return 1
    print(f"Using the password from {'the command' if len(sys.argv) > 1 else '.env'} ({len(pw)} characters).")
    if len(pw) < 8:
        print("Note: that is short. Sign-in will accept it, but the new password you are asked to choose afterwards must have at least 8 characters.")
    init_master_db()                                   # creates the database and the ADMIN login if they do not exist yet
    with db() as conn:
        set_staff_password(conn, "ADMIN", pw)
    print(f"ADMIN password set in {os.path.abspath(db_path())}")
    print("Sign in as ADMIN with it; you will be asked to choose a new password.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
