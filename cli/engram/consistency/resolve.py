"""Six resolve actions — the apply side of the Consistency Engine (T-49).

SPEC §1.2 principle 4 — *never auto-delete* — maps directly to the
calling contract of this module: every function defaults to
``consent=False`` which is a dry-run. The operator (or ``engram
review`` after explicit user confirmation) must set ``consent=True``
to touch disk. An "apply" call that was actually a dry-run returns
an :class:`ApplyResult` with ``applied=False`` and a ``detail``
describing what *would* have changed, so the caller can preview in
the UI.

Each action also journals a single event to
``~/.engram/journal/consistency.jsonl`` for auditability. A human
reading that file later can reconstruct every consistency decision
the store has seen.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from engram.consistency.types import Resolution, ResolutionKind
from engram.core.fs import write_atomic
from engram.core.journal import append_event
from engram.core.paths import memory_dir, user_root

__all__ = [
    "ApplyResult",
    "FileChange",
    "apply_resolution",
]


@dataclass(frozen=True, slots=True)
class FileChange:
    kind: str                # "created" | "modified" | "removed" | "moved"
    path: str                # relative to store_root
    note: str = ""


@dataclass(frozen=True, slots=True)
class ApplyResult:
    kind: ResolutionKind
    target: str
    applied: bool
    changes: tuple[FileChange, ...]
    detail: str


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _asset_path(store_root: Path, asset_id: str) -> Path:
    """Resolve ``local/user_foo`` → ``<store>/.memory/local/user_foo.md``."""
    if not asset_id.startswith("local/"):
        # Upper-scope assets aren't on disk in this store; resolve is a no-op
        # at this layer (the scope's own maintainer applies resolution there).
        return memory_dir(store_root) / asset_id
    return memory_dir(store_root) / f"{asset_id}.md"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _journal(
    action: str,
    resolution: Resolution,
    store_root: Path,
    applied: bool,
    extra: dict[str, object] | None = None,
) -> None:
    payload: dict[str, object] = {
        "event": "consistency-resolve",
        "action": action,
        "target": resolution.target,
        "related": list(resolution.related),
        "applied": applied,
        "timestamp": _now_iso(),
        "store_root": str(store_root.resolve()),
    }
    if extra:
        payload.update(extra)
    append_event(user_root() / "journal" / "consistency.jsonl", payload)


def _archive_destination(asset_id: str) -> Path:
    """Return the full target path under ``~/.engram/archive/<date>/<name>``."""
    date_bucket = datetime.now(timezone.utc).strftime("%Y-%m")
    leaf = asset_id.split("/")[-1] + ".md"
    return user_root() / "archive" / date_bucket / leaf


# ------------------------------------------------------------------
# ARCHIVE
# ------------------------------------------------------------------


def _apply_archive(
    store_root: Path, resolution: Resolution, *, consent: bool
) -> ApplyResult:
    src = _asset_path(store_root, resolution.target)
    if not src.is_file():
        return ApplyResult(
            kind=resolution.kind,
            target=resolution.target,
            applied=False,
            changes=(),
            detail=f"archive target not found: {src}",
        )

    dest = _archive_destination(resolution.target)

    if not consent:
        return ApplyResult(
            kind=resolution.kind,
            target=resolution.target,
            applied=False,
            changes=(FileChange("moved", resolution.target, f"would move to {dest}"),),
            detail=f"dry-run: {src} would move to {dest}",
        )

    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dest))
    _journal(
        "archive",
        resolution,
        store_root,
        applied=True,
        extra={"archive_path": str(dest)},
    )
    return ApplyResult(
        kind=resolution.kind,
        target=resolution.target,
        applied=True,
        changes=(
            FileChange("moved", resolution.target, f"archived to {dest}"),
        ),
        detail=f"archived {resolution.target} to {dest}",
    )


# ------------------------------------------------------------------
# DISMISS
# ------------------------------------------------------------------


def _apply_dismiss(
    store_root: Path, resolution: Resolution, *, consent: bool
) -> ApplyResult:
    if not consent:
        return ApplyResult(
            kind=resolution.kind,
            target=resolution.target,
            applied=False,
            changes=(),
            detail=f"dry-run: would record dismissal of {resolution.target}",
        )
    _journal("dismiss", resolution, store_root, applied=True)
    # Dismissing a Consistency proposal = "user looked at this asset and
    # decided it was correct after all" → false_positive_dismissed signal
    # per SPEC §11.4 amend (T-172).
    _emit_consistency_event(
        store_root,
        resolution.target,
        evidence_kind_name="false_positive_dismissed",
        event_type_name="validated",
    )
    return ApplyResult(
        kind=resolution.kind,
        target=resolution.target,
        applied=True,
        changes=(),
        detail="dismissed — no file change, decision logged",
    )


def _emit_consistency_event(
    store_root: Path,
    asset_id: str,
    *,
    evidence_kind_name: str,
    event_type_name: str,
) -> None:
    """Append one usage event tagged by the Consistency Engine.

    Local import to avoid widening the module's import surface, and
    swallow exceptions — observability MUST NOT break the user's
    consistency apply call.
    """
    try:
        from engram.usage import (  # noqa: PLC0415
            ActorType,
            EventType,
            EvidenceKind,
            UsageEvent,
            append_usage_event,
            derive_task_hash,
        )

        append_usage_event(
            UsageEvent(
                asset_uri=asset_id,
                task_hash=derive_task_hash(cwd=store_root),
                event_type=EventType(event_type_name),
                actor_type=ActorType.CONSISTENCY_ENGINE,
                evidence_kind=EvidenceKind(evidence_kind_name),
            )
        )
    except Exception:  # noqa: BLE001
        pass


# ------------------------------------------------------------------
# ESCALATE
# ------------------------------------------------------------------


_SAFE_SLUG_RE = re.compile(r"[^a-zA-Z0-9._-]+")


def _apply_escalate(
    store_root: Path, resolution: Resolution, *, consent: bool
) -> ApplyResult:
    queue_dir = user_root() / "escalations"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    leaf = _SAFE_SLUG_RE.sub("_", resolution.target)
    entry = queue_dir / f"{stamp}-{leaf}.md"

    if not consent:
        return ApplyResult(
            kind=resolution.kind,
            target=resolution.target,
            applied=False,
            changes=(
                FileChange("created", resolution.target, f"would create {entry}"),
            ),
            detail=f"dry-run: would enqueue escalation at {entry}",
        )

    queue_dir.mkdir(parents=True, exist_ok=True)
    related_lines = "\n".join(f"- {r}" for r in resolution.related) or "- (none)"
    body = (
        f"# Escalation — {resolution.target}\n"
        f"\n"
        f"- target: `{resolution.target}`\n"
        f"- related:\n{related_lines}\n"
        f"- detail: {resolution.detail}\n"
        f"- enqueued: {_now_iso()}\n"
    )
    write_atomic(entry, body)
    _journal(
        "escalate",
        resolution,
        store_root,
        applied=True,
        extra={"queue_entry": str(entry)},
    )
    return ApplyResult(
        kind=resolution.kind,
        target=resolution.target,
        applied=True,
        changes=(FileChange("created", str(entry)),),
        detail=f"escalated — queued at {entry}",
    )


# ------------------------------------------------------------------
# SUPERSEDE
# ------------------------------------------------------------------


def _inject_supersedes(asset_text: str, superseded: str) -> str:
    """Insert a ``supersedes: <id>`` line into the frontmatter block."""
    if not asset_text.startswith("---\n"):
        return asset_text
    parts = asset_text[4:].split("\n---", 1)
    if len(parts) != 2:
        return asset_text
    fm_text, body = parts
    if re.search(r"(?m)^supersedes:\s*", fm_text):
        # Idempotent if already set.
        fm_text = re.sub(
            r"(?m)^supersedes:.*$", f"supersedes: {superseded}", fm_text
        )
    else:
        fm_text = fm_text.rstrip("\n") + f"\nsupersedes: {superseded}\n"
    return f"---\n{fm_text}\n---{body}"


def _apply_supersede(
    store_root: Path, resolution: Resolution, *, consent: bool
) -> ApplyResult:
    if not resolution.related:
        return ApplyResult(
            kind=resolution.kind,
            target=resolution.target,
            applied=False,
            changes=(),
            detail="supersede requires `related=(<superseded_id>,)`",
        )
    superseded_id = resolution.related[0]
    target_path = _asset_path(store_root, resolution.target)
    superseded_path = _asset_path(store_root, superseded_id)
    if not target_path.is_file():
        return ApplyResult(
            kind=resolution.kind,
            target=resolution.target,
            applied=False,
            changes=(),
            detail=f"successor not found: {target_path}",
        )
    if not superseded_path.is_file():
        return ApplyResult(
            kind=resolution.kind,
            target=resolution.target,
            applied=False,
            changes=(),
            detail=f"superseded asset not found: {superseded_path}",
        )

    if not consent:
        return ApplyResult(
            kind=resolution.kind,
            target=resolution.target,
            applied=False,
            changes=(
                FileChange("modified", resolution.target, "would add supersedes:"),
                FileChange("moved", superseded_id, "would archive superseded"),
            ),
            detail=f"dry-run: {resolution.target} would supersede {superseded_id}",
        )

    new_text = _inject_supersedes(
        target_path.read_text(encoding="utf-8"), superseded_id
    )
    write_atomic(target_path, new_text)

    dest = _archive_destination(superseded_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(superseded_path), str(dest))

    _journal(
        "supersede",
        resolution,
        store_root,
        applied=True,
        extra={"archive_path": str(dest)},
    )
    return ApplyResult(
        kind=resolution.kind,
        target=resolution.target,
        applied=True,
        changes=(
            FileChange("modified", resolution.target, "added supersedes:"),
            FileChange("moved", superseded_id, f"archived to {dest}"),
        ),
        detail=f"{resolution.target} now supersedes {superseded_id}",
    )


# ------------------------------------------------------------------
# MERGE
# ------------------------------------------------------------------


def _split_frontmatter(text: str) -> tuple[str, str]:
    if not text.startswith("---\n"):
        return "", text
    parts = text[4:].split("\n---", 1)
    if len(parts) != 2:
        return "", text
    return parts[0], parts[1].lstrip("\n")


def _apply_merge(
    store_root: Path, resolution: Resolution, *, consent: bool
) -> ApplyResult:
    if not resolution.related:
        return ApplyResult(
            kind=resolution.kind,
            target=resolution.target,
            applied=False,
            changes=(),
            detail="merge requires `related=(<source_id>,)`",
        )
    source_id = resolution.related[0]
    target_path = _asset_path(store_root, resolution.target)
    source_path = _asset_path(store_root, source_id)
    if not target_path.is_file() or not source_path.is_file():
        return ApplyResult(
            kind=resolution.kind,
            target=resolution.target,
            applied=False,
            changes=(),
            detail="one of target / source is missing",
        )

    if not consent:
        return ApplyResult(
            kind=resolution.kind,
            target=resolution.target,
            applied=False,
            changes=(
                FileChange("modified", resolution.target, "would append source body"),
                FileChange("removed", source_id, "would archive source"),
            ),
            detail=f"dry-run: {source_id} merges into {resolution.target}",
        )

    tgt_fm, tgt_body = _split_frontmatter(target_path.read_text(encoding="utf-8"))
    _src_fm, src_body = _split_frontmatter(source_path.read_text(encoding="utf-8"))
    merged_body = (
        tgt_body.rstrip("\n")
        + f"\n\n<!-- merged from {source_id} -->\n\n"
        + src_body.lstrip("\n")
    )
    write_atomic(target_path, f"---\n{tgt_fm}\n---\n\n{merged_body}")

    dest = _archive_destination(source_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source_path), str(dest))

    _journal(
        "merge",
        resolution,
        store_root,
        applied=True,
        extra={"archived_source": str(dest)},
    )
    return ApplyResult(
        kind=resolution.kind,
        target=resolution.target,
        applied=True,
        changes=(
            FileChange("modified", resolution.target, "source body appended"),
            FileChange("moved", source_id, f"archived to {dest}"),
        ),
        detail=f"merged {source_id} into {resolution.target}",
    )


# ------------------------------------------------------------------
# UPDATE — proposal-writer, never auto-patches
# ------------------------------------------------------------------


def _apply_update(
    store_root: Path, resolution: Resolution, *, consent: bool
) -> ApplyResult:
    target_path = _asset_path(store_root, resolution.target)
    if not target_path.is_file():
        return ApplyResult(
            kind=resolution.kind,
            target=resolution.target,
            applied=False,
            changes=(),
            detail=f"update target not found: {target_path}",
        )
    proposal = target_path.with_suffix(".proposed.md")
    if not consent:
        return ApplyResult(
            kind=resolution.kind,
            target=resolution.target,
            applied=False,
            changes=(
                FileChange("created", str(proposal), "would drop proposal file"),
            ),
            detail=f"dry-run: would write proposal to {proposal}",
        )
    body = (
        f"# Proposed update for {resolution.target}\n"
        f"\n"
        f"- detail: {resolution.detail}\n"
        f"- proposed at: {_now_iso()}\n"
        f"\n"
        f"Edit the original `{target_path.name}` to apply; then remove this "
        f"`.proposed.md` file when done.\n"
    )
    write_atomic(proposal, body)
    _journal(
        "update",
        resolution,
        store_root,
        applied=True,
        extra={"proposal_path": str(proposal)},
    )
    return ApplyResult(
        kind=resolution.kind,
        target=resolution.target,
        applied=True,
        changes=(FileChange("created", str(proposal)),),
        detail=(
            f"update proposed at {proposal} — original left untouched "
            "(SPEC §1.2 principle 4: never auto-patch)"
        ),
    )


# ------------------------------------------------------------------
# Dispatch
# ------------------------------------------------------------------


def apply_resolution(
    store_root: Path,
    resolution: Resolution,
    *,
    consent: bool = False,
) -> ApplyResult:
    """Apply ``resolution`` to ``store_root`` (if ``consent=True``).

    Defaults to a dry-run — the returned :class:`ApplyResult` will
    have ``applied=False`` and ``detail`` describing what *would* have
    changed. Callers (``engram review --apply``) opt in with explicit
    ``consent=True``. This keeps SPEC §1.2 principle 4 — *never
    auto-delete* — at the API surface.
    """
    kind = resolution.kind
    dispatch = {
        ResolutionKind.ARCHIVE: _apply_archive,
        ResolutionKind.DISMISS: _apply_dismiss,
        ResolutionKind.ESCALATE: _apply_escalate,
        ResolutionKind.SUPERSEDE: _apply_supersede,
        ResolutionKind.MERGE: _apply_merge,
        ResolutionKind.UPDATE: _apply_update,
    }
    fn = dispatch.get(kind)
    if fn is None:
        return ApplyResult(
            kind=kind,
            target=resolution.target,
            applied=False,
            changes=(),
            detail=f"unsupported resolution kind: {kind.value}",
        )
    return fn(store_root, resolution, consent=consent)
