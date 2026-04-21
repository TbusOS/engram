"""``engram validate`` — structural and schema checks per SPEC §12.

M2 subset of SPEC §12 covering the rule families that can be checked with the
Layer 1 primitives already on main:

- **STR-*** (§12.1) — project directory layout.
- **FM-*** (§12.2) — frontmatter required fields, enum values, description length.
- **MEM-*** (§12.3) — subtype-specific required fields and body conventions
  (feedback / project "Why + How to apply"; workflow_ptr / agent required frontmatter).
- **IDX-*** (§12.6) — MEMORY.md link integrity and asset coverage.
- **REF-*** (§12.9) — dangling references and supersedes targets.

SCO / ENF / POOL / INBOX / WF / KB / CONS rule families land with their
consuming milestones (M3 scope, M3 pool, M5 workflow, M6 KB / inbox / consistency).
Exit codes follow SPEC §12.13: ``0`` clean, ``1`` warnings only, ``2`` errors.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import click
import yaml

from engram.cli import GlobalConfig
from engram.core.paths import memory_dir

__all__ = [
    "EXIT_CLEAN",
    "EXIT_ERRORS",
    "EXIT_WARNINGS",
    "Issue",
    "compute_exit_code",
    "render_json",
    "render_text",
    "run_validate",
    "validate_cmd",
]

EXIT_CLEAN = 0
EXIT_WARNINGS = 1
EXIT_ERRORS = 2


@dataclass(frozen=True, slots=True)
class Issue:
    code: str
    severity: str
    file: str
    line: int | None
    message: str
    reference: str


_VALID_TYPES: set[str] = {
    "user",
    "feedback",
    "project",
    "reference",
    "workflow_ptr",
    "agent",
}
_VALID_SCOPES: set[str] = {"user", "project", "team", "org", "pool"}
_VALID_ENFORCEMENTS: set[str] = {"mandatory", "default", "hint"}

_KNOWN_TOP_LEVEL = {"MEMORY.md", "local", "pools", "workflows", "kb", "index", "pools.toml"}

_MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")

_WHY_RE = re.compile(r"\*\*Why:?\*\*", re.IGNORECASE)
_HOW_RE = re.compile(r"\*\*How to apply:?\*\*", re.IGNORECASE)


def compute_exit_code(issues: list[Issue]) -> int:
    if any(i.severity == "error" for i in issues):
        return EXIT_ERRORS
    if any(i.severity == "warning" for i in issues):
        return EXIT_WARNINGS
    return EXIT_CLEAN


# ------------------------------------------------------------------
# Orchestration
# ------------------------------------------------------------------


def run_validate(project_root: Path) -> list[Issue]:
    """Run every M2 validator and return the aggregated issue list."""
    from engram.commands.validate_pool import run_pool_checks

    issues: list[Issue] = []
    issues.extend(_check_structural(project_root))

    # Per SPEC §12.1 note: if any E-STR-* fires, skip downstream checks to avoid
    # spurious reports on a structurally broken store.
    if any(i.severity == "error" and i.code.startswith("E-STR-") for i in issues):
        return issues

    asset_ids: set[str] = set()
    asset_records = _collect_local_assets(project_root, issues, asset_ids)
    issues.extend(_check_memory_index(project_root, asset_records))
    issues.extend(_check_references(project_root, asset_records, asset_ids))
    issues.extend(run_pool_checks(project_root))
    return issues


# ------------------------------------------------------------------
# STR-*
# ------------------------------------------------------------------


def _check_structural(root: Path) -> list[Issue]:
    issues: list[Issue] = []
    mem = memory_dir(root)

    if not mem.is_dir():
        issues.append(
            Issue(
                "E-STR-001",
                "error",
                str(mem),
                None,
                ".memory/ directory is missing at the project root",
                "SPEC §3.2",
            )
        )
        return issues

    if not (mem / "MEMORY.md").is_file():
        issues.append(
            Issue(
                "E-STR-002",
                "error",
                str(mem / "MEMORY.md"),
                None,
                ".memory/MEMORY.md is missing",
                "SPEC §7",
            )
        )

    if not (mem / "local").is_dir():
        issues.append(
            Issue(
                "E-STR-003",
                "error",
                str(mem / "local"),
                None,
                ".memory/local/ is missing",
                "SPEC §3.2",
            )
        )

    local_dir = mem / "local"
    if local_dir.is_dir():
        has_assets = any(p.suffix == ".md" for p in local_dir.iterdir())
        if not has_assets:
            issues.append(
                Issue(
                    "W-STR-001",
                    "warning",
                    str(mem),
                    None,
                    ".memory/ contains no memory assets",
                    "SPEC §3",
                )
            )

    for entry in sorted(mem.iterdir()):
        if entry.name.startswith("."):
            continue
        if entry.name not in _KNOWN_TOP_LEVEL:
            issues.append(
                Issue(
                    "W-STR-002",
                    "warning",
                    str(entry),
                    None,
                    f"unexpected top-level entry in .memory/: {entry.name}",
                    "SPEC §3.2",
                )
            )

    return issues


# ------------------------------------------------------------------
# FM-* + MEM-* (collect asset records as a side-effect)
# ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _AssetRecord:
    path: Path
    rel_path: str  # relative to .memory/
    id: str | None
    data: dict[str, object] | None
    body: str | None


def _collect_local_assets(
    project_root: Path,
    issues: list[Issue],
    asset_ids: set[str],
) -> list[_AssetRecord]:
    """Walk .memory/local/*.md, run FM/MEM validators per file, record assets."""
    records: list[_AssetRecord] = []
    mem = memory_dir(project_root)
    local = mem / "local"
    if not local.is_dir():
        return records

    for md_path in sorted(local.glob("*.md")):
        rel = md_path.relative_to(mem).as_posix()
        asset_id = _asset_id_from_path(rel)
        text = md_path.read_text(encoding="utf-8")

        fm_raw = _split_frontmatter(text)
        if fm_raw is None:
            issues.append(
                Issue(
                    "E-FM-001",
                    "error",
                    rel,
                    None,
                    "asset file has no YAML frontmatter block",
                    "SPEC §4.1",
                )
            )
            records.append(_AssetRecord(md_path, rel, asset_id, None, None))
            continue

        yaml_text, body = fm_raw
        try:
            data = yaml.safe_load(yaml_text)
        except yaml.YAMLError as exc:
            issues.append(
                Issue(
                    "E-FM-002",
                    "error",
                    rel,
                    None,
                    f"frontmatter YAML is malformed: {exc}",
                    "SPEC §4.1",
                )
            )
            records.append(_AssetRecord(md_path, rel, asset_id, None, body))
            continue

        if not isinstance(data, dict):
            issues.append(
                Issue(
                    "E-FM-002",
                    "error",
                    rel,
                    None,
                    f"frontmatter must be a YAML mapping, got {type(data).__name__}",
                    "SPEC §4.1",
                )
            )
            records.append(_AssetRecord(md_path, rel, asset_id, None, body))
            continue

        _check_required_fm(rel, data, issues)
        _check_mem_subtype(rel, data, body, issues)
        records.append(_AssetRecord(md_path, rel, asset_id, data, body))
        if asset_id:
            asset_ids.add(asset_id)

    return records


def _split_frontmatter(text: str) -> tuple[str, str] | None:
    """Return ``(yaml_text, body)`` or None if no frontmatter block is present."""
    if not text.startswith("---"):
        return None
    match = re.match(
        r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n(.*))?\Z",
        text,
        re.DOTALL,
    )
    if match is None:
        return None
    return match.group(1), match.group(2) or ""


def _asset_id_from_path(rel_path: str) -> str | None:
    if not rel_path.endswith(".md"):
        return None
    if "/" not in rel_path:
        return None
    return rel_path[:-3]  # strip .md


def _issue(code: str, rel: str, message: str, reference: str) -> Issue:
    severity = {"E": "error", "W": "warning", "I": "info"}[code[0]]
    return Issue(code, severity, rel, None, message, reference)


def _check_required_fm(rel: str, data: dict[str, object], issues: list[Issue]) -> None:
    if "name" not in data:
        issues.append(_issue("E-FM-003", rel, "required field `name` missing", "SPEC §4.1"))
    if "description" not in data:
        issues.append(_issue("E-FM-004", rel, "required field `description` missing", "SPEC §4.1"))
    else:
        desc = data.get("description")
        if isinstance(desc, str) and len(desc) > 150:
            issues.append(
                _issue(
                    "W-FM-002",
                    rel,
                    f"description exceeds 150 characters (len={len(desc)})",
                    "SPEC §7.2",
                )
            )
    if "type" not in data:
        issues.append(_issue("E-FM-005", rel, "required field `type` missing", "SPEC §4.1"))
    elif data["type"] not in _VALID_TYPES:
        issues.append(
            _issue(
                "E-FM-006",
                rel,
                f"type {data['type']!r} is not one of {sorted(_VALID_TYPES)}",
                "SPEC §4.1",
            )
        )
    if "scope" not in data:
        issues.append(_issue("E-FM-007", rel, "required field `scope` missing", "SPEC §4.1"))
    elif data["scope"] not in _VALID_SCOPES:
        issues.append(
            _issue(
                "E-FM-008",
                rel,
                f"scope {data['scope']!r} is not one of {sorted(_VALID_SCOPES)}",
                "SPEC §4.1",
            )
        )

    if data.get("scope") == "org" and not data.get("org"):
        issues.append(_issue("E-FM-011", rel, "scope=org requires `org:`", "SPEC §8.1"))
    if data.get("scope") == "team" and not data.get("team"):
        issues.append(_issue("E-FM-012", rel, "scope=team requires `team:`", "SPEC §8.1"))
    if data.get("scope") == "pool" and not data.get("pool"):
        issues.append(_issue("E-FM-009", rel, "scope=pool requires `pool:`", "SPEC §8.2"))


def _check_mem_subtype(
    rel: str, data: dict[str, object], body: str | None, issues: list[Issue]
) -> None:
    mtype = data.get("type")
    enforcement = data.get("enforcement")

    if mtype == "feedback":
        if enforcement is None:
            issues.append(
                Issue(
                    "E-MEM-001",
                    "error",
                    rel,
                    None,
                    "feedback subtype requires `enforcement:` (mandatory/default/hint)",
                    "SPEC §4.3",
                )
            )
        if body is not None and not (_WHY_RE.search(body) and _HOW_RE.search(body)):
            issues.append(
                Issue(
                    "E-MEM-003",
                    "error",
                    rel,
                    None,
                    "feedback body must contain both **Why:** and **How to apply:** sections",
                    "SPEC §4.3",
                )
            )

    if enforcement is not None and enforcement not in _VALID_ENFORCEMENTS:
        issues.append(
            Issue(
                "E-MEM-002",
                "error",
                rel,
                None,
                f"enforcement {enforcement!r} is not one of {sorted(_VALID_ENFORCEMENTS)}",
                "SPEC §8.3",
            )
        )

    if (
        mtype == "project"
        and body is not None
        and not (_WHY_RE.search(body) and _HOW_RE.search(body))
    ):
        issues.append(
            Issue(
                "E-MEM-004",
                "error",
                rel,
                None,
                "project body must contain both **Why:** and **How to apply:** sections",
                "SPEC §4.4",
            )
        )

    if mtype == "workflow_ptr" and not data.get("workflow_ref"):
        issues.append(
            Issue(
                "E-MEM-005",
                "error",
                rel,
                None,
                "workflow_ptr requires `workflow_ref:`",
                "SPEC §4.6",
            )
        )

    if mtype == "agent":
        if not data.get("source"):
            issues.append(
                Issue(
                    "E-MEM-007",
                    "error",
                    rel,
                    None,
                    "agent subtype requires `source:`",
                    "SPEC §4.7",
                )
            )
        if "confidence" not in data:
            issues.append(
                Issue(
                    "W-MEM-002",
                    "warning",
                    rel,
                    None,
                    "agent asset missing `confidence:` (recommended)",
                    "SPEC §4.7 / §4.8",
                )
            )


# ------------------------------------------------------------------
# IDX-*
# ------------------------------------------------------------------


def _check_memory_index(project_root: Path, records: list[_AssetRecord]) -> list[Issue]:
    issues: list[Issue] = []
    mem = memory_dir(project_root)
    index_path = mem / "MEMORY.md"
    if not index_path.is_file():
        return issues

    index_text = index_path.read_text(encoding="utf-8")

    # E-IDX-001: dangling links in MEMORY.md
    for target in _MD_LINK_RE.findall(index_text):
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        resolved = (mem / target).resolve()
        if not resolved.exists():
            issues.append(
                Issue(
                    "E-IDX-001",
                    "error",
                    index_path.relative_to(project_root).as_posix(),
                    None,
                    f"link to non-existent file: {target}",
                    "SPEC §7.2",
                )
            )

    # E-IDX-002: every asset must be mentioned somewhere in MEMORY.md
    # (text-level presence check — links or bare paths both count).
    for rec in records:
        if rec.data is None:
            continue
        # Link path in MEMORY.md is relative to .memory/, e.g. "local/user_foo.md".
        if rec.rel_path not in index_text:
            issues.append(
                Issue(
                    "E-IDX-002",
                    "error",
                    rec.rel_path,
                    None,
                    f"asset {rec.rel_path} is not referenced in MEMORY.md",
                    "SPEC §7.2",
                )
            )

    return issues


# ------------------------------------------------------------------
# REF-*
# ------------------------------------------------------------------


def _check_references(
    project_root: Path,
    records: list[_AssetRecord],
    asset_ids: set[str],
) -> list[Issue]:
    issues: list[Issue] = []
    for rec in records:
        if rec.data is None:
            continue
        refs = rec.data.get("references") or []
        if isinstance(refs, list):
            for ref in refs:
                if isinstance(ref, str) and ref not in asset_ids:
                    issues.append(
                        Issue(
                            "E-REF-001",
                            "error",
                            rec.rel_path,
                            None,
                            f"references entry points to non-existent asset: {ref}",
                            "SPEC §3.3 MUST 4",
                        )
                    )
        supers = rec.data.get("supersedes")
        if isinstance(supers, str) and supers and supers not in asset_ids:
            issues.append(
                Issue(
                    "E-REF-003",
                    "error",
                    rec.rel_path,
                    None,
                    f"supersedes target does not exist: {supers}",
                    "SPEC §4.1",
                )
            )
    return issues


# ------------------------------------------------------------------
# Output rendering + CLI
# ------------------------------------------------------------------


def render_text(issues: list[Issue]) -> str:
    if not issues:
        return "clean — no errors, no warnings"
    lines: list[str] = []
    by_file: dict[str, list[Issue]] = {}
    for i in issues:
        by_file.setdefault(i.file, []).append(i)
    for file, file_issues in sorted(by_file.items()):
        lines.append(f"{file}:")
        for i in file_issues:
            lines.append(f"  {i.code} ({i.severity}) {i.message}")
            lines.append(f"    → {i.reference}")
        lines.append("")
    errors = sum(1 for i in issues if i.severity == "error")
    warnings = sum(1 for i in issues if i.severity == "warning")
    info = sum(1 for i in issues if i.severity == "info")
    exit_code = compute_exit_code(issues)
    lines.append(f"{errors} error(s), {warnings} warning(s), {info} info — exit {exit_code}")
    return "\n".join(lines)


def render_json(issues: list[Issue]) -> str:
    errors = sum(1 for i in issues if i.severity == "error")
    warnings = sum(1 for i in issues if i.severity == "warning")
    info = sum(1 for i in issues if i.severity == "info")
    payload = {
        "summary": {
            "errors": errors,
            "warnings": warnings,
            "info": info,
            "exit_code": compute_exit_code(issues),
        },
        "issues": [asdict(i) for i in issues],
    }
    return json.dumps(payload)


@click.command("validate")
@click.pass_obj
def validate_cmd(cfg: GlobalConfig) -> None:
    """Run SPEC §12 validators and exit with 0 (clean) / 1 (warnings) / 2 (errors)."""
    root = cfg.resolve_project_root()
    issues = run_validate(root)
    if cfg.output_format == "json":
        click.echo(render_json(issues))
    else:
        click.echo(render_text(issues))
    sys.exit(compute_exit_code(issues))
