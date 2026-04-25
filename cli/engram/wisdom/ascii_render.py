"""ASCII / Unicode-block sparkline renderer for wisdom reports.

Uses the 8 standard sparkline block characters ▁▂▃▄▅▆▇█. Each curve is
rendered as one row: ``[id] name  <sparkline>  <summary>``. Insufficient
curves render with ``[insufficient]`` placeholder so the user sees what
they are missing data for.
"""

from __future__ import annotations

from engram.wisdom.types import Curve, Sample, WisdomReport


_BLOCKS = "▁▂▃▄▅▆▇█"


def _sparkline(samples: tuple[Sample, ...]) -> str:
    if not samples:
        return ""
    values = [s.value for s in samples]
    lo = min(values)
    hi = max(values)
    span = hi - lo
    if span <= 0.0:
        # All-equal → bottom block to indicate flat-line at any value
        return _BLOCKS[0] * len(values)
    out = []
    for v in values:
        idx = int(((v - lo) / span) * (len(_BLOCKS) - 1))
        out.append(_BLOCKS[max(0, min(len(_BLOCKS) - 1, idx))])
    return "".join(out)


def render_text(report: WisdomReport) -> str:
    lines = []
    banner = (
        f"WISDOM REPORT  store={report.store_root}  "
        f"period={report.period_days}d  generated={report.generated_at}"
    )
    lines.append(banner)
    lines.append("=" * min(len(banner), 80))
    lines.append("")

    for curve in report.curves:
        if curve.insufficient or not curve.samples:
            spark = "[insufficient]".ljust(len(_BLOCKS))
        else:
            spark = _sparkline(curve.samples)

        # Two-line per curve: header + summary indented
        lines.append(f"{curve.id}  {curve.name}")
        lines.append(f"     {spark}  {curve.summary}")
        lines.append("")

    lines.append(
        "Tip: each curve reads ~/.engram/journal/usage.jsonl. Use engram "
        "for >7 days to see real trends."
    )
    return "\n".join(lines)
