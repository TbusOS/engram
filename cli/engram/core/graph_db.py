"""SQLite-backed asset index — the `graph.db` from DESIGN §3.2.

``graph.db`` is a **cache derived from the filesystem plus journal files**. It
is not authoritative: if deleted or corrupted, ``engram graph rebuild`` (not
implemented in T-14) regenerates it from the on-disk sources. What this module
owns:

- Opening a connection with the standard pragmas (WAL mode, synchronous NORMAL,
  foreign keys ON).
- Applying the versioned schema from DESIGN §3.2 exactly once and recording the
  applied version in ``schema_version``.
- A forward-only migration runner keyed by ``SCHEMA_VERSION`` so v0.3 can add
  v2, v3, etc. without a flag-day rewrite.
- A minimal typed insert/read helper for ``assets`` so early integration tests
  can exercise the schema end-to-end. Heavier table-specific helpers (inbox,
  consistency proposals, subscriptions, usage events) land with the consuming
  commands in later tasks (T-19 memory, T-30 pool, T-49 consistency, T-50
  inbox).

Everything else — referenced edges, consistency proposals, usage events — is
accessed directly through the raw ``sqlite3.Connection`` yielded by
:func:`open_graph_db` until there is a consumer that benefits from a wrapper.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

__all__ = [
    "SCHEMA_VERSION",
    "AssetRow",
    "get_asset",
    "get_schema_version",
    "insert_asset",
    "list_asset_ids",
    "open_graph_db",
]

SCHEMA_VERSION = 1

# Full DDL from DESIGN §3.2. `references` is a SQL reserved word in many
# dialects (SQLite accepts it bare, but using `references_` keeps portability
# with any future non-SQLite read-only viewer). `IF NOT EXISTS` makes each
# statement idempotent so a partial crash mid-migration can be recovered by
# re-running.
_SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS assets (
    id          TEXT PRIMARY KEY,
    scope       TEXT NOT NULL,
    scope_name  TEXT,
    subtype     TEXT NOT NULL,
    kind        TEXT NOT NULL,
    path        TEXT NOT NULL UNIQUE,
    lifecycle_state TEXT NOT NULL,
    created     TEXT,
    updated     TEXT,
    enforcement TEXT,
    confidence_score REAL DEFAULT 0.0,
    size_bytes  INTEGER,
    sha256      TEXT
);
CREATE INDEX IF NOT EXISTS idx_assets_scope     ON assets(scope, scope_name);
CREATE INDEX IF NOT EXISTS idx_assets_kind      ON assets(kind);
CREATE INDEX IF NOT EXISTS idx_assets_lifecycle ON assets(lifecycle_state);

CREATE TABLE IF NOT EXISTS references_ (
    from_id TEXT NOT NULL,
    to_id   TEXT NOT NULL,
    kind    TEXT NOT NULL,
    created TEXT,
    PRIMARY KEY (from_id, to_id, kind),
    FOREIGN KEY (from_id) REFERENCES assets(id)
);

CREATE TABLE IF NOT EXISTS subscriptions (
    subscriber_scope  TEXT NOT NULL,
    pool_name         TEXT NOT NULL,
    subscribed_at     TEXT NOT NULL,
    propagation_mode  TEXT NOT NULL,
    pinned_revision   TEXT,
    last_synced_rev   TEXT,
    PRIMARY KEY (subscriber_scope, pool_name)
);

CREATE TABLE IF NOT EXISTS inbox_messages (
    message_id  TEXT PRIMARY KEY,
    from_repo   TEXT NOT NULL,
    to_repo     TEXT NOT NULL,
    intent      TEXT NOT NULL,
    status      TEXT NOT NULL,
    severity    TEXT,
    created     TEXT NOT NULL,
    path        TEXT NOT NULL,
    dedup_key   TEXT
);
CREATE INDEX IF NOT EXISTS idx_inbox_to_status ON inbox_messages(to_repo, status);

CREATE TABLE IF NOT EXISTS consistency_proposals (
    proposal_id     TEXT PRIMARY KEY,
    class           TEXT NOT NULL,
    severity        TEXT NOT NULL,
    involved_assets TEXT,
    status          TEXT NOT NULL,
    detected_at     TEXT NOT NULL,
    resolved_at     TEXT
);

CREATE TABLE IF NOT EXISTS usage_events (
    event_id   TEXT PRIMARY KEY,
    asset_id   TEXT NOT NULL,
    event_type TEXT NOT NULL,
    task_hash  TEXT,
    outcome    TEXT,
    timestamp  TEXT NOT NULL,
    FOREIGN KEY (asset_id) REFERENCES assets(id)
);
CREATE INDEX IF NOT EXISTS idx_usage_asset ON usage_events(asset_id, timestamp);

CREATE TABLE IF NOT EXISTS schema_version (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
"""

_MIGRATIONS: dict[int, str] = {
    1: _SCHEMA_V1,
}


@dataclass(frozen=True, slots=True)
class AssetRow:
    """Typed row for inserting into the ``assets`` table.

    Mirrors the schema in DESIGN §3.2. Fields with SQL defaults / NULL-allowed
    columns have Python defaults of the equivalent ``None`` or ``0.0`` so
    callers can insert a minimal asset with only the hard-required keys.
    """

    id: str
    scope: str
    scope_name: str | None
    subtype: str
    kind: str
    path: str
    lifecycle_state: str
    sha256: str | None
    created: str | None = None
    updated: str | None = None
    enforcement: str | None = None
    confidence_score: float = 0.0
    size_bytes: int | None = None


@contextmanager
def open_graph_db(path: Path) -> Iterator[sqlite3.Connection]:
    """Open ``graph.db`` with the DESIGN §3.2 pragmas, applying the schema if needed.

    Creates parent directories as required; always yields a connection with
    ``row_factory = sqlite3.Row`` so callers can index columns by name. Closes
    the connection on context exit even if the schema migration failed.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.row_factory = sqlite3.Row
        conn.executescript(
            "PRAGMA journal_mode=WAL;PRAGMA synchronous=NORMAL;PRAGMA foreign_keys=ON;"
        )
        _migrate(conn)
        yield conn
    finally:
        conn.close()


def get_schema_version(conn: sqlite3.Connection) -> int:
    """Return the highest applied schema version, or 0 if no migration has run."""
    has_table = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
    ).fetchone()
    if has_table is None:
        return 0
    row = conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
    return int(row["v"] or 0)


def _migrate(conn: sqlite3.Connection) -> None:
    current = get_schema_version(conn)
    if current > SCHEMA_VERSION:
        raise RuntimeError(
            f"graph.db schema_version={current} is newer than this tool supports "
            f"({SCHEMA_VERSION}); upgrade engram or run against a different store"
        )
    while current < SCHEMA_VERSION:
        target = current + 1
        if target not in _MIGRATIONS:
            raise RuntimeError(f"no migration script registered for schema version {target}")
        conn.executescript(_MIGRATIONS[target])
        conn.execute(
            "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
            (target, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        current = target


def insert_asset(conn: sqlite3.Connection, asset: AssetRow) -> None:
    """Insert an asset row. Raises :class:`sqlite3.IntegrityError` on duplicate id or path."""
    data = asdict(asset)
    columns = ", ".join(data.keys())
    placeholders = ", ".join(f":{k}" for k in data)
    conn.execute(f"INSERT INTO assets ({columns}) VALUES ({placeholders})", data)
    conn.commit()


def get_asset(conn: sqlite3.Connection, asset_id: str) -> sqlite3.Row | None:
    row: sqlite3.Row | None = conn.execute(
        "SELECT * FROM assets WHERE id = ?", (asset_id,)
    ).fetchone()
    return row


def list_asset_ids(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("SELECT id FROM assets ORDER BY id").fetchall()
    return [str(r["id"]) for r in rows]
