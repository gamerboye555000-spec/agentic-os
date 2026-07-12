"""Event emission. Called only from inside the same transaction that writes
the domain rows (the non-negotiable invariant). Payloads always carry
{"schema_version": 1, ...}.

U-C3 (D-v0.2.15, D-v0.2.21): no event record ever carries a secret-shaped
string. Every payload passes secretscan.redact_tree here — the one choke
point every write shares — so a matched value never reaches the journal,
not even a previously accepted secret-shaped identifier copied into a
later event (an agent name on update, a project slug on task add). The
top-level actor column gets the same treatment: a secret-shaped actor (a
syntactically valid `agent:<name>` evidence provenance can be
credential-shaped) is stored as the same fixed placeholder — never a hash,
preview, or excerpt — while a benign actor is stored byte-identical. The
canonical domain row keeps the accepted value; affected events carry the
safe secret_warning/secret_fields/secret_patterns metadata supplied by the
caller. Redaction is the identity on benign payloads and actors, so
unaffected event shapes and values stay byte-identical to the baseline.
"""

from __future__ import annotations

import json
import sqlite3

from . import secretscan, utils

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
        body.update(secretscan.redact_tree(payload))
    cursor = conn.execute(
        "INSERT INTO events (ts, actor, entity, entity_id, action, payload_json) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            utils.utc_now_iso(),
            secretscan.redact_tree(actor),
            entity,
            entity_id,
            action,
            json.dumps(body, ensure_ascii=False, sort_keys=True),
        ),
    )
    return cursor.lastrowid
