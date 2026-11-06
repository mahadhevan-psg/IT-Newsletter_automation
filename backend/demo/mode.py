"""Is this server running as the public DEMO? (DEMO_MODE=true). Kept tiny and dependency-free: auth imports it."""
import os

PASSWORD = "Demo@1234"       # every demo account uses this; it is published on the demo sign-in page, so it must never protect real data


def enabled() -> bool:
    return os.environ.get("DEMO_MODE", "").strip().lower() in ("1", "true", "yes", "on")


def reset_hours() -> float:
    try:
        return max(0.05, float(os.environ.get("DEMO_RESET_HOURS", "12")))
    except ValueError:
        return 12.0
