"""Drive the Relevance Gate over a fixture store + gold-set, compute metrics.

The gate is run at an effectively-unbounded budget so the *full* ranking is
measured (not the budget-packed subset). ``Asset.body`` is body-only, mirroring
``engram context pack`` — the retrieval path this benchmark scores.

The runner is backend-agnostic: it scores whatever the Relevance Gate does
today (BM25). When the semantic layer lands, the same runner measures it — the
only difference is the gate's configured backend.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from engram.benchmark.metrics import mrr_at_k, ndcg_at_k, recall_at_k
from engram.core.frontmatter import FrontmatterError, parse_file
from engram.relevance.gate import Asset, RelevanceRequest, run_relevance_gate

# Fixed "now" so the benchmark is deterministic. The gold-set's temporal
# queries resolve relative to this date (e.g. "last week" -> 2025-12-25), and
# the calibration fixtures are dated around it, so the temporal stage is
# exercised reproducibly rather than against a moving wall clock.
_FIXED_DATE = date(2026, 1, 1)
_UNBOUNDED_BUDGET = 10_000_000


@dataclass(frozen=True)
class GoldQuery:
    query: str
    relevant: set[str]
    difficulty: str


@dataclass(frozen=True)
class BenchmarkReport:
    n_queries: int
    recall_at_5: float
    recall_at_10: float
    mrr_at_10: float
    ndcg_at_10: float


def load_assets(store_dir: Path) -> list[Asset]:
    """Parse every ``local/*.md`` in the fixture store into a gate Asset.

    Asset id is ``local/<filename-stem>`` so it lines up with the gold-set.
    """
    local = store_dir / "local"
    assets: list[Asset] = []
    for path in sorted(local.glob("*.md")):
        try:
            fm, body = parse_file(path)
        except FrontmatterError:
            continue
        assets.append(
            Asset(
                id=f"local/{path.stem}",
                scope=fm.scope.value,
                enforcement=fm.enforcement.value,
                subscribed_at=fm.subscribed_at.value if fm.subscribed_at else None,
                body=body,
                updated=fm.updated or _FIXED_DATE,
                size_bytes=len(body.encode("utf-8")),
            )
        )
    return assets


def load_goldset(goldset_path: Path) -> list[GoldQuery]:
    """Read a jsonl gold-set: one ``{query, relevant: [...], difficulty}`` per line."""
    queries: list[GoldQuery] = []
    for raw in goldset_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        obj = json.loads(line)
        queries.append(
            GoldQuery(
                query=obj["query"],
                relevant=set(obj["relevant"]),
                difficulty=obj.get("difficulty", "unknown"),
            )
        )
    return queries


def ranked_ids(assets: Sequence[Asset], query: str) -> list[str]:
    """Run the gate and return ranked asset ids: mandatory first, then by score."""
    req = RelevanceRequest(
        query=query, assets=assets, budget_tokens=_UNBOUNDED_BUDGET, now=_FIXED_DATE
    )
    result = run_relevance_gate(req)
    ids = [a.id for a in result.mandatory]
    ids.extend(c.asset.id for c in result.included)
    return ids


def run_retrieval_benchmark(store_dir: Path, goldset_path: Path) -> BenchmarkReport:
    """Score the current Relevance Gate over the gold-set; averaged metrics."""
    assets = load_assets(store_dir)
    goldset = load_goldset(goldset_path)
    if not goldset:
        raise ValueError(f"empty gold-set: {goldset_path}")

    totals = {"r5": 0.0, "r10": 0.0, "mrr": 0.0, "ndcg": 0.0}
    for gq in goldset:
        ranked = ranked_ids(assets, gq.query)
        totals["r5"] += recall_at_k(ranked, gq.relevant, 5)
        totals["r10"] += recall_at_k(ranked, gq.relevant, 10)
        totals["mrr"] += mrr_at_k(ranked, gq.relevant, 10)
        totals["ndcg"] += ndcg_at_k(ranked, gq.relevant, 10)

    n = len(goldset)
    return BenchmarkReport(
        n_queries=n,
        recall_at_5=totals["r5"] / n,
        recall_at_10=totals["r10"] / n,
        mrr_at_10=totals["mrr"] / n,
        ndcg_at_10=totals["ndcg"] / n,
    )
