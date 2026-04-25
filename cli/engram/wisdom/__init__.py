"""``engram/wisdom/`` — 6 wisdom curves rendered from the usage event bus.

The 6 curves are the **only metric for "越用越好用"**: every new feature in
M4.6+ should move at least one of these. Master plan reference:
``docs/superpowers/specs/2026-04-25-越用越好用-12周主线.md`` §1.

Layout (DESIGN §4.2):

- ``types.py``        — Curve / Sample / WisdomReport
- ``curves.py``       — compute_wisdom_report(...) + 6 per-curve compute_*
- ``ascii_render.py`` — sparkline + tabular text renderer (pre-M7 web UI)
"""

from __future__ import annotations

from engram.wisdom.curves import compute_wisdom_report
from engram.wisdom.types import Curve, Sample, WisdomReport

__all__ = [
    "Curve",
    "Sample",
    "WisdomReport",
    "compute_wisdom_report",
]
