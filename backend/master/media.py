"""Photos uploaded with an entry.

Nothing image-sized is ever stored in the database. An upload is checked, straightened, resized (longest side 1600 px) and compressed to a
JPEG of roughly 150-400 KB (the original, often 3-10 MB, is discarded), plus a small thumbnail. Both files live on disk; the database keeps only
a row of metadata (size, hash, where the file is, and its Google Drive id once uploaded). A background worker then copies each file to Google
Drive (see drive.py). If MEDIA_KEEP_LOCAL=false the full-size local copy is deleted after the Drive upload, leaving the thumbnail; the full file is
fetched from Drive again when the newsletter needs it.

An entry refers to a photo as  media://<id>  (see ref()). The file is served at /api/media/<id>/<token>; the token is part of the file's hash, so
the address cannot be guessed.
"""
import hashlib
import io
import os
import re
import threading
import time
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError

from backend.master import drive
from database.master_db import db

MAX_UPLOAD = 15 * 1024 * 1024            # a phone photo is rarely larger; anything bigger is refused before it is read into memory twice
MAX_SIDE = 1600
THUMB_SIDE = 420
JPEG_QUALITY = 82
MAX_PIXELS = 60_000_000                  # refuse decompression bombs
_worker = {"thread": None}


def media_dir() -> str:
    base = os.environ.get("MEDIA_DIR") or os.path.join(os.environ.get("DATA_DIR") or os.path.join(os.path.dirname(__file__), "..", "..", "output"), "media")
    os.makedirs(base, exist_ok=True)
    return os.path.abspath(base)


def ref(media_id: int) -> str:
    return f"media://{media_id}"


def parse_ref(text: Any) -> Optional[int]:
    m = re.fullmatch(r"media://(\d+)", str(text or "").strip())
    return int(m.group(1)) if m else None


def url(media_id: int, token: str, thumb: bool = False) -> str:
    return f"/api/media/{media_id}/{token}" + ("?thumb=1" if thumb else "")


def _process(content: bytes):
    """(jpeg bytes, thumbnail bytes, width, height). Raises HTTPException for anything that is not a usable picture."""
    if len(content) > MAX_UPLOAD:
        raise HTTPException(413, f"That photo is larger than {MAX_UPLOAD // (1024 * 1024)} MB. Choose a smaller one.")
    if not content:
        raise HTTPException(400, "The file is empty")
    try:
        img = Image.open(io.BytesIO(content))
        if img.width * img.height > MAX_PIXELS:
            raise HTTPException(400, "That picture is too large to process")
        img.load()
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise HTTPException(400, "That file is not a picture the portal can read. Use a JPEG, PNG or WebP photo.")
    img = ImageOps.exif_transpose(img)                      # phones store rotation in the metadata; apply it, then drop the metadata
    if img.mode in ("RGBA", "LA", "P"):
        rgba = img.convert("RGBA")
        flat = Image.new("RGB", rgba.size, (255, 255, 255))
        flat.paste(rgba, mask=rgba.split()[3])
        img = flat
    else:
        img = img.convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    main = io.BytesIO()
    img.save(main, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
    thumb = img.copy()
    thumb.thumbnail((THUMB_SIDE, THUMB_SIDE), Image.LANCZOS)
    tb = io.BytesIO()
    thumb.save(tb, "JPEG", quality=75, optimize=True)
    return main.getvalue(), tb.getvalue(), img.width, img.height


def info(row) -> Dict[str, Any]:
    return {"media_id": row["media_id"], "ref": ref(row["media_id"]), "url": url(row["media_id"], row["token"]), "thumb_url": url(row["media_id"], row["token"], True),
            "width": row["width"], "height": row["height"], "bytes": row["bytes"], "name": row["original_name"], "drive_status": row["drive_status"]}


def save_upload(owner_id: str, filename: str, content: bytes) -> Dict[str, Any]:
    main, thumb, w, h = _process(content)
    sha = hashlib.sha256(main).hexdigest()
    with db() as conn:
        dup = conn.execute("SELECT * FROM media_files WHERE owner_id = ? AND sha256 = ?", (owner_id, sha)).fetchone()
        if dup and dup["local_path"] and os.path.exists(dup["local_path"]):
            return info(dup)                                # the same photo again: no second copy
        now = datetime.now()
        folder = os.path.join(media_dir(), now.strftime("%Y"), now.strftime("%m"))
        os.makedirs(folder, exist_ok=True)
        path, tpath = os.path.join(folder, sha[:24] + ".jpg"), os.path.join(folder, sha[:24] + ".t.jpg")
        with open(path, "wb") as f:
            f.write(main)
        with open(tpath, "wb") as f:
            f.write(thumb)
        status = "QUEUED" if drive.configured() else "LOCAL"
        if dup:
            conn.execute("UPDATE media_files SET local_path = ?, thumb_path = ?, bytes = ? WHERE media_id = ?", (path, tpath, len(main), dup["media_id"]))
            return info(conn.execute("SELECT * FROM media_files WHERE media_id = ?", (dup["media_id"],)).fetchone())
        mid = conn.execute("INSERT INTO media_files (owner_id, kind, original_name, sha256, token, width, height, bytes, local_path, thumb_path, drive_status) VALUES (?, 'PHOTO', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                           (owner_id, (filename or "photo")[:120], sha, sha[:16], w, h, len(main), path, tpath, status)).lastrowid
        return info(conn.execute("SELECT * FROM media_files WHERE media_id = ?", (mid,)).fetchone())


def get(media_id: int) -> Optional[Dict[str, Any]]:
    with db() as conn:
        row = conn.execute("SELECT * FROM media_files WHERE media_id = ?", (media_id,)).fetchone()
        return dict(row) if row else None


def file_path(media_id: int, thumb: bool = False) -> Optional[str]:
    """Where the picture is on disk; fetched back from Google Drive first when only Drive still has it."""
    row = get(media_id)
    if not row:
        return None
    if thumb and row["thumb_path"] and os.path.exists(row["thumb_path"]):
        return row["thumb_path"]
    if row["local_path"] and os.path.exists(row["local_path"]):
        return row["local_path"]
    if row["drive_file_id"] and drive.configured():
        try:
            data = drive.download(row["drive_file_id"])
        except Exception:
            return None
        os.makedirs(os.path.dirname(row["local_path"] or os.path.join(media_dir(), "x")), exist_ok=True)
        path = row["local_path"] or os.path.join(media_dir(), row["sha256"][:24] + ".jpg")
        with open(path, "wb") as f:
            f.write(data)
        with db() as conn:
            conn.execute("UPDATE media_files SET local_path = ? WHERE media_id = ?", (path, media_id))
        return path
    return None


def resolve(text: Any) -> Optional[str]:
    """For the newsletter: a 'media://12' reference -> a file on disk (None for anything else)."""
    mid = parse_ref(text)
    return file_path(mid) if mid else None


# ------------------------------------------------------------------------------------------------ copying to Google Drive
def upload_pending(limit: int = 10) -> Dict[str, int]:
    """Copy queued (and earlier failed) photos to Google Drive. One failure never stops the rest."""
    done = failed = 0
    if not drive.configured():
        return {"uploaded": 0, "failed": 0}
    with db() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM media_files WHERE drive_status IN ('QUEUED','FAILED') AND attempts < 8 ORDER BY media_id LIMIT ?", (limit,))]
    keep = os.environ.get("MEDIA_KEEP_LOCAL", "true").strip().lower() not in ("0", "false", "no", "off")
    for r in rows:
        try:
            if not r["local_path"] or not os.path.exists(r["local_path"]):
                raise RuntimeError("the local file is missing")
            with open(r["local_path"], "rb") as f:
                data = f.read()
            file_id, link = drive.upload(f"{r['media_id']}_{(r['original_name'] or 'photo').rsplit('.', 1)[0][:60]}.jpg", data, r["created_at"][:4])
            with db() as conn:
                conn.execute("UPDATE media_files SET drive_file_id = ?, drive_url = ?, drive_status = 'UPLOADED', drive_error = NULL WHERE media_id = ?", (file_id, link, r["media_id"]))
            if not keep:
                try:
                    os.remove(r["local_path"])
                except OSError:
                    pass
            done += 1
        except Exception as e:
            with db() as conn:
                conn.execute("UPDATE media_files SET drive_status = 'FAILED', drive_error = ?, attempts = attempts + 1 WHERE media_id = ?", (str(e)[:300], r["media_id"]))
            failed += 1
    return {"uploaded": done, "failed": failed}


def status() -> Dict[str, Any]:
    with db() as conn:
        counts = {r[0]: r[1] for r in conn.execute("SELECT drive_status, COUNT(*) FROM media_files GROUP BY 1")}
        size = conn.execute("SELECT COALESCE(SUM(bytes), 0) FROM media_files").fetchone()[0]
        errors = [dict(r) for r in conn.execute("SELECT media_id, drive_error FROM media_files WHERE drive_status = 'FAILED' ORDER BY media_id DESC LIMIT 5")]
    return {"configured": drive.configured(), "counts": counts, "bytes": size, "recent_errors": errors}


def retry_failed() -> int:
    with db() as conn:
        return conn.execute("UPDATE media_files SET drive_status = 'QUEUED', attempts = 0 WHERE drive_status = 'FAILED'").rowcount


def _loop():
    while True:
        time.sleep(20)
        try:
            upload_pending()
        except Exception as e:                              # the worker must never die
            print("[media] drive worker error:", e)


def start_worker() -> None:
    if not _worker["thread"]:
        t = threading.Thread(target=_loop, name="drive-upload", daemon=True)
        t.start()
        _worker["thread"] = t
