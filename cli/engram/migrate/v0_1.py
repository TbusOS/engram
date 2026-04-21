"""v0.1 → v0.2 migration (SPEC §13.4).

v0.1 projects have a flat ``.memory/*.md`` layout with no subdirectories and
no ``.engram/version`` marker. v0.2 introduces the ``local / pools /
workflows / kb`` subdirectories, the ``scope`` frontmatter field, and hard
enforcement on ``feedback`` / ``agent`` subtype metadata. Migration is a
local-only operation; no network, no git. SPEC contract:

- Pre-flight: backup the entire ``.memory/`` to ``.memory.pre-v0.2.backup/``.
- Move flat ``*.md`` files under ``local/``.
- Inject ``scope: project`` where absent.
- Add ``enforcement: default`` on ``feedback`` assets that lack it.
- Add a zero-state ``confidence`` block on ``agent`` assets that lack it.
- Preserve every unknown frontmatter field verbatim (SPEC §4.1 forward-compat).
- Regenerate ``MEMORY.md`` with the v0.2 hierarchical skeleton (§7.2).
- Write ``.engram/version = "0.2"``.
- Append one ``migration`` event to ``~/.engram/journal/migration.jsonl``.

Rollback consumes the backup and restores the pre-migration layout.
Re-running migrate after success is a no-op (idempotency invariant §13.4).
"""

from __future__ import annotations

import shutil
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import click
import yaml

from engram.commands.init import STORE_VERSION, _pools_toml_stub
from engram.core.fs import write_atomic
from engram.core.journal import append_event
from engram.core.paths import user_root

__all__ = [
    "BACKUP_DIRNAME",
    "detect_v0_1",
    "migration_journal_path",
    "plan_migration",
    "run_migration",
    "run_rollback",
]


BACKUP_DIRNAME = ".memory.pre-v0.2.backup"


# ------------------------------------------------------------------
# Detection
# ------------------------------------------------------------------


def detect_v0_1(project_root: Path) -> bool:
    """Return True iff ``project_root`` holds a v0.1-shaped store.

    Heuristics per SPEC §13.5: ``.memory/`` exists, there is no
    ``.engram/version`` file (v0.1 had no version marker) OR the version
    file says ``0.1``, and there are flat ``*.md`` files at the top of
    ``.memory/`` (v0.2 would put them under ``local/``).
    """
    memory = project_root / ".memory"
    version_file = project_root / ".engram" / "version"
    if not memory.is_dir():
        return False
    version = version_file.read_text(encoding="utf-8").strip() if version_file.is_file() else ""
    if version.startswith("0.2"):
        return False
    has_flat_md = any(p.is_file() and p.suffix == ".md" for p in memory.iterdir())
    has_local = (memory / "local").is_dir()
    return has_flat_md or not has_local


def _is_v0_2(project_root: Path) -> bool:
    version_file = project_root / ".engram" / "version"
    return version_file.is_file() and version_file.read_text(encoding="utf-8").strip().startswith(
        "0.2"
    )


# ------------------------------------------------------------------
# Planning (dry-run)
# ------------------------------------------------------------------


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Parse a v0.1 asset file. Returns (frontmatter_dict, body_text)."""
    if not text.startswith("---"):
        return {}, text
    # Find the closing --- delimiter.
    tail = text[4:] if text.startswith("---\n") else text[3:]
    parts = tail.split("\n---", 1)
    if len(parts) != 2:
        return {}, text
    yaml_text, body = parts
    data = yaml.safe_load(yaml_text) or {}
    if not isinstance(data, dict):
        return {}, text
    # Strip the leading newline after the closing ---.
    body = body.lstrip("\n")
    return data, body


def _fields_to_add(fm: dict[str, Any]) -> list[str]:
    """Return the list of frontmatter keys this migration would inject."""
    added: list[str] = []
    if "scope" not in fm:
        added.append("scope")
    mtype = fm.get("type")
    if mtype == "feedback" and "enforcement" not in fm:
        added.append("enforcement")
    if mtype == "agent" and "confidence" not in fm:
        added.append("confidence")
    return added


def plan_migration(project_root: Path) -> dict[str, Any]:
    """Compute the migration plan without touching disk.

    Returned shape::

        {"mode": "dry-run", "project_root": str, "moves": [
          {"from": ".memory/user_foo.md", "to": ".memory/local/user_foo.md",
           "type": "user", "fields_added": ["scope"]},
          ...
        ]}
    """
    memory = project_root / ".memory"
    moves: list[dict[str, Any]] = []
    for md in sorted(memory.glob("*.md")):
        if not md.is_file() or md.name == "MEMORY.md":
            continue
        text = md.read_text(encoding="utf-8")
        fm, _body = _split_frontmatter(text)
        moves.append(
            {
                "from": f".memory/{md.name}",
                "to": f".memory/local/{md.name}",
                "type": fm.get("type", "?"),
                "fields_added": _fields_to_add(fm),
            }
        )
    return {
        "mode": "dry-run",
        "project_root": str(project_root.resolve()),
        "moves": moves,
        "backup_to": f"{BACKUP_DIRNAME}/",
    }


# ------------------------------------------------------------------
# Live migration
# ------------------------------------------------------------------


def _render_asset(fm: dict[str, Any], body: str) -> str:
    yaml_block = yaml.dump(fm, sort_keys=False, allow_unicode=True, default_flow_style=False)
    tail = body if body.endswith("\n") else body + "\n"
    return f"---\n{yaml_block}---\n\n{tail}"


def _upgrade_frontmatter(fm: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Apply SPEC §13.4 default injections. Preserves every existing key."""
    added: list[str] = []
    fm = dict(fm)  # defensive copy
    if "scope" not in fm:
        fm["scope"] = "project"
        added.append("scope")
    if fm.get("type") == "feedback" and "enforcement" not in fm:
        fm["enforcement"] = "default"
        added.append("enforcement")
    if fm.get("type") == "agent" and "confidence" not in fm:
        # SPEC §13.4 says `confidence: {}` but the parser rejects an empty block
        # (§4.8). Per SPEC §13.7 rule 6 ("additive default = least-surprising value"),
        # use a zero-state block that the validator accepts.
        fm["confidence"] = {
            "validated_count": 0,
            "contradicted_count": 0,
            "last_validated": date.today().isoformat(),
            "usage_count": 0,
        }
        added.append("confidence")
    return fm, added


def _build_memory_md(project_name: str, local_dir: Path) -> str:
    """Regenerate MEMORY.md with migrated assets slotted into the right sections.

    Categorisation (SPEC §7.2):
    - ``type: user`` → ## Identity
    - ``type: feedback`` → ## Always-on rules
    - everything else (project / reference / agent / workflow_ptr) → ## Topics
    """
    identity: list[str] = []
    rules: list[str] = []
    topics: list[str] = []
    for md in sorted(local_dir.glob("*.md")):
        text = md.read_text(encoding="utf-8")
        fm, _ = _split_frontmatter(text)
        name = fm.get("name", md.stem)
        desc = fm.get("description", "")
        entry = f"- [{name}](local/{md.name}) — {desc}"
        mtype = fm.get("type")
        if mtype == "user":
            identity.append(entry)
        elif mtype == "feedback":
            rules.append(entry)
        else:
            topics.append(entry)

    from engram.commands.init import STORE_VERSION as _V

    def _section(heading: str, entries: list[str], comment: str) -> str:
        if entries:
            return f"{heading}\n\n" + "\n".join(entries) + "\n"
        return f"{heading}\n\n<!-- {comment} -->\n"

    return (
        "# MEMORY.md\n"
        "\n"
        f"<!-- engram v{_V} landing index for {project_name}. "
        "See SPEC.md §7. Regenerated by migrate from v0.1. -->\n"
        "\n"
        + _section("## Identity", identity, "User profile + always-loaded identity facts.")
        + "\n"
        + _section(
            "## Always-on rules",
            rules,
            "enforcement=mandatory / default feedback rules.",
        )
        + "\n"
        + _section(
            "## Topics",
            topics,
            "Topic sub-indexes plus high-frequency inline items.",
        )
        + "\n"
        + _section(
            "## Subscribed pools",
            [],
            "One line per subscribed pool; written by `engram pool subscribe`.",
        )
        + "\n"
        + _section("## Recently added", [], "Last ~5 assets added, newest first.")
    )


def migration_journal_path() -> Path:
    """``~/.engram/journal/migration.jsonl`` — append-only migration record."""
    return user_root() / "journal" / "migration.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def run_migration(project_root: Path) -> dict[str, Any]:
    """Execute the SPEC §13.4 migration steps. Returns a result summary."""
    if _is_v0_2(project_root):
        return {"already_v0_2": True, "project_root": str(project_root.resolve())}

    memory = project_root / ".memory"
    if not memory.is_dir():
        raise click.ClickException(f"no .memory/ at {project_root}; nothing to migrate")

    backup = project_root / BACKUP_DIRNAME
    if backup.exists():
        raise click.ClickException(
            f"backup {backup} already exists — roll back or remove it before re-running"
        )

    # Step 2: backup the entire .memory/ tree verbatim.
    shutil.copytree(memory, backup, symlinks=True)

    # Step 3: make the v0.2 subdirectory skeleton.
    for sub in ("local", "pools", "workflows", "kb"):
        (memory / sub).mkdir(parents=True, exist_ok=True)

    # Step 4: move + upgrade every flat .md file.
    moves: list[dict[str, Any]] = []
    fields_added_total = 0
    for md in sorted(memory.glob("*.md")):
        if not md.is_file() or md.name == "MEMORY.md":
            continue
        text = md.read_text(encoding="utf-8")
        fm, body = _split_frontmatter(text)
        upgraded, added = _upgrade_frontmatter(fm)
        dest = memory / "local" / md.name
        write_atomic(dest, _render_asset(upgraded, body))
        md.unlink()
        moves.append(
            {
                "from": f".memory/{md.name}",
                "to": f".memory/local/{md.name}",
                "type": fm.get("type", "?"),
                "fields_added": added,
            }
        )
        fields_added_total += len(added)

    # Step 7: regenerate MEMORY.md with migrated assets indexed (so `validate`
    # does not emit E-IDX-002 on a freshly migrated store). The v0.1 MEMORY.md
    # is preserved inside the backup.
    old_memory_md = memory / "MEMORY.md"
    if old_memory_md.is_file():
        old_memory_md.unlink()
    project_name = project_root.resolve().name
    write_atomic(memory / "MEMORY.md", _build_memory_md(project_name, memory / "local"))
    if not (memory / "pools.toml").is_file():
        write_atomic(memory / "pools.toml", _pools_toml_stub())

    # Step 8: version marker.
    engram_dir = project_root / ".engram"
    engram_dir.mkdir(parents=True, exist_ok=True)
    write_atomic(engram_dir / "version", f"{STORE_VERSION}\n")

    # Step 9: journal record.
    record = {
        "event": "migration",
        "from_version": "0.1",
        "to_version": STORE_VERSION,
        "timestamp": _now_iso(),
        "assets_moved": len(moves),
        "fields_added": fields_added_total,
        "backup_path": f"{BACKUP_DIRNAME}/",
        "project_root": str(project_root.resolve()),
    }
    append_event(migration_journal_path(), record)

    return {
        "mode": "live",
        "already_v0_2": False,
        "project_root": str(project_root.resolve()),
        "moves": moves,
        "assets_moved": len(moves),
        "fields_added": fields_added_total,
        "backup_path": str(backup),
    }


# ------------------------------------------------------------------
# Rollback
# ------------------------------------------------------------------


def run_rollback(project_root: Path) -> dict[str, Any]:
    """Restore ``.memory/`` from the backup and remove the v0.2 markers."""
    backup = project_root / BACKUP_DIRNAME
    if not backup.is_dir():
        raise click.ClickException(
            f"no backup found at {backup}; rollback is a one-time escape hatch"
        )
    memory = project_root / ".memory"
    if memory.exists():
        shutil.rmtree(memory)
    shutil.move(str(backup), str(memory))

    version_file = project_root / ".engram" / "version"
    if version_file.is_file():
        version_file.unlink()
    # If .engram/ now only held the version file, remove the empty dir.
    engram_dir = project_root / ".engram"
    if engram_dir.is_dir() and not any(engram_dir.iterdir()):
        engram_dir.rmdir()

    return {
        "mode": "rollback",
        "project_root": str(project_root.resolve()),
        "restored_from": str(backup),
    }
