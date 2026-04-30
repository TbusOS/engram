"""Compute the 6 wisdom curves from ``~/.engram/journal/usage.jsonl``.

Each curve is intentionally **simple to start** — the M4.6 goal is to
render *something* for every curve so users see the trend exists, even
when data is sparse. Sophistication lands as we accumulate data: e.g.
C2 task-recurrence should later use task_hash clustering across runs;
C5 redundancy should join with Consistency Engine merge proposals.

Today's proxies:

- C1 retrieval_hit_rate   = validated events / (validated + loaded)
- C2 task_recurrence       = distinct task_hashes seen ≥ 2 times
- C3 write_friction_proxy  = events per day (lower = less friction)
- C4 mandatory_false_pos   = contradicted on mandatory / loads on mandatory
- C5 redundancy_rate       = false_positive_dismissed / total events
- C6 confidence_calibration = avg per-asset (validated_score - contradicted_score) / exposure
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from engram.usage import EventType, EvidenceKind, UsageEvent, iter_events
from engram.wisdom.types import Curve, Sample, WisdomReport


def _today_utc() -> date:
    return datetime.now(tz=timezone.utc).date()


def _bucket_day(ts: str) -> str:
    return ts.split("T", 1)[0]


def _empty_curve(curve_id: str, name: str, unit: str, hint: str) -> Curve:
    return Curve(
        id=curve_id,
        name=name,
        unit=unit,
        samples=(),
        summary=f"insufficient data — {hint}",
        insufficient=True,
    )


def _ratio_summary(samples: tuple[Sample, ...], suffix: str = "") -> str:
    if not samples:
        return ""
    last = samples[-1].value
    if len(samples) >= 2:
        delta = last - samples[0].value
        return f"current: {last:.2f}{suffix}  Δperiod: {delta:+.2f}"
    return f"current: {last:.2f}{suffix}"


def _within_window(events: Iterable[UsageEvent], days: int) -> list[UsageEvent]:
    cutoff = (_today_utc() - timedelta(days=days)).isoformat()
    return [e for e in events if (e.timestamp or "") >= cutoff]


def _daily_samples(
    events: Iterable[UsageEvent],
    days: int,
    reducer,
) -> tuple[Sample, ...]:
    """Bucket events into daily values via ``reducer(events_for_day) -> float``.

    Empty days fill 0.0 so sparkline renders as a flat baseline rather
    than a gap.
    """
    by_day: dict[str, list[UsageEvent]] = defaultdict(list)
    for ev in events:
        if not ev.timestamp:
            continue
        by_day[_bucket_day(ev.timestamp)].append(ev)

    today = _today_utc()
    out: list[Sample] = []
    for offset in range(days - 1, -1, -1):
        day = (today - timedelta(days=offset)).isoformat()
        out.append(Sample(day=day, value=float(reducer(by_day.get(day, [])))))
    return tuple(out)


# ------------------------------------------------------------------
# Per-curve computers
# ------------------------------------------------------------------


def _compute_c1_hit_rate(all_events: list[UsageEvent], days: int) -> Curve:
    if not all_events:
        return _empty_curve(
            "C1",
            "Retrieval hit rate",
            "ratio",
            "no events in usage.jsonl yet — run `engram context pack`",
        )

    def hit_ratio(events: list[UsageEvent]) -> float:
        if not events:
            return 0.0
        validated = sum(
            1
            for e in events
            if e.event_type is EventType.VALIDATED and e.trust_weight and e.trust_weight > 0
        )
        loaded = sum(1 for e in events if e.event_type is EventType.LOADED)
        denom = validated + loaded
        return (validated / denom) if denom else 0.0

    samples = _daily_samples(all_events, days, hit_ratio)
    return Curve(
        id="C1",
        name="Retrieval hit rate",
        unit="ratio",
        samples=samples,
        summary=_ratio_summary(samples),
    )


def _compute_c2_task_recurrence(
    all_events: list[UsageEvent], days: int
) -> Curve:
    if not all_events:
        return _empty_curve(
            "C2",
            "Task recurrence",
            "count",
            "need ≥ 2 events with same task_hash to detect recurrence",
        )
    counts: dict[str, int] = defaultdict(int)
    for e in all_events:
        if e.task_hash:
            counts[e.task_hash] += 1
    recurring = sum(1 for n in counts.values() if n >= 2)
    if recurring == 0:
        return _empty_curve(
            "C2",
            "Task recurrence",
            "count",
            "no recurring tasks yet — keep using engram on similar tasks",
        )

    # Daily series: count of recurring tasks observed per day
    def per_day_recurring(events: list[UsageEvent]) -> int:
        local: dict[str, int] = defaultdict(int)
        for e in events:
            if e.task_hash:
                local[e.task_hash] += 1
        return sum(1 for n in local.values() if n >= 2)

    samples = _daily_samples(all_events, days, per_day_recurring)
    return Curve(
        id="C2",
        name="Task recurrence",
        unit="distinct tasks/day",
        samples=samples,
        summary=f"current: {samples[-1].value:.0f} recurring task(s) today;"
        f" {recurring} total over period",
    )


def _compute_c3_write_friction(
    all_events: list[UsageEvent], days: int
) -> Curve:
    """Proxy: total events per day. Lower count with same-or-higher value
    elsewhere = less friction for the same outcome. This is a placeholder
    until per-asset add timing lands."""
    if not all_events:
        return _empty_curve(
            "C3",
            "Write friction (proxy)",
            "events/day",
            "use `engram memory quick` and rerun to populate",
        )
    samples = _daily_samples(all_events, days, lambda evs: float(len(evs)))
    return Curve(
        id="C3",
        name="Write friction (proxy: events/day)",
        unit="events/day",
        samples=samples,
        summary=f"current: {samples[-1].value:.0f} events today",
    )


def _compute_c4_mandatory_fp(
    all_events: list[UsageEvent], days: int
) -> Curve:
    """Without graph.db join we approximate by `EXPLICIT_USER_CORRECTION`
    events overall: rises = false positives that should not have triggered.
    Will sharpen once we tag mandatory events explicitly."""
    if not all_events:
        return _empty_curve(
            "C4",
            "Mandatory false-positive (proxy)",
            "count/day",
            "no corrections yet — engram has no triggers to evaluate",
        )

    def fp(events: list[UsageEvent]) -> int:
        return sum(
            1
            for e in events
            if e.evidence_kind is EvidenceKind.EXPLICIT_USER_CORRECTION
        )

    samples = _daily_samples(all_events, days, fp)
    return Curve(
        id="C4",
        name="Mandatory false-positive (proxy: corrections/day)",
        unit="count/day",
        samples=samples,
        summary=f"current: {samples[-1].value:.0f} correction(s) today",
    )


def _compute_c5_redundancy(
    all_events: list[UsageEvent], days: int
) -> Curve:
    if not all_events:
        return _empty_curve(
            "C5",
            "Redundancy rate (proxy)",
            "ratio",
            "needs Consistency Engine MERGE proposals (T-189) for real signal",
        )

    def fp_dismissed_ratio(events: list[UsageEvent]) -> float:
        if not events:
            return 0.0
        total = len(events)
        fp = sum(
            1
            for e in events
            if e.evidence_kind is EvidenceKind.FALSE_POSITIVE_DISMISSED
        )
        return fp / total

    samples = _daily_samples(all_events, days, fp_dismissed_ratio)
    return Curve(
        id="C5",
        name="Redundancy rate (proxy: false_positive dismiss / events)",
        unit="ratio",
        samples=samples,
        summary=_ratio_summary(samples),
    )


def _compute_c6_calibration(
    all_events: list[UsageEvent], days: int
) -> Curve:
    if not all_events:
        return _empty_curve(
            "C6",
            "Confidence calibration",
            "score/exposure",
            "no events yet to calibrate against",
        )

    by_asset: dict[str, list[UsageEvent]] = defaultdict(list)
    for e in all_events:
        by_asset[e.asset_uri].append(e)

    def avg_calibration(events: list[UsageEvent]) -> float:
        if not events:
            return 0.0
        local_by_asset: dict[str, list[UsageEvent]] = defaultdict(list)
        for e in events:
            local_by_asset[e.asset_uri].append(e)
        if not local_by_asset:
            return 0.0
        per_asset_scores = []
        for asset_evs in local_by_asset.values():
            exposure = len(asset_evs)
            net = sum(float(e.trust_weight or 0.0) for e in asset_evs)
            per_asset_scores.append(net / exposure if exposure else 0.0)
        return sum(per_asset_scores) / len(per_asset_scores)

    samples = _daily_samples(all_events, days, avg_calibration)
    return Curve(
        id="C6",
        name="Confidence calibration (avg per-asset signal/exposure)",
        unit="score/exposure",
        samples=samples,
        summary=_ratio_summary(samples),
    )


# ------------------------------------------------------------------
# C7 / C8 — Auto-Continuation pipeline curves (T-211)
# ------------------------------------------------------------------


def _scan_session_files(store_root: Path) -> list[dict[str, Any]]:
    """Walk session asset directories and pull out the few fields C7/C8 need.

    Reads from both the project-local ``.memory/sessions/`` and the
    user-global ``~/.engram/sessions/``. Sessions without a parseable
    frontmatter or without an ``ended_at`` are skipped — the curves
    are best-effort, not validators.
    """
    from contextlib import suppress

    from engram.core.paths import user_root
    from engram.observer.session import parse_session_file, sessions_root

    roots: list[Path] = [sessions_root(store_root / ".memory"), sessions_root(user_root())]
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("sess_*.md"):
            # Security reviewer F5 — refuse to read through symlinks.
            if not path.is_file() or path.is_symlink():
                continue
            try:
                fm, _ = parse_session_file(path)
            except Exception:
                continue
            if fm.session_id in seen:
                continue
            seen.add(fm.session_id)
            ended_iso: str | None = None
            if fm.ended_at is not None:
                with suppress(Exception):
                    ended_iso = fm.ended_at.date().isoformat()
            out.append(
                {
                    "session_id": fm.session_id,
                    "task_hash": fm.task_hash,
                    "ended_day": ended_iso,
                    "exposure_count": int(fm.confidence.exposure_count),
                    "distilled_into": list(fm.distilled_into),
                }
            )
    return out


def _compute_c7_continuation_hit_rate(
    sessions: list[dict[str, Any]], days: int
) -> Curve:
    """Continuation hit rate = sessions per day with exposure_count > 0.

    A "hit" is a session that the Relevance Gate Stage 0 actually
    injected (and the LLM consumed) at least once. Captured via the
    ``exposure_count`` field on the Session frontmatter that Tier 1
    bumps when a downstream usage event references the session.
    """
    if not sessions:
        return _empty_curve(
            "C7",
            "Continuation hit rate",
            "ratio/day",
            "no Session assets yet — install observer hooks (engram observer install)",
        )
    today = _today_utc()
    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for s in sessions:
        day = s.get("ended_day")
        if isinstance(day, str):
            by_day[day].append(s)

    samples: list[Sample] = []
    any_data = False
    for offset in range(days - 1, -1, -1):
        day = (today - timedelta(days=offset)).isoformat()
        bucket = by_day.get(day, [])
        if not bucket:
            samples.append(Sample(day=day, value=0.0))
            continue
        any_data = True
        hits = sum(1 for s in bucket if int(s.get("exposure_count", 0) or 0) > 0)
        samples.append(Sample(day=day, value=hits / len(bucket)))

    if not any_data:
        return _empty_curve(
            "C7",
            "Continuation hit rate",
            "ratio/day",
            "no sessions ended in window — ride the observer pipeline more",
        )
    return Curve(
        id="C7",
        name="Continuation hit rate",
        unit="ratio/day",
        samples=tuple(samples),
        summary=_ratio_summary(tuple(samples)),
    )


def _compute_c8_distillation_yield(
    sessions: list[dict[str, Any]], days: int
) -> Curve:
    """Distillation yield = sessions per day that contributed to a promoted Memory.

    Counted as: ``len(distilled_into) > 0``. Tier 2 (T-208) writes
    candidates; T-209 promote stamps the source sessions with the
    promoted asset name. So a non-empty ``distilled_into`` means the
    session's content actually became durable Memory — the canonical
    "did engram learn anything" signal.
    """
    if not sessions:
        return _empty_curve(
            "C8",
            "Distillation yield",
            "ratio/day",
            "no Session assets — run more sessions, then `engram distill review`",
        )
    today = _today_utc()
    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for s in sessions:
        day = s.get("ended_day")
        if isinstance(day, str):
            by_day[day].append(s)

    samples: list[Sample] = []
    any_data = False
    for offset in range(days - 1, -1, -1):
        day = (today - timedelta(days=offset)).isoformat()
        bucket = by_day.get(day, [])
        if not bucket:
            samples.append(Sample(day=day, value=0.0))
            continue
        any_data = True
        promoted = sum(
            1
            for s in bucket
            if isinstance(s.get("distilled_into"), list) and s.get("distilled_into")
        )
        samples.append(Sample(day=day, value=promoted / len(bucket)))

    if not any_data:
        return _empty_curve(
            "C8",
            "Distillation yield",
            "ratio/day",
            "no sessions in window; nothing to distill yet",
        )
    return Curve(
        id="C8",
        name="Distillation yield",
        unit="ratio/day",
        samples=tuple(samples),
        summary=_ratio_summary(tuple(samples)),
    )


# ------------------------------------------------------------------
# Public entry
# ------------------------------------------------------------------


def compute_wisdom_report(store_root: Path, *, days: int = 7) -> WisdomReport:
    all_events = list(iter_events())
    in_window = _within_window(all_events, days)
    session_rows = _scan_session_files(store_root)

    curves = [
        _compute_c1_hit_rate(in_window, days),
        _compute_c2_task_recurrence(in_window, days),
        _compute_c3_write_friction(in_window, days),
        _compute_c4_mandatory_fp(in_window, days),
        _compute_c5_redundancy(in_window, days),
        _compute_c6_calibration(in_window, days),
        _compute_c7_continuation_hit_rate(session_rows, days),
        _compute_c8_distillation_yield(session_rows, days),
    ]

    return WisdomReport(
        store_root=str(store_root),
        period_days=days,
        generated_at=datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
        curves=curves,
    )
