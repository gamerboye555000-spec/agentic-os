"""Search over the ledger: tasks, decisions, evidence, handoffs, memory.

Backend: SQLite FTS5 when this build provides it, else a LIKE-style
fallback — detected at runtime and reported in the output.

The FTS index is a DERIVED artifact inside aos.db (`CREATE VIRTUAL TABLE IF
NOT EXISTS`), NOT part of the versioned schema: it is safe to DROP at any
time and is rebuilt from the source tables whenever the watermark stored in
meta (`fts_event_watermark` = max events.id at last build) says it is stale.
Rebuilding the index mutates no ledger rows, so it emits no event (the
derived-view rule, D-P0.6 / D-W5.2).
"""

from __future__ import annotations

import re
import sqlite3

from . import db, ids
from .models import MEMORY_SENSITIVITY_RESTRICTED
from .utils import AosError

FTS_TABLE = "search_index"
WATERMARK_KEY = "fts_event_watermark"

_SNIPPET_WINDOW = 40

_fts5_probe_result: bool | None = None


def fts5_available() -> bool:
    """Runtime FTS5 detection (probed once per process; patchable in tests
    to force the fallback path)."""
    global _fts5_probe_result
    if _fts5_probe_result is None:
        probe = sqlite3.connect(":memory:")
        try:
            probe.execute("CREATE VIRTUAL TABLE fts5_probe USING fts5(x)")
            _fts5_probe_result = True
        except sqlite3.OperationalError:
            _fts5_probe_result = False
        finally:
            probe.close()
    return _fts5_probe_result


def _documents(conn: sqlite3.Connection) -> list[tuple[str, int, str, str]]:
    """(entity, entity_id, title, body) for every searchable row. The body
    concatenates exactly the fields the contract says are searched; both
    backends consume the same documents, keeping membership aligned."""
    docs: list[tuple[str, int, str, str]] = []
    for row in conn.execute(
        "SELECT id, title, COALESCE(spec_md, '') AS spec, "
        "COALESCE(acceptance_md, '') AS acceptance FROM tasks ORDER BY id"
    ):
        body = "\n".join(part for part in (row["title"], row["spec"], row["acceptance"]) if part)
        docs.append(("task", row["id"], row["title"], body))
    for row in conn.execute(
        "SELECT id, title, decision_md FROM decisions ORDER BY id"
    ):
        docs.append(
            ("decision", row["id"], row["title"], row["title"] + "\n" + row["decision_md"])
        )
    for row in conn.execute(
        "SELECT id, COALESCE(claim, '') AS claim, ref FROM evidence ORDER BY id"
    ):
        body = "\n".join(part for part in (row["claim"], row["ref"]) if part)
        docs.append(("evidence", row["id"], row["claim"] or row["ref"], body))
    for row in conn.execute(
        "SELECT id, from_agent, to_agent, state_md FROM handoffs ORDER BY id"
    ):
        docs.append(
            (
                "handoff",
                row["id"],
                f"{row['from_agent']} → {row['to_agent']}",
                row["state_md"],
            )
        )
    # U-M2: search may surface historical claims (that is the point of a
    # ledger search), so every memory hit carries its curation status in the
    # title — a retired or quarantined claim can never be read off a results
    # list as live context.
    #
    # U-M3: a RESTRICTED claim still matches administratively — an operator
    # must be able to discover that something on their topic exists — but its
    # title and snippet are the fixed placeholder. The body is still indexed,
    # which is what makes the match possible; the index is derived state
    # inside the same database that already holds the value, so indexing it
    # exposes nothing new. The output is where the boundary is (M3.13).
    for row in conn.execute(
        "SELECT id, key, value_md, status, sensitivity FROM memory ORDER BY id"
    ):
        restricted = row["sensitivity"] == MEMORY_SENSITIVITY_RESTRICTED
        title = (
            f"[{row['status']}] ({MEMORY_SENSITIVITY_RESTRICTED})"
            if restricted
            else f"[{row['status']}] {row['key']}"
        )
        docs.append(
            (
                "memory",
                row["id"],
                title,
                row["key"] + "\n" + row["value_md"],
            )
        )
    return docs


def _restricted_memory_ids(conn: sqlite3.Connection) -> set[int]:
    """The claims whose search snippets must be suppressed (M3.13).

    Read at RESULT time, never trusted from the index: the FTS table is
    derived state that a stale watermark could leave behind a `memory
    classify`, and a snippet suppressed by a stale index is a snippet not
    suppressed at all.
    """
    return {
        row["id"]
        for row in conn.execute(
            "SELECT id FROM memory WHERE sensitivity = ?",
            (MEMORY_SENSITIVITY_RESTRICTED,),
        )
    }


def _suppress_restricted(conn: sqlite3.Connection, results: list[dict]) -> list[dict]:
    """Blank the title and snippet of every restricted memory hit.

    The hit itself stays: the id, the type and the fact that it matched are
    administrative metadata. Its text is not.
    """
    restricted = _restricted_memory_ids(conn)
    if not restricted:
        return results
    placeholder = f"({MEMORY_SENSITIVITY_RESTRICTED})"
    for result in results:
        if result["type"] != "memory":
            continue
        if ids.parse_id(result["id"], "memory") in restricted:
            result["title"] = placeholder
            result["snippet"] = placeholder
    return results


# ---------------------------------------------------------------------------
# FTS5 backend

def _events_watermark(conn: sqlite3.Connection) -> str:
    return str(
        conn.execute("SELECT COALESCE(MAX(id), 0) AS n FROM events").fetchone()["n"]
    )


def _index_stale(conn: sqlite3.Connection, current: str) -> bool:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (FTS_TABLE,),
    ).fetchone()
    if exists is None:
        return True  # dropped (allowed at any time) → rebuild
    return db.get_meta(conn, WATERMARK_KEY) != current


def _refresh_index(conn: sqlite3.Connection) -> None:
    current = _events_watermark(conn)
    if not _index_stale(conn, current):
        return
    with conn:  # derived state only: index + watermark, no ledger rows
        conn.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS {FTS_TABLE} "
            "USING fts5(entity UNINDEXED, entity_id UNINDEXED, "
            "title UNINDEXED, body)"
        )
        conn.execute(f"DELETE FROM {FTS_TABLE}")
        conn.executemany(
            f"INSERT INTO {FTS_TABLE} (entity, entity_id, title, body) "
            "VALUES (?, ?, ?, ?)",
            _documents(conn),
        )
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
            (WATERMARK_KEY, current),
        )


def _fts_match_expression(query: str) -> str:
    """Quote every whitespace-separated term so user text can never reach
    the FTS5 query parser as syntax; terms are implicitly ANDed."""
    return " ".join(
        '"' + term.replace('"', '""') + '"' for term in query.split()
    )


def _fts_search(conn: sqlite3.Connection, query: str) -> list[dict]:
    _refresh_index(conn)
    try:
        rows = conn.execute(
            f"SELECT entity, entity_id, title, "
            f"snippet({FTS_TABLE}, 3, '', '', '…', 12) AS snip "
            f"FROM {FTS_TABLE} WHERE {FTS_TABLE} MATCH ? "
            "ORDER BY rank, entity, entity_id",
            (_fts_match_expression(query),),
        ).fetchall()
    except sqlite3.OperationalError:
        raise AosError(
            f"Search query {query!r} could not be parsed by the FTS5 "
            "backend. Use plain words."
        )
    return [
        {
            "type": row["entity"],
            "id": ids.render_id(row["entity"], row["entity_id"]),
            "title": row["title"],
            "snippet": " ".join(row["snip"].split()),
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# LIKE fallback (no FTS5 in this SQLite build)

def _like_snippet(body: str, term: str) -> str:
    """A deterministic context window around the first hit — the fallback's
    stand-in for FTS5's snippet(). The hit is located case-insensitively on
    the ORIGINAL string (str.lower() can change lengths — e.g. 'İ' — and a
    position found in the lowered copy would desync the slice); exotic
    matches regex can't see fall back to a window from the start."""
    match = re.search(re.escape(term), body, re.IGNORECASE)
    pos = match.start() if match else 0
    hit_len = len(match.group(0)) if match else 0
    start = max(0, pos - _SNIPPET_WINDOW)
    end = min(len(body), pos + hit_len + _SNIPPET_WINDOW)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(body) else ""
    return prefix + " ".join(body[start:end].split()) + suffix


def _like_search(conn: sqlite3.Connection, query: str) -> list[dict]:
    """Case-insensitive substring conjunction (each term must appear, LIKE
    '%term%' semantics) over the same documents the index would hold.
    Simple ordering: source order — entity type, then ascending id."""
    terms = query.split()
    results = []
    for entity, entity_id, title, body in _documents(conn):
        lowered = body.lower()
        if all(term.lower() in lowered for term in terms):
            results.append(
                {
                    "type": entity,
                    "id": ids.render_id(entity, entity_id),
                    "title": title,
                    "snippet": _like_snippet(body, terms[0]),
                }
            )
    return results


# ---------------------------------------------------------------------------

def search(conn: sqlite3.Connection, query: str) -> dict:
    query = query.strip()
    if not query:
        raise AosError("Search query must not be empty.")
    if fts5_available():
        backend = "fts5"
        results = _fts_search(conn, query)
    else:
        backend = "like"
        results = _like_search(conn, query)
    # One suppression pass over BOTH backends' results, at the single point
    # where they converge (M3.13). Suppressing inside each backend would mean
    # two implementations of one rule, and the fallback is exactly the path
    # that gets tested least.
    return {
        "query": query,
        "backend": backend,
        "results": _suppress_restricted(conn, results),
    }
