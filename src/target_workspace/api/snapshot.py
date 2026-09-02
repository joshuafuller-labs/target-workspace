"""Workspace snapshot — sqlite-hot-backup → tar.gz with manifest (tw-b0ky).

MVP scope: hot-consistent SQLite snapshot, packaged with a manifest, as
an admin-only download. Restore into a FRESH instance only (refuses if
destination is populated). Scheduled backups are a deployment concern.

Format:
  data.db       — sqlite3.Connection.backup() target (point-in-time)
  manifest.json — {version, schema_version, exported_at, exporter_user_id}
"""

from __future__ import annotations

import io
import json
import os
import sqlite3
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _hot_copy_sqlite(src_db_path: str, dst_db_path: str) -> None:
    """Hot backup using SQLite's online backup API.

    Safe to run while the source is being written to.
    """
    src = sqlite3.connect(src_db_path)
    dst = sqlite3.connect(dst_db_path)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def make_snapshot(*, src_db_path: str, manifest: dict[str, Any]) -> bytes:
    """Return a tar.gz containing data.db + manifest.json."""
    with tempfile.TemporaryDirectory() as work:
        db_target = os.path.join(work, "data.db")
        _hot_copy_sqlite(src_db_path, db_target)
        manifest_json = json.dumps(manifest, separators=(",", ":"), sort_keys=True)

        out = io.BytesIO()
        with tarfile.open(fileobj=out, mode="w:gz") as tf:
            tf.add(db_target, arcname="data.db")
            man_bytes = manifest_json.encode("utf-8")
            info = tarfile.TarInfo(name="manifest.json")
            info.size = len(man_bytes)
            info.mtime = int(datetime.now(tz=UTC).timestamp())
            tf.addfile(info, io.BytesIO(man_bytes))
        return out.getvalue()


def restore_snapshot(
    *,
    dst_db_path: str,
    tar_bytes: bytes,
    allow_overwrite: bool = False,
) -> dict[str, Any]:
    """Restore a snapshot into dst_db_path.

    Refuses if dst_db_path already exists (interpreted as populated)
    unless allow_overwrite=True. Returns the parsed manifest on success.
    """
    if Path(dst_db_path).exists() and not allow_overwrite:
        raise ValueError(
            f"destination is not empty: {dst_db_path} (use allow_overwrite=True to force)"
        )

    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:gz") as tf:
        names = tf.getnames()
        if "data.db" not in names or "manifest.json" not in names:
            raise ValueError(f"snapshot missing required members; got {names!r}")
        man_member = tf.extractfile("manifest.json")
        assert man_member is not None
        manifest: dict[str, Any] = json.loads(man_member.read())
        db_member = tf.extractfile("data.db")
        assert db_member is not None
        Path(dst_db_path).write_bytes(db_member.read())
    return manifest


def current_schema_version(db_path: str) -> str:
    """Return the alembic version_num for the given DB, or empty string."""
    try:
        c = sqlite3.connect(db_path)
        try:
            row = c.execute("SELECT version_num FROM alembic_version LIMIT 1").fetchone()
        except sqlite3.OperationalError:
            return ""
        finally:
            c.close()
    except sqlite3.DatabaseError:
        return ""
    return row[0] if row else ""
