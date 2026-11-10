"""When the Google Sheets are pulled (and the pull itself).

The Admin sets the rhythm in the portal: every N days, or one weekday each week, at a time of day in a chosen time zone.
It can be changed at any time, switched off, and a pull can always be started by hand. The timer runs inside the server, so
the server has to be running at that moment: on a service that sleeps when idle, the pull happens when it wakes up.
"""
import json
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException

from backend.review import service, sheets
from database.master_db import audit, db

SOURCES = ["form_student", "form_research", "form_faculty", "form_departmental", "form_industry", service.PLACEMENT]
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_run_lock = threading.Lock()
_started = {"thread": None}


# ---------------------------------------------------------------- settings
def _utc(text: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc) if text else None


def compute_next(s: Dict[str, Any], now: datetime, last_run: Optional[datetime] = None) -> Optional[datetime]:
    """The next pull (UTC). 'week': the coming chosen weekday at the chosen time. 'days': N days after the last pull, at the chosen time
    (an overdue pull happens straight away); with no earlier pull, the next time the clock shows that time."""
    if not s.get("enabled"):
        return None
    tz = ZoneInfo(s["timezone"])
    local = now.astimezone(tz)
    at = lambda d: d.replace(hour=s["hour"], minute=s["minute"], second=0, microsecond=0)
    if s["mode"] == "week":
        cand = at(local + timedelta(days=(s["weekday"] - local.weekday()) % 7))
        if cand <= local:
            cand += timedelta(days=7)
    elif last_run:
        cand = at(last_run.astimezone(tz) + timedelta(days=s["every_days"]))
        if cand <= local:
            return now                                   # overdue: run as soon as the timer looks
    else:
        cand = at(local)
        if cand <= local:
            cand += timedelta(days=1)
    return cand.astimezone(timezone.utc)


def validate(p: Dict[str, Any]) -> Dict[str, Any]:
    try:
        clean = {"enabled": 1 if p.get("enabled") else 0, "mode": p.get("mode", "days"), "every_days": int(p.get("every_days", 2)), "weekday": int(p.get("weekday", 0)),
                 "hour": int(p.get("hour", 2)), "minute": int(p.get("minute", 0)), "timezone": (p.get("timezone") or "Asia/Kolkata").strip()}
    except (TypeError, ValueError):
        raise HTTPException(400, "Please enter whole numbers for the days and the time")
    if clean["mode"] not in ("days", "week"):
        raise HTTPException(400, "Choose 'every N days' or 'once a week'")
    if not 1 <= clean["every_days"] <= 60:
        raise HTTPException(400, "Pull every 1 to 60 days")
    if not 0 <= clean["weekday"] <= 6 or not 0 <= clean["hour"] <= 23 or not 0 <= clean["minute"] <= 59:
        raise HTTPException(400, "That day or time is not valid")
    try:
        ZoneInfo(clean["timezone"])
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(400, f"'{clean['timezone']}' is not a time zone name (for India: Asia/Kolkata)")
    return clean


def get_settings(conn) -> Dict[str, Any]:
    conn.execute("INSERT OR IGNORE INTO sync_settings (id) VALUES (1)")
    return dict(conn.execute("SELECT * FROM sync_settings WHERE id = 1").fetchone())


def describe(s: Dict[str, Any]) -> str:
    if not s["enabled"]:
        return "Automatic pulls are switched off. You can still pull whenever you like."
    when = f"{s['hour']:02d}:{s['minute']:02d} ({s['timezone']})"
    return (f"Every {WEEKDAYS[s['weekday']]} at {when}" if s["mode"] == "week" else (f"Every day at {when}" if s["every_days"] == 1 else f"Every {s['every_days']} days at {when}"))


def save_settings(conn, user, payload: Dict[str, Any]) -> Dict[str, Any]:
    clean = validate(payload)
    conn.execute("INSERT OR IGNORE INTO sync_settings (id) VALUES (1)")
    nxt = compute_next(clean, datetime.now(timezone.utc), None)
    conn.execute("UPDATE sync_settings SET enabled = ?, mode = ?, every_days = ?, weekday = ?, hour = ?, minute = ?, timezone = ?, next_run_at = ?, updated_by = ? WHERE id = 1",
                 (clean["enabled"], clean["mode"], clean["every_days"], clean["weekday"], clean["hour"], clean["minute"], clean["timezone"],
                  nxt.strftime("%Y-%m-%d %H:%M:%S") if nxt else None, user.id))
    audit(conn, user.id, "SYNC_SETTINGS", "sync_settings", "1", describe({**clean, "enabled": clean["enabled"]}))
    return get_settings(conn)


# ---------------------------------------------------------------- the pull
def overview(conn) -> Dict[str, Any]:
    s = get_settings(conn)
    nxt = _utc(s["next_run_at"])
    local_next = nxt.astimezone(ZoneInfo(s["timezone"])).strftime("%a %d %b %Y, %H:%M") if nxt else None
    titles = {fid: service.LABELS[fid] for fid in SOURCES}
    pending = {r[0]: r[1] for r in conn.execute("SELECT form_id, COUNT(*) FROM staged_items WHERE status = 'PENDING' GROUP BY 1")}
    have = {r["form_id"]: dict(r) for r in conn.execute("SELECT * FROM sync_sources")}
    sources = [{"form_id": f, "title": titles[f], "sheet_url": have.get(f, {}).get("sheet_url") or "", "last_pulled_at": have.get(f, {}).get("last_pulled_at"),
                "last_result": json.loads(have[f]["last_result"]) if have.get(f, {}).get("last_result") else None, "pending": pending.get(f, 0)} for f in SOURCES]
    runs = [{**dict(r), "summary": json.loads(r["summary_json"]) if r["summary_json"] else None} for r in conn.execute("SELECT * FROM sync_runs ORDER BY run_id DESC LIMIT 12")]
    for r in runs:
        r.pop("summary_json", None)
    return {"settings": {**s, "describe": describe(s), "next_run_local": local_next, "weekdays": WEEKDAYS}, "sources": sources, "runs": runs,
            "service_account": sheets.using_service_account(), "running": _run_lock.locked()}


def set_source(conn, user, form_id: str, url: str):
    if form_id not in SOURCES:
        raise HTTPException(400, "Unknown form")
    url = (url or "").strip()
    if url:
        try:
            if not url.startswith("demo://"):
                sheets.parse_url(url)
        except sheets.SheetError as e:
            raise HTTPException(400, str(e))
    conn.execute("INSERT INTO sync_sources (form_id, sheet_url) VALUES (?, ?) ON CONFLICT(form_id) DO UPDATE SET sheet_url = excluded.sheet_url", (form_id, url or None))
    audit(conn, user.id, "SYNC_SOURCE", "sync_sources", form_id, "set" if url else "cleared")


def run_sync(trigger: str, actor: Optional[str], only: Optional[List[str]] = None) -> Dict[str, Any]:
    """Read every configured sheet (or just `only`) and put new responses into the review queue. Each sheet is independent:
    one that fails does not stop the others. Returns what happened per sheet."""
    if not _run_lock.acquire(blocking=False):
        raise HTTPException(409, "A pull is already running. Give it a minute.")
    try:
        with db() as conn:
            run_id = conn.execute("INSERT INTO sync_runs (trigger, actor, status) VALUES (?,?, 'running')", (trigger, actor)).lastrowid
            todo = [(r["form_id"], r["sheet_url"]) for r in conn.execute("SELECT form_id, sheet_url FROM sync_sources WHERE sheet_url IS NOT NULL AND sheet_url != ''")
                    if not only or r["form_id"] in only]
        results: Dict[str, Any] = {}
        for form_id, url in todo:
            try:
                rows = sheets.fetch_rows(url)
                with db() as conn:
                    counts = service.stage_rows(conn, form_id, rows)
                results[form_id] = {"rows": len(rows), **counts}
            except sheets.SheetError as e:
                results[form_id] = {"error": str(e)}
            except Exception as e:                                                  # a bug must not leave the run 'running' forever
                results[form_id] = {"error": f"Unexpected problem: {type(e).__name__}"}
            with db() as conn:
                conn.execute("UPDATE sync_sources SET last_pulled_at = CURRENT_TIMESTAMP, last_result = ? WHERE form_id = ?", (json.dumps(results[form_id]), form_id))
        new = sum(r.get("new", 0) + r.get("updated", 0) for r in results.values())
        failed = [f for f, r in results.items() if "error" in r]
        status = "failed" if results and len(failed) == len(results) else "done"
        with db() as conn:
            conn.execute("UPDATE sync_runs SET finished_at = CURRENT_TIMESTAMP, status = ?, summary_json = ? WHERE run_id = ?",
                         (status, json.dumps({"sources": results, "new_or_updated": new, "failed": failed, "none_configured": not todo}), run_id))
            s = get_settings(conn)
            now = datetime.now(timezone.utc)
            nxt = compute_next(s, now, now if trigger == "schedule" else _utc(s["last_run_at"]))
            conn.execute("UPDATE sync_settings SET last_run_at = ?, next_run_at = ? WHERE id = 1",
                         (now.strftime("%Y-%m-%d %H:%M:%S") if trigger == "schedule" else s["last_run_at"], nxt.strftime("%Y-%m-%d %H:%M:%S") if nxt else None))
        return {"run_id": run_id, "status": status, "sources": results, "new_or_updated": new, "none_configured": not todo}
    finally:
        _run_lock.release()


# ---------------------------------------------------------------- the timer
def _tick() -> None:
    with db() as conn:
        s = get_settings(conn)
        conn.execute("UPDATE sync_runs SET status = 'failed', finished_at = CURRENT_TIMESTAMP WHERE status = 'running' AND NOT ?", (1 if _run_lock.locked() else 0,))
    nxt = _utc(s["next_run_at"])
    if s["enabled"] and nxt and datetime.now(timezone.utc) >= nxt:
        try:
            run_sync("schedule", None)
        except HTTPException:
            pass                                                                   # a manual pull is running; the next tick tries again


def _loop() -> None:
    while True:
        time.sleep(30)
        try:
            _tick()
        except Exception as e:                                                      # the timer must never die
            print("[sync] timer error:", e)


def start() -> None:
    """Called once at server start-up. Anything left 'running' by a crash is closed, then the timer starts."""
    with db() as conn:
        conn.execute("UPDATE sync_runs SET status = 'failed', finished_at = CURRENT_TIMESTAMP WHERE status = 'running'")
        s = get_settings(conn)
        if s["enabled"] and not s["next_run_at"]:
            nxt = compute_next(s, datetime.now(timezone.utc), _utc(s["last_run_at"]))
            conn.execute("UPDATE sync_settings SET next_run_at = ? WHERE id = 1", (nxt.strftime("%Y-%m-%d %H:%M:%S") if nxt else None,))
    if not _started["thread"]:
        t = threading.Thread(target=_loop, name="sheet-sync", daemon=True)
        t.start()
        _started["thread"] = t
