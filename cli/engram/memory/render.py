"""Serialize a MemoryFrontmatter + body to a SPEC §4.1-compliant .md file."""

from __future__ import annotations

from datetime import date
from typing import Any

import yaml

from engram.core.frontmatter import MemoryFrontmatter


def render_asset_file(fm: MemoryFrontmatter, body: str) -> str:
    """Serialize a MemoryFrontmatter + body to a SPEC-compliant .md file."""
    data = frontmatter_to_dict(fm)
    yaml_block = yaml.dump(
        data,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )
    body_tail = body if body.endswith("\n") else body + "\n"
    return f"---\n{yaml_block}---\n\n{body_tail}"


def frontmatter_to_dict(fm: MemoryFrontmatter) -> dict[str, Any]:
    """Ordered dict suitable for YAML dump. Omits None / empty optional fields."""
    data: dict[str, Any] = {
        "name": fm.name,
        "description": fm.description,
        "type": fm.type.value,
        "scope": fm.scope.value,
        "enforcement": fm.enforcement.value,
    }
    for field_name, field_value in (
        ("org", fm.org),
        ("team", fm.team),
        ("pool", fm.pool),
        ("subscribed_at", fm.subscribed_at.value if fm.subscribed_at else None),
    ):
        if field_value:
            data[field_name] = field_value

    _maybe_date(data, "created", fm.created)
    _maybe_date(data, "updated", fm.updated)
    if fm.tags:
        data["tags"] = list(fm.tags)
    _maybe_date(data, "expires", fm.expires)
    _maybe_date(data, "valid_from", fm.valid_from)
    _maybe_date(data, "valid_to", fm.valid_to)
    if fm.source:
        data["source"] = fm.source
    if fm.references:
        data["references"] = list(fm.references)
    if fm.overrides:
        data["overrides"] = fm.overrides
    if fm.supersedes:
        data["supersedes"] = fm.supersedes
    if fm.limitations:
        data["limitations"] = list(fm.limitations)
    if fm.confidence:
        data["confidence"] = {
            "validated_count": fm.confidence.validated_count,
            "contradicted_count": fm.confidence.contradicted_count,
            "last_validated": fm.confidence.last_validated.isoformat(),
            "usage_count": fm.confidence.usage_count,
        }
    if fm.workflow_ref:
        data["workflow_ref"] = fm.workflow_ref

    # Unknown fields preserved last (SPEC §4.1).
    for k, v in fm.extra.items():
        if k not in data:
            data[k] = v

    return data


def _maybe_date(data: dict[str, Any], key: str, value: date | None) -> None:
    if value is not None:
        data[key] = value.isoformat()
