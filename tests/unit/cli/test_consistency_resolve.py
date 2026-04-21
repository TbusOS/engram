"""T-49 tests: consistency resolve actions.

Six actions map directly to SPEC §1.2 principle 4 ("never auto-delete"):
every action is *opt-in*. By default, every ``apply_resolution`` call
is a dry-run; only with ``consent=True`` does it touch disk.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import engram.cli  # noqa: F401  # import order — see test_consistency.py
from engram.commands.init import init_project
from engram.consistency import Resolution, ResolutionKind
from engram.consistency.resolve import (
    ApplyResult,
    apply_resolution,
)


def _write_local(root: Path, filename: str, body: str = "body") -> Path:
    local = root / ".memory" / "local"
    local.mkdir(parents=True, exist_ok=True)
    path = local / filename
    path.write_text(
        "---\n"
        f"name: {filename[:-3]}\n"
        "description: x\n"
        "type: user\n"
        "scope: project\n"
        f"---\n\n{body}\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = tmp_path / "proj"
    init_project(root)
    return root


# ------------------------------------------------------------------
# Dry-run is the default
# ------------------------------------------------------------------


def test_apply_resolution_is_dry_run_by_default(store: Path) -> None:
    _write_local(store, "user_alpha.md", "alpha body")
    before = (store / ".memory" / "local" / "user_alpha.md").read_bytes()
    result = apply_resolution(
        store,
        Resolution(
            kind=ResolutionKind.ARCHIVE,
            target="local/user_alpha",
            detail="drop it",
        ),
    )
    after = (store / ".memory" / "local" / "user_alpha.md").read_bytes()
    assert before == after
    assert isinstance(result, ApplyResult)
    assert result.applied is False


# ------------------------------------------------------------------
# ARCHIVE
# ------------------------------------------------------------------


def test_archive_moves_asset_to_user_archive(store: Path) -> None:
    _write_local(store, "user_alpha.md")
    result = apply_resolution(
        store,
        Resolution(kind=ResolutionKind.ARCHIVE, target="local/user_alpha"),
        consent=True,
    )
    assert result.applied is True
    assert not (store / ".memory" / "local" / "user_alpha.md").exists()
    home = Path.home() if Path.home().exists() else Path.cwd()  # not used
    import os

    archive_root = Path(os.environ["HOME"]) / ".engram" / "archive"
    assert archive_root.is_dir()
    assert any(archive_root.rglob("user_alpha.md"))


def test_archive_refuses_nonexistent_target(store: Path) -> None:
    result = apply_resolution(
        store,
        Resolution(kind=ResolutionKind.ARCHIVE, target="local/nowhere"),
        consent=True,
    )
    assert result.applied is False
    assert "not found" in result.detail.lower()


# ------------------------------------------------------------------
# DISMISS
# ------------------------------------------------------------------


def test_dismiss_records_decision_without_touching_asset(store: Path) -> None:
    path = _write_local(store, "user_alpha.md", "original")
    result = apply_resolution(
        store,
        Resolution(
            kind=ResolutionKind.DISMISS,
            target="local/user_alpha",
            detail="intentional override",
        ),
        consent=True,
    )
    assert result.applied is True
    assert path.read_text(encoding="utf-8").endswith("original\n")

    import os

    journal = (
        Path(os.environ["HOME"]) / ".engram" / "journal" / "consistency.jsonl"
    )
    events = [json.loads(line) for line in journal.read_text().splitlines()]
    assert any(e["action"] == "dismiss" for e in events)


# ------------------------------------------------------------------
# ESCALATE
# ------------------------------------------------------------------


def test_escalate_writes_queue_entry(store: Path) -> None:
    _write_local(store, "feedback_alpha.md")
    result = apply_resolution(
        store,
        Resolution(
            kind=ResolutionKind.ESCALATE,
            target="local/feedback_alpha",
            related=("local/feedback_beta",),
            detail="ask platform-security",
        ),
        consent=True,
    )
    assert result.applied is True

    import os

    queue_dir = Path(os.environ["HOME"]) / ".engram" / "escalations"
    assert queue_dir.is_dir()
    entries = list(queue_dir.glob("*.md"))
    assert len(entries) == 1
    text = entries[0].read_text(encoding="utf-8")
    assert "feedback_alpha" in text
    assert "feedback_beta" in text
    assert "ask platform-security" in text


# ------------------------------------------------------------------
# SUPERSEDE
# ------------------------------------------------------------------


def test_supersede_archives_superseded_and_patches_successor(
    store: Path,
) -> None:
    _write_local(store, "user_old.md", "old content")
    _write_local(store, "user_new.md", "new content")

    result = apply_resolution(
        store,
        Resolution(
            kind=ResolutionKind.SUPERSEDE,
            target="local/user_new",
            related=("local/user_old",),
            detail="new replaces old",
        ),
        consent=True,
    )
    assert result.applied is True

    # Old is archived.
    assert not (store / ".memory" / "local" / "user_old.md").exists()
    # New file carries a supersedes pointer.
    new_text = (store / ".memory" / "local" / "user_new.md").read_text(encoding="utf-8")
    assert "supersedes:" in new_text
    assert "local/user_old" in new_text


def test_supersede_refuses_without_related(store: Path) -> None:
    _write_local(store, "user_new.md")
    result = apply_resolution(
        store,
        Resolution(
            kind=ResolutionKind.SUPERSEDE,
            target="local/user_new",
            related=(),
        ),
        consent=True,
    )
    assert result.applied is False


# ------------------------------------------------------------------
# MERGE
# ------------------------------------------------------------------


def test_merge_combines_bodies_and_archives_source(store: Path) -> None:
    _write_local(store, "user_a.md", "first block")
    _write_local(store, "user_b.md", "second block")

    result = apply_resolution(
        store,
        Resolution(
            kind=ResolutionKind.MERGE,
            target="local/user_a",
            related=("local/user_b",),
        ),
        consent=True,
    )
    assert result.applied is True

    merged = (store / ".memory" / "local" / "user_a.md").read_text(encoding="utf-8")
    assert "first block" in merged
    assert "second block" in merged
    assert not (store / ".memory" / "local" / "user_b.md").exists()


# ------------------------------------------------------------------
# UPDATE — proposal-writer, never auto-patches
# ------------------------------------------------------------------


def test_update_writes_proposal_file_alongside_asset(store: Path) -> None:
    _write_local(store, "user_alpha.md", "original body")
    result = apply_resolution(
        store,
        Resolution(
            kind=ResolutionKind.UPDATE,
            target="local/user_alpha",
            detail="fix the broken link in line 4",
        ),
        consent=True,
    )
    assert result.applied is True

    # Original is untouched.
    original = (store / ".memory" / "local" / "user_alpha.md").read_text(encoding="utf-8")
    assert "original body" in original

    # Proposal dropped next to the asset.
    proposal = (
        store / ".memory" / "local" / "user_alpha.proposed.md"
    )
    assert proposal.is_file()
    text = proposal.read_text(encoding="utf-8")
    assert "fix the broken link in line 4" in text


# ------------------------------------------------------------------
# Invariant: every action emits a journal event
# ------------------------------------------------------------------


def test_every_applied_action_is_journaled(store: Path) -> None:
    import os

    _write_local(store, "user_alpha.md")
    _write_local(store, "user_beta.md")

    apply_resolution(
        store,
        Resolution(kind=ResolutionKind.DISMISS, target="local/user_alpha"),
        consent=True,
    )
    apply_resolution(
        store,
        Resolution(
            kind=ResolutionKind.ARCHIVE, target="local/user_beta"
        ),
        consent=True,
    )

    journal = (
        Path(os.environ["HOME"]) / ".engram" / "journal" / "consistency.jsonl"
    )
    events = [json.loads(line) for line in journal.read_text().splitlines()]
    actions = [e["action"] for e in events]
    assert "dismiss" in actions
    assert "archive" in actions
