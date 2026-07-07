"""Event emission. Called only from inside the same transaction that writes
the domain rows (the non-negotiable invariant). Payloads always carry
{"schema_version": 1, ...}.
"""

from __future__ import annotations

import json
import sqlite3

from . import utils

PAYLOAD_SCHEMA_VERSION = 1


def emit(
    conn: sqlite3.Connection,
    *,
    actor: str,
    entity: str,
    entity_id: int | None,
    action: str,
    payload: dict | None = None,
) -> int:
    body = {"schema_version": PAYLOAD_SCHEMA_VERSION}
    if payload:
        body.update(payload)
    cursor = conn.execute(
        "INSERT INTO events (ts, actor, entity, entity_id, action, payload_json) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            utils.utc_now_iso(),
            actor,
            entity,
            entity_id,
            action,
            json.dumps(body, ensure_ascii=False, sort_keys=True),
        ),
    )
    return cursor.lastrowid
