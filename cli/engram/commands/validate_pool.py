"""POOL-family validation rules for ``engram validate`` (SPEC §12.10).

Subset implemented in M3:

- **E-POOL-000** (new, deviation): malformed ``pools.toml`` — couldn't parse
  as TOML. SPEC §12.10 didn't assign a code for this; documented in the
  T-37 commit and in ``project_tasks_vs_spec_authority.md``. Emitted as
  an Issue rather than raising so ``engram validate`` stays a pure
  diagnostic tool.
- **E-POOL-001** (SPEC §12.10): ``propagation_mode = "pinned"`` without
  ``pinned_revision``.
- **E-POOL-002** (SPEC §12.10): subscription references a pool name that
  is not present under ``~/.engram/pools/<name>/``.
- **E-POOL-003** (SPEC §12.10): pool's ``rev/current`` symlink dangles —
  only reported for auto-sync / notify subscribers that actually resolve
  through it.
- **E-POOL-004** (new, deviation): ``subscribed_at`` not in
  ``{org, team, user, project}``. SPEC §9.2 defines the enum; §12.10
  hadn't assigned an error code for it.
- **E-POOL-005** (new, deviation): ``propagation_mode`` not in
  ``{auto-sync, notify, pinned}``.
- **E-POOL-006** (new, deviation): ``pinned_revision`` set while
  ``propagation_mode`` is not ``pinned`` (SPEC §9.2 requires null).
- **E-POOL-007** (new, deviation): ``pinned_revision`` points at a
  ``rev/<id>/`` directory that does not exist in the pool.
- **W-POOL-002** (SPEC §12.10): pool directory is missing
  ``.engram-pool.toml`` manifest.

Deferred to later milestones:

- W-POOL-001 (new pool revision pending review) — needs propagation
  notify-mode awareness; will land with the propagation engine.
- W-POOL-003 (subscribed_at mismatches publisher scope) — needs pool
  manifest publisher-scope field; pool manifest schema is stabilising.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import tomli

from engram.commands.validate import Issue
from engram.core.paths import memory_dir, user_root

__all__ = ["run_pool_checks"]


_VALID_AT = {"org", "team", "user", "project"}
_VALID_MODE = {"auto-sync", "notify", "pinned"}


def _issue(code: str, file: str, message: str, reference: str) -> Issue:
    severity = "error" if code.startswith("E-") else "warning"
    return Issue(code, severity, file, None, message, reference)


def _pool_root(pool_name: str) -> Path:
    return user_root() / "pools" / pool_name


def run_pool_checks(project_root: Path) -> list[Issue]:
    """Return every POOL-family Issue for ``project_root``.

    Safe to call when ``pools.toml`` is missing (returns ``[]``).
    """
    mem = memory_dir(project_root)
    toml_path = mem / "pools.toml"
    rel_toml = "pools.toml"

    if not toml_path.is_file():
        return []

    raw_text = toml_path.read_text(encoding="utf-8")
    # An empty or stub-only pools.toml (comments only) parses to {} — clean.
    try:
        data = tomli.loads(raw_text)
    except tomli.TOMLDecodeError as exc:
        return [
            _issue(
                "E-POOL-000",
                rel_toml,
                f"malformed pools.toml: {exc}",
                "SPEC §9.2",
            )
        ]

    subs = data.get("subscribe")
    if subs is None:
        return []
    if not isinstance(subs, dict):
        return [
            _issue(
                "E-POOL-000",
                rel_toml,
                "`subscribe` key in pools.toml must be a TOML table",
                "SPEC §9.2",
            )
        ]

    issues: list[Issue] = []
    for name, body in subs.items():
        if not isinstance(body, dict):
            issues.append(
                _issue(
                    "E-POOL-000",
                    rel_toml,
                    f"subscribe.{name} must be a TOML table",
                    "SPEC §9.2",
                )
            )
            continue
        issues.extend(_check_one_subscription(name, body, rel_toml))
    return issues


def _check_one_subscription(
    name: str, body: dict[str, Any], rel_toml: str
) -> list[Issue]:
    issues: list[Issue] = []

    subscribed_at = body.get("subscribed_at")
    mode = body.get("propagation_mode")
    pinned_revision = body.get("pinned_revision")

    # E-POOL-004 — invalid subscribed_at
    if not isinstance(subscribed_at, str) or subscribed_at not in _VALID_AT:
        issues.append(
            _issue(
                "E-POOL-004",
                rel_toml,
                f"subscribe.{name}.subscribed_at = {subscribed_at!r} "
                f"is not one of {sorted(_VALID_AT)}",
                "SPEC §9.2",
            )
        )

    # E-POOL-005 — invalid propagation_mode
    if not isinstance(mode, str) or mode not in _VALID_MODE:
        issues.append(
            _issue(
                "E-POOL-005",
                rel_toml,
                f"subscribe.{name}.propagation_mode = {mode!r} "
                f"is not one of {sorted(_VALID_MODE)}",
                "SPEC §9.2",
            )
        )

    # E-POOL-001 / E-POOL-006 — pinned consistency
    if mode == "pinned" and not pinned_revision:
        issues.append(
            _issue(
                "E-POOL-001",
                rel_toml,
                f"subscribe.{name}: propagation_mode=pinned requires pinned_revision",
                "SPEC §9.2",
            )
        )
    if mode in ("auto-sync", "notify") and pinned_revision is not None:
        issues.append(
            _issue(
                "E-POOL-006",
                rel_toml,
                f"subscribe.{name}: pinned_revision must be null when "
                f"propagation_mode is {mode}",
                "SPEC §9.2",
            )
        )

    # E-POOL-002 — pool dir present at ~/.engram/pools/<name>/?
    pool_dir = _pool_root(name)
    if not pool_dir.is_dir():
        # No pool on disk — every other "does X exist inside the pool" check
        # would be tautologically broken, so skip them.
        issues.append(
            _issue(
                "E-POOL-002",
                rel_toml,
                f"subscribe.{name}: pool directory not found at {pool_dir}",
                "SPEC §9.2",
            )
        )
        return issues

    # W-POOL-002 — manifest missing
    if not (pool_dir / ".engram-pool.toml").is_file():
        issues.append(
            _issue(
                "W-POOL-002",
                rel_toml,
                f"pool {name!r} is missing .engram-pool.toml manifest at {pool_dir}",
                "SPEC §9.1",
            )
        )

    # E-POOL-007 — pinned_revision points at a missing rev/<id>/
    if mode == "pinned" and isinstance(pinned_revision, str):
        rev_dir = pool_dir / "rev" / pinned_revision
        if not rev_dir.is_dir():
            issues.append(
                _issue(
                    "E-POOL-007",
                    rel_toml,
                    f"subscribe.{name}: pinned_revision={pinned_revision!r} does "
                    f"not exist at {rev_dir}",
                    "SPEC §9.2",
                )
            )

    # E-POOL-003 — dangling rev/current (only relevant for non-pinned)
    if mode in ("auto-sync", "notify"):
        current = pool_dir / "rev" / "current"
        if current.is_symlink() and not current.resolve().is_dir():
            issues.append(
                _issue(
                    "E-POOL-003",
                    rel_toml,
                    f"pool {name!r} rev/current symlink is dangling "
                    f"(points at {current.readlink()})",
                    "SPEC §9.1",
                )
            )

    return issues
