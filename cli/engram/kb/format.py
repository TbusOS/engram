"""On-disk format contracts for KB articles (SPEC §6.2 / §6.5).

- ``README.md`` frontmatter + body (:class:`KbFrontmatter`)
- ``_compile_state.toml`` (:class:`CompileState`)
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover — Py 3.11+ everywhere we ship
    import tomli as tomllib

__all__ = [
    "CompileState",
    "KbFormatError",
    "KbFrontmatter",
    "parse_compile_state",
    "parse_readme",
    "render_compile_state",
    "render_readme",
]

_LIFECYCLE_STATES: frozenset[str] = frozenset(
    {"draft", "active", "stable", "deprecated", "archived", "tombstoned"}
)
_SCOPES: frozenset[str] = frozenset({"org", "team", "user", "project", "pool"})

MAX_README_FILE_BYTES = 1 * 1024 * 1024
MAX_STATE_FILE_BYTES = 1 * 1024 * 1024
_FRONTMATTER_DELIM = "---"

_REQUIRED_FM = ("name", "description", "type", "scope", "lifecycle_state")
_KNOWN_FM = frozenset(
    {
        *_REQUIRED_FM,
        "primary_author",
        "chapters",
        "compiled_from",
        "compiled_at",
        "tags",
        "references",
    }
)


class KbFormatError(ValueError):
    """Raised when a KB on-disk file cannot be parsed/validated."""


@dataclass(frozen=True, slots=True)
class KbFrontmatter:
    """Typed ``README.md`` frontmatter (SPEC §6.2)."""

    name: str
    description: str
    scope: str
    lifecycle_state: str = "draft"
    type: str = "kb"
    primary_author: str = ""
    chapters: tuple[str, ...] = ()
    compiled_from: tuple[str, ...] = ()
    compiled_at: str | None = None
    tags: tuple[str, ...] = ()
    references: tuple[str, ...] = ()
    extra: dict[str, Any] = field(default_factory=dict)

    def to_yaml_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "type": "kb",
            "scope": self.scope,
            "lifecycle_state": self.lifecycle_state,
        }
        if self.primary_author:
            out["primary_author"] = self.primary_author
        if self.chapters:
            out["chapters"] = list(self.chapters)
        if self.compiled_from:
            out["compiled_from"] = list(self.compiled_from)
        if self.compiled_at is not None:
            out["compiled_at"] = self.compiled_at
        if self.tags:
            out["tags"] = list(self.tags)
        if self.references:
            out["references"] = list(self.references)
        for key, value in self.extra.items():
            out.setdefault(key, value)
        return out


def _as_str_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple)):
        return tuple(str(v) for v in value)
    raise KbFormatError(f"expected a string list, got {type(value).__name__}")


def parse_readme_frontmatter(data: dict[str, Any]) -> KbFrontmatter:
    if not isinstance(data, dict):
        raise KbFormatError("README.md frontmatter must be a mapping")
    missing = [k for k in _REQUIRED_FM if k not in data]
    if missing:
        raise KbFormatError(f"README.md missing required field(s): {missing}")
    if data["type"] != "kb":
        raise KbFormatError(f"type must be 'kb', got {data['type']!r}")
    scope = str(data["scope"])
    if scope not in _SCOPES:
        raise KbFormatError(f"invalid scope {scope!r}; expected one of {_SCOPES}")
    lifecycle = str(data["lifecycle_state"])
    if lifecycle not in _LIFECYCLE_STATES:
        raise KbFormatError(
            f"invalid lifecycle_state {lifecycle!r}; expected one of {_LIFECYCLE_STATES}"
        )
    extra = {k: v for k, v in data.items() if k not in _KNOWN_FM}
    return KbFrontmatter(
        name=str(data["name"]),
        description=str(data["description"]),
        scope=scope,
        lifecycle_state=lifecycle,
        primary_author=str(data.get("primary_author") or ""),
        chapters=_as_str_tuple(data.get("chapters")),
        compiled_from=_as_str_tuple(data.get("compiled_from")),
        compiled_at=(None if data.get("compiled_at") is None else str(data["compiled_at"])),
        tags=_as_str_tuple(data.get("tags")),
        references=_as_str_tuple(data.get("references")),
        extra=extra,
    )


def parse_readme(path: Path) -> tuple[KbFrontmatter, str]:
    """Parse ``README.md`` -> (frontmatter, body). Body returned verbatim."""
    try:
        with open(path, "rb") as fh:
            raw = fh.read(MAX_README_FILE_BYTES + 1)
    except OSError as exc:
        raise KbFormatError(f"cannot read {path}: {exc}") from exc
    if len(raw) > MAX_README_FILE_BYTES:
        raise KbFormatError(f"{path} exceeds {MAX_README_FILE_BYTES}-byte cap")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise KbFormatError(f"{path} is not valid UTF-8: {exc}") from exc
    if not text.startswith(_FRONTMATTER_DELIM):
        raise KbFormatError(f"missing leading '---' frontmatter in {path}")
    rest = text[len(_FRONTMATTER_DELIM) :]
    end_idx = rest.find("\n" + _FRONTMATTER_DELIM)
    if end_idx < 0:
        raise KbFormatError(f"missing closing '---' frontmatter in {path}")
    yaml_text = rest[:end_idx].lstrip("\n")
    body_after = rest[end_idx + len("\n" + _FRONTMATTER_DELIM) :]
    if body_after.startswith("\n"):
        body_after = body_after[1:]
    try:
        data = yaml.safe_load(yaml_text) or {}
    except yaml.YAMLError as exc:
        raise KbFormatError(f"YAML parse failed for {path}: {exc}") from exc
    return parse_readme_frontmatter(data), body_after


def render_readme(fm: KbFrontmatter, body: str) -> str:
    yaml_text = yaml.safe_dump(
        fm.to_yaml_dict(), sort_keys=False, allow_unicode=True, default_flow_style=False
    )
    if not body.endswith("\n"):
        body = body + "\n"
    return f"{_FRONTMATTER_DELIM}\n{yaml_text}{_FRONTMATTER_DELIM}\n{body}"


# ----------------------------------------------------------------------
# _compile_state.toml (SPEC §6.5)
# ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CompileState:
    files: tuple[str, ...]
    hashes: dict[str, str]
    compiled_at: str
    tool_version: str = "engram 0.2.0"
    model: str = "local/none"
    is_stale: bool = False
    detected_at: str | None = None


def parse_compile_state(path: Path) -> CompileState:
    # Bounded read: a shared/pulled KB dir could plant a multi-GB state
    # file, and `kb list` parses one per article.
    try:
        with open(path, "rb") as fh:
            raw = fh.read(MAX_STATE_FILE_BYTES + 1)
    except OSError as exc:
        raise KbFormatError(f"cannot read {path}: {exc}") from exc
    if len(raw) > MAX_STATE_FILE_BYTES:
        raise KbFormatError(f"{path} exceeds {MAX_STATE_FILE_BYTES}-byte cap")
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise KbFormatError(f"cannot parse {path}: {exc}") from exc
    source = data.get("source", {})
    compile_ = data.get("compile", {})
    stale = data.get("stale", {})
    files = source.get("files", []) if isinstance(source, dict) else []
    hashes = source.get("hashes", {}) if isinstance(source, dict) else {}
    return CompileState(
        files=tuple(str(f) for f in files),
        hashes={str(k): str(v) for k, v in hashes.items()} if isinstance(hashes, dict) else {},
        compiled_at=str(compile_.get("at", "")) if isinstance(compile_, dict) else "",
        tool_version=str(compile_.get("tool_version", "engram 0.2.0"))
        if isinstance(compile_, dict)
        else "engram 0.2.0",
        model=(
            str(compile_.get("model", "local/none")) if isinstance(compile_, dict) else "local/none"
        ),
        is_stale=bool(stale.get("is_stale", False)) if isinstance(stale, dict) else False,
        detected_at=(
            None if not isinstance(stale, dict) or stale.get("detected_at") in (None, "")
            else str(stale["detected_at"])
        ),
    )


def render_compile_state(state: CompileState) -> str:
    lines = ["[source]"]
    files_repr = ", ".join(f'"{f}"' for f in state.files)
    lines.append(f"files = [{files_repr}]")
    lines.append("")
    lines.append("[source.hashes]")
    for fname in state.files:
        h = state.hashes.get(fname, "")
        lines.append(f'"{fname}" = "{h}"')
    lines.append("")
    lines.append("[compile]")
    lines.append(f'at = "{state.compiled_at}"')
    lines.append(f'tool_version = "{state.tool_version}"')
    lines.append(f'model = "{state.model}"')
    lines.append("")
    lines.append("[stale]")
    lines.append(f"is_stale = {'true' if state.is_stale else 'false'}")
    if state.detected_at:
        lines.append(f'detected_at = "{state.detected_at}"')
    else:
        lines.append("detected_at = false")
    return "\n".join(lines) + "\n"
