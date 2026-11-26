"""Back up both databases to a separate, PRIVATE Git repository.

    venv\\Scripts\\python.exe backup_db.py              copy, commit and push
    venv\\Scripts\\python.exe backup_db.py --no-push    copy and commit only
    --to FOLDER                                        another backup folder (default: ..\\IT-Matrix-DB-backup)

The backup folder is a clone of the private repository and must be OUTSIDE this project: the databases hold password hashes and
faculty and student records. Each copy is taken through SQLite itself, so it is complete even while the application is running
(copying the .db file by hand can miss what is still in the -wal file).

To restore: stop the application; in database\\ delete master_system.db-wal and master_system.db-shm (if present); copy the .db
files from the backup folder (or from an earlier commit of it) into database\\; start the application.
"""
import argparse
import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from datetime import datetime

import envfile  # noqa: F401  (settings from the project's .env, which may move the databases)
from database.db_manager import DB_PATH as NEWSLETTER_DB
from database.master_db import db_path

PROJECT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_FOLDER = os.path.join(os.path.dirname(PROJECT), "IT-Matrix-DB-backup")
GITHUB_LIMIT, GITHUB_WARNING = 100 * 1024 * 1024, 50 * 1024 * 1024     # GitHub refuses a file over 100 MB


class BackupError(Exception):
    pass


def git(folder, *args, check=True):
    done = subprocess.run(["git", "-C", folder, *args], capture_output=True, text=True, stdin=subprocess.DEVNULL,
                          env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})        # a scheduled run must fail, not wait for a password
    if check and done.returncode:
        raise BackupError(f"git {' '.join(args)} failed:\n{(done.stderr or done.stdout).strip()}")
    return done


def check_folder(folder):
    """The folder must be the top of its own repository, outside this project."""
    if not os.path.isdir(folder):
        raise BackupError(f"{folder} does not exist. Clone your private backup repository there first.")
    real, project = os.path.realpath(folder), os.path.realpath(PROJECT)
    if os.path.normcase(real + os.sep).startswith(os.path.normcase(project + os.sep)):
        raise BackupError("The backup folder must be outside the project, so the databases never get into the code repository.")
    top = git(folder, "rev-parse", "--show-toplevel", check=False)
    if top.returncode or os.path.normcase(os.path.realpath(top.stdout.strip())) != os.path.normcase(real):
        raise BackupError(f"{folder} is not its own Git repository. Clone your private backup repository there first.")


def snapshot(source, target):
    """A consistent copy of a database that may be in use, checked before it replaces the previous backup."""
    part = target + ".part"
    if os.path.exists(part):
        os.remove(part)
    with closing(sqlite3.connect(source, timeout=30)) as src, closing(sqlite3.connect(part)) as dst:
        src.backup(dst)
        dst.execute("PRAGMA journal_mode = DELETE")                       # one self-contained file
        result = dst.execute("PRAGMA integrity_check").fetchone()[0]
    if result != "ok":
        raise BackupError(f"The copy of {source} did not pass SQLite's check: {result}")
    size = os.path.getsize(part)
    if size >= GITHUB_LIMIT:
        os.remove(part)
        raise BackupError(f"{os.path.basename(source)} is {size / 1048576:.0f} MB. GitHub refuses files of 100 MB or more: back it up elsewhere.")
    if size >= GITHUB_WARNING:
        print(f"Warning: {os.path.basename(source)} is {size / 1048576:.0f} MB; GitHub refuses files of 100 MB or more.")
    os.replace(part, target)
    return size


def run(folder, push=True):
    check_folder(folder)
    names = []
    for source in (db_path(), NEWSLETTER_DB):
        if not os.path.exists(source):
            raise BackupError(f"Database not found: {source}")
        name = os.path.basename(source)
        print(f"{name}: {snapshot(source, os.path.join(folder, name)) / 1024:.0f} KB copied and checked")
        names.append(name)
    git(folder, "add", "-f", "--", *names)                                # only the databases, never anything else in the folder
    if git(folder, "diff", "--cached", "--quiet", check=False).returncode:
        git(folder, "commit", "-m", f"Database backup {datetime.now():%Y-%m-%d %H:%M}")
        print("Committed.")
    else:
        print("Nothing has changed since the last backup.")
    if not push:
        print("Not pushed (--no-push).")
    elif not git(folder, "remote", check=False).stdout.strip():
        raise BackupError("The backup repository has no remote, so nothing was uploaded.")
    else:
        git(folder, "push", "-u", "origin", "HEAD")                       # also sends commits an earlier failed run left behind
        print("Pushed to GitHub.")


def main():
    ap = argparse.ArgumentParser(description="Back up the databases to a private Git repository.")
    ap.add_argument("--to", default=DEFAULT_FOLDER, help="the backup repository's folder")
    ap.add_argument("--no-push", action="store_true", help="commit without uploading")
    a = ap.parse_args()
    folder = os.path.abspath(a.to)
    try:
        run(folder, push=not a.no_push)
        outcome, code = "OK", 0
    except (BackupError, OSError, sqlite3.Error) as e:
        print(f"BACKUP FAILED: {e}", file=sys.stderr)
        outcome, code = "FAILED: " + " ".join(str(e).split()), 1
    if os.path.isdir(os.path.join(folder, ".git")):                       # a scheduled run shows no window: keep a record
        with open(os.path.join(folder, ".git", "backup.log"), "a", encoding="utf-8") as log:
            log.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {outcome}{' (not pushed)' if a.no_push and not code else ''}\n")
    return code


if __name__ == "__main__":
    sys.exit(main())
