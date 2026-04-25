"""Shared types for wisdom curves."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class Sample:
    """One bucketed datapoint on a wisdom curve.

    ``day`` is the ISO date of the bucket; ``value`` is the curve's
    metric for that day. Curves whose unit is ratio use [0.0, 1.0];
    counts use float-as-int. Unit is described per-curve via
    ``Curve.unit``.
    """

    day: str
    value: float


@dataclass
class Curve:
    id: str           # C1, C2, ..., C6
    name: str         # human-readable
    unit: str         # "ratio", "count/day", "score/exposure", etc.
    samples: tuple[Sample, ...] = ()
    summary: str = ""
    insufficient: bool = False


@dataclass
class WisdomReport:
    store_root: str
    period_days: int
    generated_at: str
    curves: list[Curve] = field(default_factory=list)
