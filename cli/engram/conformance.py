"""SPEC-level conformance suite (D4-1, productization plan §4).

This module encodes the structural invariants from SPEC §1.2, §2, §3,
§4, §7, and §13 as a list of machine-checkable functions. It is
deliberately separate from :mod:`engram.commands.validate`:

- ``validate`` reports line-level errors (E-FM-002 "malformed YAML",
  E-IDX-001 "broken link"). Its audience is the operator fixing one
  bad asset.
- ``conformance`` reports invariant violations ("a store is supposed
  to never auto-delete", "every asset is supposed to be parseable
  with plain yaml.safe_load"). Its audience is the maintainer of a
  *third-party* engram implementation who needs to know whether their
  store passes the SPEC self-test.

Every invariant has a stable ID (``INV-Lx``, ``INV-Fx``, ``INV-Ix``,
``INV-Vx``) that will never change once assigned — a test suite or a
downstream tool that references an ID today must still work in v1.0.

The suite is intentionally small (~a dozen checks). A bloated
conformance suite defeats its purpose: it stops being a minimum bar
and starts being a friction tax.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

__all__ = [
    "ConformanceReport",
    "Invariant",
    "check_conformance",
    "list_invariants",
]


@dataclass(frozen=True, slots=True)
class ConformanceReport:
    """Outcome of a single invariant check against one store."""

    invariant_id: str
    title: str
    passed: bool
    detail: str = ""
    reference: str = ""


@dataclass(frozen=True, slots=True)
class Invariant:
    """A named, stable-ID conformance check."""

    id: str
    title: str
    reference: str
    checker: Callable[[Path], tuple[bool, str]]


# ------------------------------------------------------------------
# Shared helpers
# ------------------------------------------------------------------


_VALID_TYPES: frozenset[str] = frozenset(
    {"user", "feedback", "project", "reference", "workflow_ptr", "agent"}
)
_VALID_SCOPES: frozenset[str] = frozenset(
    {"project", "user", "team", "org", "pool"}
)
_VALID_ENFORCEMENTS: frozenset[str] = frozenset(
    {"mandatory", "default", "hint"}
)
_REQUIRED_FM_FIELDS: tuple[str, ...] = ("name", "description", "type", "scope")
_REQUIRED_CONFIDENCE_FIELDS: tuple[str, ...] = (
    "validated_count",
    "contradicted_count",
    "last_validated",
    "usage_count",
)

_MEMORY_INDEX_LINK_RE = re.compile(r"\]\(([^)]+)\)")


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str] | None:
    if not text.startswith("---\n"):
        return None
    tail = text[4:]
    parts = tail.split("\n---", 1)
    if len(parts) != 2:
        return None
    yaml_text, body = parts
    try:
        fm = yaml.safe_load(yaml_text)
    except yaml.YAMLError:
        return None
    if not isinstance(fm, dict):
        return None
    return fm, body.lstrip("\n")


def _iter_local_assets(store_root: Path) -> list[Path]:
    local = store_root / ".memory" / "local"
    if not local.is_dir():
        return []
    return sorted(p for p in local.glob("*.md") if p.is_file())


# ------------------------------------------------------------------
# Layout invariants (INV-L*)
# ------------------------------------------------------------------


def _inv_l1(store_root: Path) -> tuple[bool, str]:
    mem = store_root / ".memory"
    if mem.is_dir():
        return True, ""
    return False, f"{mem} does not exist"


def _inv_l2(store_root: Path) -> tuple[bool, str]:
    f = store_root / ".memory" / "MEMORY.md"
    if f.is_file():
        return True, ""
    return False, f"{f} does not exist (SPEC §7)"


def _inv_l3(store_root: Path) -> tuple[bool, str]:
    missing = []
    for sub in ("local", "pools", "workflows", "kb"):
        if not (store_root / ".memory" / sub).is_dir():
            missing.append(sub)
    if not missing:
        return True, ""
    return False, f"missing subdirs under .memory/: {missing} (SPEC §3.2)"


def _inv_l4(store_root: Path) -> tuple[bool, str]:
    vf = store_root / ".engram" / "version"
    if not vf.is_file():
        return False, f"{vf} does not exist (SPEC §13)"
    text = vf.read_text(encoding="utf-8").strip()
    if not text.startswith("0.2"):
        return False, f".engram/version = {text!r} (expected 0.2*)"
    return True, ""


# ------------------------------------------------------------------
# Format invariants (INV-F*)
# ------------------------------------------------------------------


def _inv_f1(store_root: Path) -> tuple[bool, str]:
    """Every asset parses as frontmatter + body with plain yaml.safe_load."""
    bad: list[str] = []
    for asset in _iter_local_assets(store_root):
        text = asset.read_text(encoding="utf-8", errors="replace")
        if _split_frontmatter(text) is None:
            bad.append(asset.name)
    if not bad:
        return True, ""
    return False, f"{len(bad)} asset(s) failed plain-YAML parse: {bad[:5]}"


def _inv_f2(store_root: Path) -> tuple[bool, str]:
    """Every asset carries the four required frontmatter fields."""
    offenders: list[str] = []
    for asset in _iter_local_assets(store_root):
        parsed = _split_frontmatter(asset.read_text(encoding="utf-8"))
        if parsed is None:
            continue  # INV-F1 already flagged
        fm, _ = parsed
        missing = [f for f in _REQUIRED_FM_FIELDS if f not in fm]
        if missing:
            offenders.append(f"{asset.name}: missing {missing}")
    if not offenders:
        return True, ""
    return False, "; ".join(offenders[:5])


def _inv_f3(store_root: Path) -> tuple[bool, str]:
    """Every asset's type is one of the six canonical subtypes."""
    offenders: list[str] = []
    for asset in _iter_local_assets(store_root):
        parsed = _split_frontmatter(asset.read_text(encoding="utf-8"))
        if parsed is None:
            continue
        fm, _ = parsed
        t = fm.get("type")
        if t not in _VALID_TYPES:
            offenders.append(f"{asset.name}: type={t!r}")
    if not offenders:
        return True, ""
    return False, "; ".join(offenders[:5])


def _inv_f4(store_root: Path) -> tuple[bool, str]:
    """Every asset's scope is one of the five canonical scopes."""
    offenders: list[str] = []
    for asset in _iter_local_assets(store_root):
        parsed = _split_frontmatter(asset.read_text(encoding="utf-8"))
        if parsed is None:
            continue
        fm, _ = parsed
        s = fm.get("scope")
        if s not in _VALID_SCOPES:
            offenders.append(f"{asset.name}: scope={s!r}")
    if not offenders:
        return True, ""
    return False, "; ".join(offenders[:5])


def _inv_f5(store_root: Path) -> tuple[bool, str]:
    """Every feedback asset has enforcement in the canonical set."""
    offenders: list[str] = []
    for asset in _iter_local_assets(store_root):
        parsed = _split_frontmatter(asset.read_text(encoding="utf-8"))
        if parsed is None:
            continue
        fm, _ = parsed
        if fm.get("type") != "feedback":
            continue
        enf = fm.get("enforcement")
        if enf not in _VALID_ENFORCEMENTS:
            offenders.append(f"{asset.name}: enforcement={enf!r}")
    if not offenders:
        return True, ""
    return False, "; ".join(offenders[:5])


def _inv_f6(store_root: Path) -> tuple[bool, str]:
    """Every agent asset has a complete confidence block."""
    offenders: list[str] = []
    for asset in _iter_local_assets(store_root):
        parsed = _split_frontmatter(asset.read_text(encoding="utf-8"))
        if parsed is None:
            continue
        fm, _ = parsed
        if fm.get("type") != "agent":
            continue
        conf = fm.get("confidence")
        if not isinstance(conf, dict):
            offenders.append(f"{asset.name}: confidence not a mapping")
            continue
        missing = [f for f in _REQUIRED_CONFIDENCE_FIELDS if f not in conf]
        if missing:
            offenders.append(f"{asset.name}: confidence missing {missing}")
    if not offenders:
        return True, ""
    return False, "; ".join(offenders[:5])


# ------------------------------------------------------------------
# Integrity invariants (INV-I*)
# ------------------------------------------------------------------


def _inv_i1(store_root: Path) -> tuple[bool, str]:
    """Every local asset is referenced by MEMORY.md (SPEC §7.2)."""
    index_path = store_root / ".memory" / "MEMORY.md"
    if not index_path.is_file():
        return True, "skipped — INV-L2 will catch missing MEMORY.md"
    index_text = index_path.read_text(encoding="utf-8")
    missing: list[str] = []
    for asset in _iter_local_assets(store_root):
        rel = f"local/{asset.name}"
        if rel not in index_text:
            missing.append(asset.name)
    if not missing:
        return True, ""
    return False, f"{len(missing)} asset(s) not in MEMORY.md: {missing[:5]}"


def _inv_i2(store_root: Path) -> tuple[bool, str]:
    """No two assets share the same filename stem (would collide on ID)."""
    seen: dict[str, str] = {}
    dupes: list[str] = []
    for asset in _iter_local_assets(store_root):
        stem = asset.stem
        if stem in seen:
            dupes.append(f"{stem} (at {seen[stem]} and {asset.name})")
        else:
            seen[stem] = asset.name
    if not dupes:
        return True, ""
    return False, "; ".join(dupes[:5])


# ------------------------------------------------------------------
# Portability invariants (INV-V* — "values" / principles from SPEC §2)
# ------------------------------------------------------------------


def _inv_v1(store_root: Path) -> tuple[bool, str]:
    """SPEC §2.2 portability — no non-markdown in local/ (except known
    control files). Third-party tools must be able to read a store with
    plain text tooling; binary blobs in the memory tree would break that."""
    local = store_root / ".memory" / "local"
    if not local.is_dir():
        return True, "skipped — INV-L3 will catch missing local/"
    known_suffixes = {".md"}
    known_control = {".gitkeep", "_compiled.md"}
    offenders: list[str] = []
    for p in local.rglob("*"):
        if p.is_dir():
            continue
        if p.suffix in known_suffixes or p.name in known_control:
            continue
        offenders.append(p.relative_to(store_root).as_posix())
    if not offenders:
        return True, ""
    return False, f"non-markdown files under local/: {offenders[:5]}"


def _inv_v2(store_root: Path) -> tuple[bool, str]:
    """SPEC §2.4 never auto-delete. The pre-v0.2 migration backup, if
    present, must not have been removed — it is the one-time escape
    hatch and tools must never silently clean it up."""
    backup = store_root / ".memory.pre-v0.2.backup"
    # Invariant only applies when the backup *was* created; we can't tell
    # retroactively if one existed and got deleted. But we can assert: if
    # any other backup directory pattern is present, it wasn't touched.
    if not backup.exists():
        return True, ""
    # Backup exists — confirm it is a directory and non-empty.
    if not backup.is_dir():
        return False, f"{backup} exists but is not a directory"
    if not any(backup.iterdir()):
        return False, f"{backup} exists but is empty (suspicious)"
    return True, ""


# ------------------------------------------------------------------
# Registry
# ------------------------------------------------------------------


INVARIANTS: tuple[Invariant, ...] = (
    Invariant(
        id="INV-L1",
        title=".memory/ directory exists",
        reference="SPEC §3.2",
        checker=_inv_l1,
    ),
    Invariant(
        id="INV-L2",
        title=".memory/MEMORY.md present",
        reference="SPEC §7",
        checker=_inv_l2,
    ),
    Invariant(
        id="INV-L3",
        title=".memory/{local,pools,workflows,kb}/ subdirs present",
        reference="SPEC §3.2",
        checker=_inv_l3,
    ),
    Invariant(
        id="INV-L4",
        title=".engram/version = '0.2'",
        reference="SPEC §13",
        checker=_inv_l4,
    ),
    Invariant(
        id="INV-F1",
        title="every asset parses as frontmatter + body",
        reference="SPEC §4.1",
        checker=_inv_f1,
    ),
    Invariant(
        id="INV-F2",
        title="every asset has name / description / type / scope",
        reference="SPEC §4.1",
        checker=_inv_f2,
    ),
    Invariant(
        id="INV-F3",
        title="every asset's type is one of six canonical subtypes",
        reference="SPEC §4.1",
        checker=_inv_f3,
    ),
    Invariant(
        id="INV-F4",
        title="every asset's scope is one of five canonical scopes",
        reference="SPEC §4.1, §8",
        checker=_inv_f4,
    ),
    Invariant(
        id="INV-F5",
        title="every feedback asset has valid enforcement",
        reference="SPEC §4.3, §8.3",
        checker=_inv_f5,
    ),
    Invariant(
        id="INV-F6",
        title="every agent asset has complete confidence block",
        reference="SPEC §4.7, §4.8",
        checker=_inv_f6,
    ),
    Invariant(
        id="INV-I1",
        title="every local asset is referenced by MEMORY.md",
        reference="SPEC §7.2",
        checker=_inv_i1,
    ),
    Invariant(
        id="INV-I2",
        title="no asset-ID collisions",
        reference="SPEC §3.3",
        checker=_inv_i2,
    ),
    Invariant(
        id="INV-V1",
        title="no non-markdown files in local/",
        reference="SPEC §2.2 portability",
        checker=_inv_v1,
    ),
    Invariant(
        id="INV-V2",
        title="pre-v0.2 backup, if present, is intact",
        reference="SPEC §2.4 never auto-delete",
        checker=_inv_v2,
    ),
)


def list_invariants() -> tuple[Invariant, ...]:
    """Return the frozen registry of conformance invariants."""
    return INVARIANTS


def check_conformance(store_root: Path) -> list[ConformanceReport]:
    """Run every invariant against ``store_root`` and return the reports.

    Reports are emitted in registry order so output diffs are stable
    across runs. Failing or missing preconditions (e.g. ``.memory/``
    doesn't exist) cause the specific invariant that relies on them to
    fail, not every downstream invariant.
    """
    out: list[ConformanceReport] = []
    for inv in INVARIANTS:
        try:
            ok, detail = inv.checker(store_root)
        except Exception as exc:  # defensive; a bad store should not crash the suite
            ok, detail = False, f"checker raised {type(exc).__name__}: {exc}"
        out.append(
            ConformanceReport(
                invariant_id=inv.id,
                title=inv.title,
                passed=ok,
                detail=detail,
                reference=inv.reference,
            )
        )
    return out
