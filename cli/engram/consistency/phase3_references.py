"""Phase 3 — reference-graph health checks (T-47r).

Phase 1 catches *flat* broken references (E-REF-001 / E-REF-003 — a
single asset pointing at something missing). Phase 3's added value is
*transitive* analysis of the ``supersedes`` graph, which phase 1 cannot
see:

1. **dangling supersedes** — A declares ``supersedes: X`` but X is not a
   real asset. (Phase 1 validates ``references`` but not ``supersedes``.)
2. **circular supersedes** — A → B → … → A. A supersede cycle is
   incoherent: no asset is authoritative.
3. **fork (silent override)** — two assets both declare they supersede
   the same target. Only one can be the rightful successor; the other is
   a silent override that needs a human decision.

All three are computed from frontmatter alone (no embeddings, no DB), so
Phase 3 is deterministic and offline. Pool cross-reference graphs are a
later refinement; this pass covers the project-local ``supersedes`` edges.
"""

from __future__ import annotations

from pathlib import Path

from engram.consistency.types import (
    ConflictClass,
    ConflictReport,
    ConflictSeverity,
    Resolution,
    ResolutionKind,
)
from engram.core.frontmatter import FrontmatterError, parse_file

__all__ = ["detect_phase3"]


def _load_supersedes_graph(local: Path) -> dict[str, str | None]:
    """Return ``{asset_id: supersedes_target_or_None}`` for local assets."""
    graph: dict[str, str | None] = {}
    for asset in sorted(local.glob("*.md")):
        try:
            fm, _ = parse_file(asset)
        except (FrontmatterError, OSError):
            continue
        graph[f"local/{asset.stem}"] = fm.supersedes or None
    return graph


def _find_cycle(start: str, graph: dict[str, str | None]) -> list[str] | None:
    """Follow supersedes edges from ``start``; return the cycle if one exists."""
    seen: list[str] = []
    node: str | None = start
    while node is not None:
        if node in seen:
            return [*seen[seen.index(node) :], node]
        seen.append(node)
        if node not in graph:
            return None  # edge leaves the known graph (dangling, handled elsewhere)
        node = graph.get(node)
    return None


def detect_phase3(store_root: Path) -> list[ConflictReport]:
    local = store_root / ".memory" / "local"
    if not local.is_dir():
        return []
    graph = _load_supersedes_graph(local)
    ids = set(graph)
    reports: list[ConflictReport] = []

    # 1. Dangling supersedes target.
    for asset_id, target in graph.items():
        if target is not None and target not in ids:
            reports.append(
                ConflictReport(
                    conflict_class=ConflictClass.REFERENCE_ROT,
                    severity=ConflictSeverity.ERROR,
                    primary_asset=asset_id,
                    related_assets=(target,),
                    message=(
                        f"{asset_id} declares supersedes: {target!r}, but no "
                        "such asset exists (dangling supersede)"
                    ),
                    phase=3,
                    proposed=(
                        Resolution(
                            kind=ResolutionKind.ESCALATE,
                            target=asset_id,
                            related=(target,),
                            detail=(
                                "fix or remove the supersedes pointer; the "
                                "superseded asset is missing"
                            ),
                        ),
                    ),
                )
            )

    # 2. Circular supersedes — report each cycle once (by its member set).
    seen_cycles: set[frozenset[str]] = set()
    for asset_id in graph:
        cycle = _find_cycle(asset_id, graph)
        if cycle is None:
            continue
        key = frozenset(cycle)
        if key in seen_cycles:
            continue
        seen_cycles.add(key)
        chain = " -> ".join(cycle)
        members = sorted(set(cycle))
        reports.append(
            ConflictReport(
                conflict_class=ConflictClass.REFERENCE_ROT,
                severity=ConflictSeverity.ERROR,
                primary_asset=members[0],
                related_assets=tuple(m for m in members if m != members[0]),
                message=f"circular supersedes chain: {chain}",
                phase=3,
                proposed=(
                    Resolution(
                        kind=ResolutionKind.ESCALATE,
                        target=members[0],
                        related=tuple(m for m in members if m != members[0]),
                        detail="break the supersede cycle; no asset is authoritative",
                    ),
                ),
            )
        )

    # 3. Fork — two or more assets supersede the same target (silent override).
    by_target: dict[str, list[str]] = {}
    for asset_id, target in graph.items():
        if target is not None and target in ids:
            by_target.setdefault(target, []).append(asset_id)
    for target, supersedors in sorted(by_target.items()):
        if len(supersedors) < 2:
            continue
        ordered = sorted(supersedors)
        reports.append(
            ConflictReport(
                conflict_class=ConflictClass.SILENT_OVERRIDE,
                severity=ConflictSeverity.WARNING,
                primary_asset=ordered[0],
                related_assets=(*ordered[1:], target),
                message=(
                    f"{len(ordered)} assets supersede {target!r} "
                    f"({', '.join(ordered)}); only one can be the rightful "
                    "successor"
                ),
                phase=3,
                proposed=(
                    Resolution(
                        kind=ResolutionKind.ESCALATE,
                        target=ordered[0],
                        related=(*ordered[1:], target),
                        detail=(
                            "decide which asset supersedes the target; merge or "
                            "archive the rest"
                        ),
                    ),
                ),
            )
        )

    return reports
