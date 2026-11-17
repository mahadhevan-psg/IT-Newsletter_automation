"""Reads the project's ".env" file into the process environment, so running on your own computer uses the same settings as the server.

The file holds the same variables as the Render service (see .env.example). A variable that is already set in the real environment
(Docker's --env-file, Render's dashboard, a shell) always wins over the file, and an empty value in the file is ignored. Docker does not
copy ".env" into the image: the container gets its settings from --env-file instead. Nothing is read while the tests run.
"""
import os
import sys

_done = {"loaded": False}
DOCKER_PATHS = ("DATA_DIR", "MASTER_DB_PATH", "NEWSLETTER_DB_PATH")


def load(path=None) -> bool:
    """Load the .env file once. Returns True when a file was read."""
    if _done["loaded"] or "pytest" in sys.modules:
        return False
    _done["loaded"] = True
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.isfile(path):
        return False
    count = 0
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key, value = key.strip(), value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            if key in DOCKER_PATHS and value.replace("\\", "/").startswith("/data") and not os.path.isdir("/data"):
                print(f"[env] ignoring {key}={value}: /data exists only inside Docker; the project's own database folder is used here")
                continue                                   # a .env written for Docker still works when the same file is used on a computer without Docker
            if key and value and key not in os.environ:
                os.environ[key] = value
                count += 1
    if count:
        print(f"[env] {count} setting(s) read from {os.path.basename(path)}")
    return True


load()
