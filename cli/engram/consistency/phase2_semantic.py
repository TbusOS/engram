"""Phase 2 — semantic conflict detection.

M4 scope (T-46): minimal deterministic detectors that work without a
vector embedder. Specifically:

- **Factual conflict by body hash:** two assets with byte-identical
  normalized body text are almost always a duplicate (or a legacy
  asset that was copy-pasted rather than superseded).
- **Topic divergence by name:** two assets whose ``name`` differs only
  by a negation phrase (``prefer tabs`` vs ``prefer spaces``) are a
  rule-conflict candidate.

Full DBSCAN clustering + six cluster rules land with T-48 once the
embedder (T-41) is wired. Until then, these two heuristic detectors
cover the "obvious" 80% of cases and emit reports the evaluator can
grade.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import yaml

from engram.consistency.types import (
    ConflictClass,
    ConflictReport,
    ConflictSeverity,
    Resolution,
    ResolutionKind,
)

__all__ = ["detect_phase2"]


# Master plan §第8周 / T-189: Jaccard shingle similarity ≥ this triggers a
# fuzzy MERGE proposal. 3-word shingles + 0.85 threshold chosen so single
# word substitutions in a long rule still trip MERGE (≈0.86 Jaccard for
# one substituted word in a 30-token body), but unrelated rules with
# stop-word overlap stay below 0.5.
_FUZZY_MERGE_THRESHOLD = 0.85
_SHINGLE_SIZE = 3


_OPPOSITES: tuple[tuple[str, str], ...] = (
    ("prefer", "avoid"),
    ("always", "never"),
    ("enable", "disable"),
    ("include", "exclude"),
    ("use", "do not use"),
    ("tabs", "spaces"),
    ("squash", "rebase"),
    ("merge", "fast-forward"),
)

_WORD_RE = re.compile(r"[a-z0-9]+")


def _read_frontmatter_and_body(path: Path) -> tuple[dict[str, object], str] | None:
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---\n"):
        return None
    parts = text[4:].split("\n---", 1)
    if len(parts) != 2:
        return None
    try:
        fm = yaml.safe_load(parts[0]) or {}
    except yaml.YAMLError:
        return None
    if not isinstance(fm, dict):
        return None
    return fm, parts[1].lstrip("\n")


def _normalize_body(body: str) -> str:
    """Collapse whitespace + lowercase so trivial edits don't hide duplicates."""
    return re.sub(r"\s+", " ", body.lower().strip())


def _body_hash(body: str) -> str:
    return hashlib.sha256(_normalize_body(body).encode("utf-8")).hexdigest()


def _word_set(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


def _shingles(body: str, n: int = _SHINGLE_SIZE) -> frozenset[str]:
    """N-word shingles over the normalized body text.

    Frozen to allow set operations + use as dict keys when needed.
    Returns an empty set when the body has fewer than ``n`` tokens —
    callers should treat that as "no useful similarity signal".
    """
    tokens = _WORD_RE.findall(body.lower())
    if len(tokens) < n:
        return frozenset()
    return frozenset(
        " ".join(tokens[i : i + n]) for i in range(len(tokens) - n + 1)
    )


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _has_opposite(a: str, b: str) -> str | None:
    """Return a short ``"tabs vs spaces"`` marker if two names contain an
    opposed pair of keywords; None otherwise."""
    wa, wb = _word_set(a), _word_set(b)
    for left, right in _OPPOSITES:
        if (left in wa and right in wb) or (right in wa and left in wb):
            return f"{left} vs {right}"
    return None


def detect_phase2(store_root: Path) -> list[ConflictReport]:
    local = store_root / ".memory" / "local"
    if not local.is_dir():
        return []

    entries: list[tuple[str, dict[str, object], str]] = []
    for asset in sorted(local.glob("*.md")):
        parsed = _read_frontmatter_and_body(asset)
        if parsed is None:
            continue
        fm, body = parsed
        entries.append((f"local/{asset.stem}", fm, body))

    reports: list[ConflictReport] = []

    # 1. Factual conflict by normalized body hash
    seen: dict[str, str] = {}
    for asset_id, _fm, body in entries:
        h = _body_hash(body)
        if h in seen:
            other = seen[h]
            reports.append(
                ConflictReport(
                    conflict_class=ConflictClass.FACTUAL,
                    severity=ConflictSeverity.WARNING,
                    primary_asset=asset_id,
                    related_assets=(other,),
                    message=(
                        f"body of {asset_id} is byte-identical to {other} "
                        "(normalized); likely copy-paste, candidate for "
                        "merge or supersede"
                    ),
                    phase=2,
                    proposed=(
                        Resolution(
                            kind=ResolutionKind.MERGE,
                            target=asset_id,
                            related=(other,),
                            detail="merge the two duplicate bodies into one",
                        ),
                    ),
                )
            )
        else:
            seen[h] = asset_id

    # 1b. Fuzzy MERGE — Jaccard shingle similarity ≥ threshold (T-189).
    # Skip pairs already flagged in 1 (exact-hash) so we do not double-report.
    flagged: set[frozenset[str]] = {
        frozenset((r.primary_asset, *r.related_assets))
        for r in reports
        if r.conflict_class is ConflictClass.FACTUAL
    }
    shingled: list[tuple[str, frozenset[str]]] = [
        (aid, _shingles(body)) for aid, _fm, body in entries
    ]
    for i, (aid_a, sh_a) in enumerate(shingled):
        if not sh_a:
            continue
        for aid_b, sh_b in shingled[i + 1 :]:
            if not sh_b:
                continue
            if frozenset((aid_a, aid_b)) in flagged:
                continue
            sim = _jaccard(sh_a, sh_b)
            if sim < _FUZZY_MERGE_THRESHOLD:
                continue
            pct = int(round(sim * 100))
            reports.append(
                ConflictReport(
                    conflict_class=ConflictClass.FACTUAL,
                    severity=ConflictSeverity.WARNING,
                    primary_asset=aid_a,
                    related_assets=(aid_b,),
                    message=(
                        f"{aid_a} and {aid_b} are {pct}% similar by Jaccard "
                        f"shingle (≥ {int(_FUZZY_MERGE_THRESHOLD * 100)}%); "
                        "candidate for merge — review wording differences "
                        "before consolidating"
                    ),
                    phase=2,
                    proposed=(
                        Resolution(
                            kind=ResolutionKind.MERGE,
                            target=aid_a,
                            related=(aid_b,),
                            detail=(
                                f"merge near-duplicate ({pct}% similar); "
                                "keep the more specific wording"
                            ),
                        ),
                    ),
                )
            )
            flagged.add(frozenset((aid_a, aid_b)))

    # 2. Rule conflict by name-opposite detection (feedback only — SPEC §4.3)
    feedback = [(aid, fm) for aid, fm, _ in entries if fm.get("type") == "feedback"]
    for i, (aid_a, fm_a) in enumerate(feedback):
        for aid_b, fm_b in feedback[i + 1 :]:
            na = str(fm_a.get("name", ""))
            nb = str(fm_b.get("name", ""))
            marker = _has_opposite(na, nb)
            if marker is None:
                continue
            reports.append(
                ConflictReport(
                    conflict_class=ConflictClass.RULE,
                    severity=ConflictSeverity.WARNING,
                    primary_asset=aid_a,
                    related_assets=(aid_b,),
                    message=(
                        f"feedback {aid_a} and {aid_b} carry opposing "
                        f"keywords ({marker}) — candidate for rule-conflict; "
                        "set an explicit overrides: relation or reconcile"
                    ),
                    phase=2,
                    proposed=(
                        Resolution(
                            kind=ResolutionKind.ESCALATE,
                            target=aid_a,
                            related=(aid_b,),
                            detail=(
                                "ask the owner to pick one; set `overrides:` "
                                "on the loser"
                            ),
                        ),
                    ),
                )
            )

    return reports
