"""Photos uploaded with an entry, kept in the application's own database.

An upload is checked, straightened, resized (longest side 1600 px) and compressed to a JPEG of roughly 150-400 KB (the original, often 3-10 MB,
is discarded), plus a small thumbnail. The two pictures go in `media_blobs`; `media_files` holds only the small metadata row, so listings and
searches never read image data. The same photo uploaded twice by one person is stored once.

An entry refers to a photo as  media://<id>  (see ref()). The picture is served at /api/media/<id>/<token>; the token is part of the file's hash,
so the address cannot be guessed. Because it lives in the database, a backup of the database is a backup of the photos.
"""
import hashlib
import io
import os
import re
import tempfile
from typing import Any, Dict, Optional

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError

from database.master_db import db

MAX_UPLOAD = 15 * 1024 * 1024            # a phone photo is rarely larger; anything bigger is refused before it is read into memory twice
MAX_DOCUMENT = 5 * 1024 * 1024           # PDFs are stored as uploaded, so they get a tighter limit than photos
MAX_SIDE = 1600
THUMB_SIDE = 420
JPEG_QUALITY = 82
MAX_PIXELS = 60_000_000                  # refuse decompression bombs
def ref(media_id: int) -> str:
    return f"media://{media_id}"


def link_ref(meta: Dict[str, Any]) -> str:
    """The reference stored with an entry. It carries the file's token, so any screen can turn it into the file's address."""
    return f"media://{meta['media_id']}/{meta['token']}"


def parse_ref(text: Any) -> Optional[int]:
    m = re.fullmatch(r"media://(\d+)(?:/[0-9a-f]+)?", str(text or "").strip())
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
            "kind": row["kind"], "link_ref": link_ref(row), "width": row["width"], "height": row["height"], "bytes": row["bytes"], "name": row["original_name"]}


def save_document(owner_id: str, filename: str, content: bytes) -> Dict[str, Any]:
    """A certificate, report or letter: a PDF is kept as it is; a picture of a document is shrunk like any photo."""
    if content[:5] != b"%PDF-":
        try:
            return save_upload(owner_id, filename, content)
        except HTTPException as e:
            if e.status_code == 400 and content:
                raise HTTPException(400, "Upload the document as a PDF, or as a JPEG, PNG or WebP picture")
            raise
    if len(content) > MAX_DOCUMENT:
        raise HTTPException(413, f"That PDF is larger than {MAX_DOCUMENT // (1024 * 1024)} MB. Compress it and upload it again.")
    return _store(owner_id, filename or "document.pdf", "DOCUMENT", content, None, None, None)


def save_upload(owner_id: str, filename: str, content: bytes) -> Dict[str, Any]:
    main, thumb, w, h = _process(content)
    return _store(owner_id, filename or "photo", "PHOTO", main, thumb, w, h)


def _store(owner_id: str, filename: str, kind: str, main: bytes, thumb: Optional[bytes], w: Optional[int], h: Optional[int]) -> Dict[str, Any]:
    sha = hashlib.sha256(main).hexdigest()
    with db() as conn:
        dup = conn.execute("SELECT * FROM media_files WHERE owner_id = ? AND sha256 = ?", (owner_id, sha)).fetchone()
        if dup:
            return info(dup)                                # the same photo again: no second copy
        mid = conn.execute("INSERT INTO media_files (owner_id, kind, original_name, sha256, token, width, height, bytes) VALUES (?,?,?,?,?,?,?,?)",
                           (owner_id, kind, filename[:120], sha, sha[:16], w, h, len(main))).lastrowid
        conn.execute("INSERT INTO media_blobs (media_id, data, thumb) VALUES (?, ?, ?)", (mid, main, thumb))
        return info(conn.execute("SELECT * FROM media_files WHERE media_id = ?", (mid,)).fetchone())


def get(media_id: int) -> Optional[Dict[str, Any]]:
    """The metadata row (never the picture itself)."""
    with db() as conn:
        row = conn.execute("SELECT * FROM media_files WHERE media_id = ?", (media_id,)).fetchone()
        return dict(row) if row else None


def read(media_id: int, thumb: bool = False) -> Optional[bytes]:
    with db() as conn:
        row = conn.execute("SELECT data, thumb FROM media_blobs WHERE media_id = ?", (media_id,)).fetchone()
    if not row:
        return None
    return bytes((row["thumb"] if thumb and row["thumb"] else row["data"]))


def resolve(text: Any) -> Optional[str]:
    """For the newsletter generator, which wants a file: a 'media://12' reference -> a cached copy on disk (None for anything else)."""
    mid = parse_ref(text)
    meta = get(mid) if mid else None
    if not meta:
        return None
    folder = os.path.join(tempfile.gettempdir(), "itmatrix_media")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{mid}_{meta['sha256'][:16]}.jpg")
    if not os.path.exists(path):
        data = read(mid)
        if not data:
            return None
        with open(path, "wb") as f:
            f.write(data)
    return path
