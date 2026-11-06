"""/api/demo/*: what the sign-in page and the banner need. In a normal (non-demo) deployment these answer 'not a demo'."""
from fastapi import APIRouter, HTTPException

from backend.demo.mode import enabled

router = APIRouter()


@router.get("/api/demo/info")
def demo_info():
    if not enabled():
        return {"enabled": False}
    from backend.demo import seed
    return seed.info()


@router.post("/api/demo/reset")
def demo_reset():
    """Public on purpose (it is a demo that anyone may tidy up), so it is rate limited to once every five minutes."""
    if not enabled():
        raise HTTPException(404, "Not available")
    from backend.demo import seed
    wait = seed.manual_reset_wait()
    if wait:
        raise HTTPException(429, f"The demo was reset a moment ago. Please try again in {wait} seconds.")
    return {"success": True, "counts": seed.reset(manual=True)}
