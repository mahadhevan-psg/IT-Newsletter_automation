import os
import sys

# Ensure workspace root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import envfile  # noqa: E402,F401  (reads .env: the same settings as the server, see .env.example)
import uvicorn  # noqa: E402

if __name__ == "__main__":
    # HOST=127.0.0.1 (this computer only) or 0.0.0.0 (everyone on the network); PORT; RELOAD=0 to stop restarting on code changes: all from .env
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    reload = os.environ.get("RELOAD", "1").strip().lower() not in ("0", "false", "no", "off")
    shown = "localhost" if host in ("127.0.0.1", "0.0.0.0") else host
    print(f"Starting the IT Matrix server at http://{shown}:{port}")
    print("  /            sign in (everyone starts here)      /newsletter/   newsletter studio (Admin, HoD)")
    print("  /homepage/   faculty: the home page              /portal/       staff portal")
    print("  /diary/      students: placements diary")
    uvicorn.run("backend.app:app", host=host, port=port, reload=reload)
