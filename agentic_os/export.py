"""Export and snapshot.

`export events` is a read-only, EVENTLESS derived view (extends D-P0.6):
one JSON object per line, all columns, ascending id.

`snapshot` copies aos.db through the sqlite3 backup API (`conn.backup`) —
NEVER a bare file copy: the database runs in WAL mode and a raw copy can
miss or tear transactions still living in the -wal file. The audit event
(action=snapshot) is emitted AFTER the file is written, so the snapshot
never contains its own event; the payload says so.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from . import db, events, ops, utils


def _utc_stamp() -> str:
    """YYYYMMDDTHHMMSSZ, derived from the single clock utility."""
    return utils.utc_now_iso().replace("-", "").replace(":", "")


def _collision_free(path: Path) -> Path:
    """On collision, append -2, -3, … before the suffix."""
    if not path.exists():
        return path
    n = 2
    while True:
        candidate = path.with_name(f"{path.stem}-{n}{path.suffix}")
        if not candidate.exists():
            return candidate
        n += 1


def export_events(
    conn: sqlite3.Connection, aos_dir: Path, output: str | None = None
) -> tuple[Path, int]:
    if output is not None:
        path = Path(output).expanduser().resolve()
    else:
        path = _collision_free(
            aos_dir / "exports" / f"events-{_utc_stamp()}.jsonl"
        )
    rows = conn.execute("SELECT * FROM events ORDER BY id").fetchall()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(dict(row), ensure_ascii=False) + "\n")
    return path, len(rows)


def snapshot(conn: sqlite3.Connection, aos_dir: Path) -> Path:
    exports_dir = aos_dir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    path = _collision_free(exports_dir / f"aos-{_utc_stamp()}.db")
    dest = sqlite3.connect(path)
    try:
        conn.backup(dest)
    finally:
        dest.close()
    with db.transaction(conn):
        events.emit(
            conn,
            actor=ops.ACTOR_HUMAN,
            entity="system",
            entity_id=None,
            action="snapshot",
            payload={
                "filename": path.name,
                "path": f"exports/{path.name}",
                "note": (
                    "snapshot file was written before this event; "
                    "the snapshot does not contain its own event"
                ),
            },
        )
    return path
