"""T-14 tests for engram.core.graph_db — SQLite schema + pragmas + migrations."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from engram.core.graph_db import (
    SCHEMA_VERSION,
    AssetRow,
    get_asset,
    get_schema_version,
    insert_asset,
    list_asset_ids,
    open_graph_db,
)


EXPECTED_TABLES = {
    "assets",
    "references_",
    "subscriptions",
    "inbox_messages",
    "consistency_proposals",
    "usage_events",
    "schema_version",
}

EXPECTED_INDEXES = {
    "idx_assets_scope",
    "idx_assets_kind",
    "idx_assets_lifecycle",
    "idx_inbox_to_status",
    "idx_usage_asset",
}


def _list_tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {r["name"] for r in rows}


def _list_indexes(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {r["name"] for r in rows}


def _sample_asset(**overrides: object) -> AssetRow:
    defaults: dict[str, object] = {
        "id": "local/user_kernel_fluency",
        "scope": "user",
        "scope_name": None,
        "subtype": "user",
        "kind": "memory",
        "path": "user/user_kernel_fluency.md",
        "lifecycle_state": "active",
        "sha256": "abc123",
    }
    defaults.update(overrides)
    return AssetRow(**defaults)  # type: ignore[arg-type]


# ------------------------------------------------------------------
# Open + schema + pragmas
# ------------------------------------------------------------------


def test_open_creates_database_file(tmp_path: Path) -> None:
    db_path = tmp_path / "graph.db"
    with open_graph_db(db_path):
        pass
    assert db_path.exists()


def test_open_creates_parent_directories(tmp_path: Path) -> None:
    db_path = tmp_path / "a" / "b" / "graph.db"
    with open_graph_db(db_path):
        pass
    assert db_path.exists()


def test_open_enables_wal_mode(tmp_path: Path) -> None:
    with open_graph_db(tmp_path / "graph.db") as conn:
        row = conn.execute("PRAGMA journal_mode").fetchone()
    assert row[0].lower() == "wal"


def test_open_enables_foreign_keys(tmp_path: Path) -> None:
    with open_graph_db(tmp_path / "graph.db") as conn:
        row = conn.execute("PRAGMA foreign_keys").fetchone()
    assert row[0] == 1


def test_open_sets_synchronous_normal(tmp_path: Path) -> None:
    with open_graph_db(tmp_path / "graph.db") as conn:
        row = conn.execute("PRAGMA synchronous").fetchone()
    # 1 = NORMAL
    assert row[0] == 1


def test_all_expected_tables_created(tmp_path: Path) -> None:
    with open_graph_db(tmp_path / "graph.db") as conn:
        tables = _list_tables(conn)
    assert tables == EXPECTED_TABLES


def test_all_expected_indexes_created(tmp_path: Path) -> None:
    with open_graph_db(tmp_path / "graph.db") as conn:
        indexes = _list_indexes(conn)
    assert EXPECTED_INDEXES <= indexes


def test_schema_version_recorded(tmp_path: Path) -> None:
    with open_graph_db(tmp_path / "graph.db") as conn:
        assert get_schema_version(conn) == SCHEMA_VERSION


def test_reopen_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "graph.db"
    for _ in range(3):
        with open_graph_db(db_path) as conn:
            assert get_schema_version(conn) == SCHEMA_VERSION
            tables = _list_tables(conn)
    assert tables == EXPECTED_TABLES


def test_reopen_preserves_data(tmp_path: Path) -> None:
    db_path = tmp_path / "graph.db"
    with open_graph_db(db_path) as conn:
        insert_asset(conn, _sample_asset())
    with open_graph_db(db_path) as conn:
        assert get_asset(conn, "local/user_kernel_fluency") is not None


def test_schema_version_newer_than_supported_raises(tmp_path: Path) -> None:
    db_path = tmp_path / "graph.db"
    with open_graph_db(db_path):
        pass
    # Tamper: set a version that is beyond what the code knows about.
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
            (SCHEMA_VERSION + 99, "2099-01-01T00:00:00+00:00"),
        )
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(RuntimeError, match="newer"):
        with open_graph_db(db_path):
            pass


# ------------------------------------------------------------------
# Asset CRUD helpers
# ------------------------------------------------------------------


def test_insert_and_get_asset_roundtrip(tmp_path: Path) -> None:
    with open_graph_db(tmp_path / "graph.db") as conn:
        insert_asset(conn, _sample_asset())
        row = get_asset(conn, "local/user_kernel_fluency")
    assert row is not None
    assert row["id"] == "local/user_kernel_fluency"
    assert row["scope"] == "user"
    assert row["subtype"] == "user"
    assert row["kind"] == "memory"
    assert row["lifecycle_state"] == "active"
    assert row["confidence_score"] == 0.0


def test_get_asset_returns_none_when_absent(tmp_path: Path) -> None:
    with open_graph_db(tmp_path / "graph.db") as conn:
        assert get_asset(conn, "nope") is None


def test_list_asset_ids(tmp_path: Path) -> None:
    with open_graph_db(tmp_path / "graph.db") as conn:
        insert_asset(conn, _sample_asset(id="a", path="a.md"))
        insert_asset(conn, _sample_asset(id="b", path="b.md"))
        insert_asset(conn, _sample_asset(id="c", path="c.md"))
        ids = list_asset_ids(conn)
    assert set(ids) == {"a", "b", "c"}


def test_insert_duplicate_id_raises(tmp_path: Path) -> None:
    with open_graph_db(tmp_path / "graph.db") as conn:
        insert_asset(conn, _sample_asset(id="dup", path="dup.md"))
        with pytest.raises(sqlite3.IntegrityError):
            insert_asset(conn, _sample_asset(id="dup", path="dup2.md"))


def test_insert_duplicate_path_raises(tmp_path: Path) -> None:
    with open_graph_db(tmp_path / "graph.db") as conn:
        insert_asset(conn, _sample_asset(id="a", path="same.md"))
        with pytest.raises(sqlite3.IntegrityError):
            insert_asset(conn, _sample_asset(id="b", path="same.md"))


def test_insert_asset_stores_optional_fields(tmp_path: Path) -> None:
    with open_graph_db(tmp_path / "graph.db") as conn:
        insert_asset(
            conn,
            _sample_asset(
                created="2026-04-20",
                updated="2026-04-21",
                enforcement="mandatory",
                confidence_score=0.85,
                size_bytes=4096,
            ),
        )
        row = get_asset(conn, "local/user_kernel_fluency")
    assert row is not None
    assert row["created"] == "2026-04-20"
    assert row["updated"] == "2026-04-21"
    assert row["enforcement"] == "mandatory"
    assert row["confidence_score"] == pytest.approx(0.85)
    assert row["size_bytes"] == 4096


# ------------------------------------------------------------------
# Foreign key enforcement (references_)
# ------------------------------------------------------------------


def test_references_foreign_key_enforced(tmp_path: Path) -> None:
    """Inserting a reference whose from_id is not in assets must fail."""
    with open_graph_db(tmp_path / "graph.db") as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO references_ (from_id, to_id, kind) VALUES (?, ?, ?)",
                ("nonexistent-from", "also-nonexistent", "references"),
            )
            conn.commit()


def test_references_accepts_valid_edge(tmp_path: Path) -> None:
    with open_graph_db(tmp_path / "graph.db") as conn:
        insert_asset(conn, _sample_asset(id="a", path="a.md"))
        conn.execute(
            "INSERT INTO references_ (from_id, to_id, kind) VALUES (?, ?, ?)",
            ("a", "b", "references"),
        )
        conn.commit()
        count = conn.execute("SELECT COUNT(*) AS c FROM references_").fetchone()["c"]
    assert count == 1
