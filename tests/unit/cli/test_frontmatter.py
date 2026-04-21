"""T-12 tests for engram.core.frontmatter — parse + validate per SPEC §4.1."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from textwrap import dedent

import pytest

from engram.core.frontmatter import (
    Confidence,
    Enforcement,
    FrontmatterError,
    InvalidEnumValueError,
    MemoryFrontmatter,
    MemoryType,
    MissingFieldError,
    Scope,
    parse_file,
    parse_frontmatter,
)


# ------------------------------------------------------------------
# Happy path — each subtype
# ------------------------------------------------------------------


def test_parse_minimal_user_subtype() -> None:
    src = dedent("""\
        ---
        name: user is a platform lead
        description: ten years Go, Kubernetes primary stack
        type: user
        scope: user
        ---

        The user leads the platform team.
        """)
    fm = parse_frontmatter(src)
    assert fm.name == "user is a platform lead"
    assert fm.description == "ten years Go, Kubernetes primary stack"
    assert fm.type is MemoryType.USER
    assert fm.scope is Scope.USER
    assert fm.enforcement is Enforcement.HINT  # default
    assert fm.tags == ()


def test_parse_feedback_with_enforcement() -> None:
    src = dedent("""\
        ---
        name: prefer table-driven tests
        description: write Go tests as table-driven subtests
        type: feedback
        scope: user
        enforcement: hint
        tags: [go, style]
        ---

        Body.
        """)
    fm = parse_frontmatter(src)
    assert fm.type is MemoryType.FEEDBACK
    assert fm.enforcement is Enforcement.HINT
    assert fm.tags == ("go", "style")


def test_parse_workflow_ptr() -> None:
    src = dedent("""\
        ---
        name: git merge workflow
        description: standard merge procedure
        type: workflow_ptr
        scope: team
        team: platform
        workflow_ref: workflows/git-merge-standard/
        ---
        """)
    fm = parse_frontmatter(src)
    assert fm.type is MemoryType.WORKFLOW_PTR
    assert fm.workflow_ref == "workflows/git-merge-standard/"
    assert fm.team == "platform"


def test_parse_agent_with_confidence_and_limitations() -> None:
    src = dedent("""\
        ---
        name: squash before merge prevents flakiness
        description: squashing locally reduces CI re-run rate
        type: agent
        scope: project
        enforcement: hint
        source: autolearn/git-merge-standard/r5
        confidence:
          validated_count: 5
          contradicted_count: 0
          last_validated: 2026-04-17
          usage_count: 7
        limitations:
          - observed only on platform service repos
          - may not apply under individual authorship requirements
        ---

        Body.
        """)
    fm = parse_frontmatter(src)
    assert fm.type is MemoryType.AGENT
    assert fm.source == "autolearn/git-merge-standard/r5"
    assert fm.confidence == Confidence(
        validated_count=5,
        contradicted_count=0,
        last_validated=date(2026, 4, 17),
        usage_count=7,
    )
    assert fm.limitations == (
        "observed only on platform service repos",
        "may not apply under individual authorship requirements",
    )


def test_parse_org_scope() -> None:
    src = dedent("""\
        ---
        name: SPDX headers required
        description: every source file needs an SPDX header
        type: feedback
        scope: org
        org: acme
        enforcement: mandatory
        ---
        """)
    fm = parse_frontmatter(src)
    assert fm.scope is Scope.ORG
    assert fm.org == "acme"
    assert fm.enforcement is Enforcement.MANDATORY


def test_parse_pool_scope_with_subscribed_at() -> None:
    src = dedent("""\
        ---
        name: compliance checklist pool rule
        description: pool-sourced mandatory rule
        type: feedback
        scope: pool
        pool: compliance-checklists
        subscribed_at: team
        enforcement: mandatory
        ---
        """)
    fm = parse_frontmatter(src)
    assert fm.scope is Scope.POOL
    assert fm.pool == "compliance-checklists"
    assert fm.subscribed_at is Scope.TEAM


# ------------------------------------------------------------------
# Optional fields — dates, lists, references
# ------------------------------------------------------------------


def test_dates_parse_as_date_objects() -> None:
    src = dedent("""\
        ---
        name: a
        description: b
        type: project
        scope: project
        created: 2026-04-10
        updated: 2026-04-18
        expires: 2026-07-01
        valid_from: 2026-04-10
        valid_to: 2026-06-30
        ---
        """)
    fm = parse_frontmatter(src)
    assert fm.created == date(2026, 4, 10)
    assert fm.updated == date(2026, 4, 18)
    assert fm.expires == date(2026, 7, 1)
    assert fm.valid_from == date(2026, 4, 10)
    assert fm.valid_to == date(2026, 6, 30)


def test_string_dates_coerce_to_date() -> None:
    """Quoted ISO 8601 strings still coerce."""
    src = dedent("""\
        ---
        name: a
        description: b
        type: project
        scope: project
        created: "2026-04-10"
        ---
        """)
    fm = parse_frontmatter(src)
    assert fm.created == date(2026, 4, 10)


def test_references_and_lists_become_tuples() -> None:
    src = dedent("""\
        ---
        name: a
        description: b
        type: project
        scope: project
        tags: [go, migration]
        references:
          - user/user_role
          - project/previous_decision
        ---
        """)
    fm = parse_frontmatter(src)
    assert isinstance(fm.tags, tuple)
    assert fm.tags == ("go", "migration")
    assert isinstance(fm.references, tuple)
    assert fm.references == ("user/user_role", "project/previous_decision")


def test_unknown_fields_preserved_in_extra() -> None:
    """SPEC §4.1: unknown fields MUST be preserved on rewrite."""
    src = dedent("""\
        ---
        name: a
        description: b
        type: user
        scope: user
        future_field: some-value
        nested:
          inner: 42
        ---
        """)
    fm = parse_frontmatter(src)
    assert fm.extra == {"future_field": "some-value", "nested": {"inner": 42}}


# ------------------------------------------------------------------
# Validation errors
# ------------------------------------------------------------------


@pytest.mark.parametrize("missing", ["name", "description", "type", "scope"])
def test_missing_required_top_level_field_raises(missing: str) -> None:
    fields = {
        "name": "a",
        "description": "b",
        "type": "user",
        "scope": "user",
    }
    del fields[missing]
    src = "---\n" + "\n".join(f"{k}: {v}" for k, v in fields.items()) + "\n---\n"
    with pytest.raises(MissingFieldError, match=missing):
        parse_frontmatter(src)


def test_invalid_type_enum_raises() -> None:
    src = dedent("""\
        ---
        name: a
        description: b
        type: made_up
        scope: user
        ---
        """)
    with pytest.raises(InvalidEnumValueError, match="type"):
        parse_frontmatter(src)


def test_invalid_scope_enum_raises() -> None:
    src = dedent("""\
        ---
        name: a
        description: b
        type: user
        scope: galaxy
        ---
        """)
    with pytest.raises(InvalidEnumValueError, match="scope"):
        parse_frontmatter(src)


def test_invalid_enforcement_enum_raises() -> None:
    src = dedent("""\
        ---
        name: a
        description: b
        type: feedback
        scope: user
        enforcement: always
        ---
        """)
    with pytest.raises(InvalidEnumValueError, match="enforcement"):
        parse_frontmatter(src)


def test_feedback_without_enforcement_raises() -> None:
    src = dedent("""\
        ---
        name: a
        description: b
        type: feedback
        scope: user
        ---
        """)
    with pytest.raises(MissingFieldError, match="enforcement"):
        parse_frontmatter(src)


def test_workflow_ptr_without_workflow_ref_raises() -> None:
    src = dedent("""\
        ---
        name: a
        description: b
        type: workflow_ptr
        scope: project
        ---
        """)
    with pytest.raises(MissingFieldError, match="workflow_ref"):
        parse_frontmatter(src)


def test_agent_without_source_raises() -> None:
    src = dedent("""\
        ---
        name: a
        description: b
        type: agent
        scope: project
        ---
        """)
    with pytest.raises(MissingFieldError, match="source"):
        parse_frontmatter(src)


def test_scope_org_without_org_name_raises() -> None:
    src = dedent("""\
        ---
        name: a
        description: b
        type: user
        scope: org
        ---
        """)
    with pytest.raises(MissingFieldError, match="org"):
        parse_frontmatter(src)


def test_scope_team_without_team_name_raises() -> None:
    src = dedent("""\
        ---
        name: a
        description: b
        type: user
        scope: team
        ---
        """)
    with pytest.raises(MissingFieldError, match="team"):
        parse_frontmatter(src)


def test_scope_pool_without_pool_name_raises() -> None:
    src = dedent("""\
        ---
        name: a
        description: b
        type: user
        scope: pool
        subscribed_at: team
        ---
        """)
    with pytest.raises(MissingFieldError, match="pool"):
        parse_frontmatter(src)


def test_scope_pool_without_subscribed_at_raises() -> None:
    src = dedent("""\
        ---
        name: a
        description: b
        type: user
        scope: pool
        pool: some-pool
        ---
        """)
    with pytest.raises(MissingFieldError, match="subscribed_at"):
        parse_frontmatter(src)


def test_subscribed_at_pool_is_invalid() -> None:
    """subscribed_at is restricted to org/team/user/project (SPEC §4.1)."""
    src = dedent("""\
        ---
        name: a
        description: b
        type: user
        scope: pool
        pool: x
        subscribed_at: pool
        ---
        """)
    with pytest.raises(InvalidEnumValueError, match="subscribed_at"):
        parse_frontmatter(src)


def test_missing_frontmatter_block_raises() -> None:
    with pytest.raises(FrontmatterError, match="frontmatter"):
        parse_frontmatter("no frontmatter here, just a body\n")


def test_malformed_yaml_raises() -> None:
    src = "---\nname: [unclosed\n---\n"
    with pytest.raises(FrontmatterError):
        parse_frontmatter(src)


def test_frontmatter_not_a_mapping_raises() -> None:
    src = "---\n- just\n- a list\n---\n"
    with pytest.raises(FrontmatterError, match="mapping"):
        parse_frontmatter(src)


# ------------------------------------------------------------------
# Confidence validation
# ------------------------------------------------------------------


@pytest.mark.parametrize(
    "missing",
    ["validated_count", "contradicted_count", "last_validated", "usage_count"],
)
def test_confidence_missing_subfield_raises(missing: str) -> None:
    block = {
        "validated_count": 1,
        "contradicted_count": 0,
        "last_validated": "2026-04-17",
        "usage_count": 3,
    }
    del block[missing]
    conf_lines = "\n".join(f"  {k}: {v}" for k, v in block.items())
    src = (
        "---\n"
        "name: a\n"
        "description: b\n"
        "type: user\n"
        "scope: user\n"
        "confidence:\n"
        f"{conf_lines}\n"
        "---\n"
    )
    with pytest.raises(MissingFieldError, match=missing):
        parse_frontmatter(src)


def test_confidence_negative_count_raises() -> None:
    src = dedent("""\
        ---
        name: a
        description: b
        type: user
        scope: user
        confidence:
          validated_count: -1
          contradicted_count: 0
          last_validated: 2026-04-17
          usage_count: 3
        ---
        """)
    with pytest.raises(FrontmatterError, match="validated_count"):
        parse_frontmatter(src)


def test_confidence_boolean_count_rejected() -> None:
    """bool is a subclass of int in Python — reject it anyway."""
    src = dedent("""\
        ---
        name: a
        description: b
        type: user
        scope: user
        confidence:
          validated_count: true
          contradicted_count: 0
          last_validated: 2026-04-17
          usage_count: 3
        ---
        """)
    with pytest.raises(FrontmatterError, match="validated_count"):
        parse_frontmatter(src)


# ------------------------------------------------------------------
# File-level parsing
# ------------------------------------------------------------------


def test_parse_file_returns_body(tmp_path: Path) -> None:
    src = dedent("""\
        ---
        name: a
        description: b
        type: user
        scope: user
        ---

        This is the body of the memory asset.
        Multiple lines.
        """)
    target = tmp_path / "user_example.md"
    target.write_text(src, encoding="utf-8")
    fm, body = parse_file(target)
    assert isinstance(fm, MemoryFrontmatter)
    assert fm.name == "a"
    assert "body of the memory" in body
    assert "Multiple lines." in body


def test_parse_frontmatter_handles_missing_body() -> None:
    """A memory file can end immediately after the closing ---."""
    src = "---\nname: a\ndescription: b\ntype: user\nscope: user\n---"
    fm = parse_frontmatter(src)
    assert fm.name == "a"


# ------------------------------------------------------------------
# Misc
# ------------------------------------------------------------------


def test_tags_accepts_empty_list() -> None:
    src = dedent("""\
        ---
        name: a
        description: b
        type: user
        scope: user
        tags: []
        ---
        """)
    fm = parse_frontmatter(src)
    assert fm.tags == ()


def test_tags_non_list_raises() -> None:
    src = dedent("""\
        ---
        name: a
        description: b
        type: user
        scope: user
        tags: just-a-string
        ---
        """)
    with pytest.raises(FrontmatterError, match="tags"):
        parse_frontmatter(src)


def test_error_classes_hierarchy() -> None:
    """All frontmatter errors are ValueError subclasses for ergonomic catches."""
    assert issubclass(FrontmatterError, ValueError)
    assert issubclass(MissingFieldError, FrontmatterError)
    assert issubclass(InvalidEnumValueError, FrontmatterError)
