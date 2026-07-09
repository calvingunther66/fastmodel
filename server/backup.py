"""Backup & restore of the data directory (L1), standard-library only.

A backup is a zip of everything under DATA_DIR (accounts, schedule, tokens,
stats, settings, audit log, the uploaded workbook, …) so the whole app state can
be moved to a fresh Pi or rolled back. Restore extracts a backup over DATA_DIR.

The inbox of dropped spreadsheets is excluded (it can be large and is a transient
source, not state). Restore guards against path traversal in the archive.
"""

from __future__ import annotations

import datetime as dt
import io
import zipfile
from pathlib import Path


def _included(path: Path, data_dir: Path) -> bool:
    rel = path.relative_to(data_dir)
    # skip the transient inbox of dropped spreadsheets
    return rel.parts[:1] != ("inbox",)


def make_backup(data_dir: Path) -> bytes:
    """Return a zip of the data directory as bytes."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(data_dir.rglob("*")):
            if path.is_file() and _included(path, data_dir):
                zf.write(path, arcname=str(path.relative_to(data_dir)))
    return buf.getvalue()


def backup_filename() -> str:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"fastmodel-backup-{stamp}.zip"


def restore_backup(data_dir: Path, zip_bytes: bytes) -> dict:
    """Extract a backup zip over the data directory. Returns a summary.

    Rejects archives with absolute or parent-traversing member paths.
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile as exc:
        raise ValueError("not a valid backup zip") from exc

    members = [m for m in zf.namelist() if not m.endswith("/")]
    data_dir = data_dir.resolve()
    safe = []
    for name in members:
        dest = (data_dir / name).resolve()
        if not str(dest).startswith(str(data_dir) + "/") and dest != data_dir:
            raise ValueError(f"unsafe path in archive: {name}")
        safe.append((name, dest))

    for name, dest in safe:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(zf.read(name))
    return {"restored": len(safe)}
