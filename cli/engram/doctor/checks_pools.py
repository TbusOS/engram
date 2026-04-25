"""Pool sync checks: subscribed pool's `last_synced_rev` vs available rev.

Today this is best-effort: when the pool is not present at
``~/.engram/pools/<name>/`` we surface a "missing local copy" issue. When
the pool is present we compare ``last_synced_rev`` (from `pools.toml`) with
the actual `rev/current` symlink target. Once T-183 (issue #7) lands the
notify-mode dual-revision schema, this check expands.
"""

from __future__ import annotations

import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover — Py 3.11+ everywhere we ship
    import tomli as tomllib

from engram.core.paths import memory_dir, user_root
from engram.doctor.types import CheckIssue, Severity


def check_pool_sync(project_root: Path) -> list[CheckIssue]:
    issues: list[CheckIssue] = []
    pools_toml = memory_dir(project_root) / "pools.toml"
    if not pools_toml.is_file():
        return issues

    try:
        data = tomllib.loads(pools_toml.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        issues.append(
            CheckIssue(
                code="DOC-POOL-001",
                severity=Severity.ERROR,
                message=f"pools.toml is malformed: {exc}",
                fix_command=f"edit {pools_toml} and fix the TOML syntax",
            )
        )
        return issues

    subscriptions = data.get("subscribe", {}) or {}
    if not isinstance(subscriptions, dict):
        return issues

    pools_root = user_root() / "pools"
    for pool_name, conf in subscriptions.items():
        pool_dir = pools_root / pool_name
        if not pool_dir.is_dir():
            issues.append(
                CheckIssue(
                    code="DOC-POOL-002",
                    severity=Severity.WARNING,
                    message=(
                        f"subscribed to pool {pool_name!r} but local copy is "
                        f"missing at {pool_dir}"
                    ),
                    fix_command=f"engram pool pull {pool_name}",
                )
            )
            continue

        last_synced = (conf or {}).get("last_synced_rev")
        rev_current = pool_dir / "rev" / "current"
        if rev_current.is_symlink():
            available = rev_current.resolve().name
            if last_synced and last_synced != available:
                issues.append(
                    CheckIssue(
                        code="DOC-POOL-003",
                        severity=Severity.INFO,
                        message=(
                            f"pool {pool_name!r} has new revision {available!r} "
                            f"available (you are at {last_synced!r})"
                        ),
                        fix_command=f"engram pool sync {pool_name}",
                    )
                )

    return issues
