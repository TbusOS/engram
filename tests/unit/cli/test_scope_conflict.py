"""T-39 tests: SPEC §8.4 conflict-resolution decision tree.

``resolve_conflict()`` is the pure function that encodes SPEC §8.4:

1. **Enforcement level wins absolutely** — `mandatory` > `default` > `hint`,
   regardless of scope.
2. **Within the same enforcement, hierarchy specificity wins** —
   `project > user > team > org`.
3. **Pool assets use `subscribed_at` as their effective hierarchy**, and a
   native asset at the same level beats a pool asset ("native first").
4. **Same enforcement + same effective level + different sources** → no
   deterministic winner; both assets load and the LLM arbitrates.
5. **Internal conflict inside one pool** → the resolver flags it as a
   pool-publish-time error (downstream consumers raise).

The tests below cover every rule plus edge cases (single-candidate, empty,
ties at higher levels of the hierarchy) so adding a new conflict scenario
later has a drop-in place in the suite.
"""

from __future__ import annotations

import pytest

from engram.core.scope_conflict import (
    ConflictCandidate,
    PoolInternalConflict,
    Resolution,
    resolve_conflict,
)


def _c(
    id_: str,
    scope: str,
    enforcement: str,
    *,
    subscribed_at: str | None = None,
    source: str | None = None,
) -> ConflictCandidate:
    """Convenience builder — source defaults to the scope for brevity."""
    return ConflictCandidate(
        id=id_,
        scope=scope,
        enforcement=enforcement,
        subscribed_at=subscribed_at,
        source=source if source is not None else scope,
    )


# ------------------------------------------------------------------
# Rule 0 — edge cases around input arity
# ------------------------------------------------------------------


def test_single_candidate_wins_trivially() -> None:
    only = _c("local/feedback_only", "project", "default")
    res = resolve_conflict([only])
    assert res.winner == only.id
    assert res.losers == ()
    assert res.rule == 0


def test_empty_candidate_list_raises() -> None:
    with pytest.raises(ValueError, match="at least one"):
        resolve_conflict([])


# ------------------------------------------------------------------
# Rule 1 — enforcement is absolute
# ------------------------------------------------------------------


def test_rule_1_org_mandatory_beats_project_hint() -> None:
    """SPEC §8.4 Example 1."""
    org = _c("org/acme/feedback_no_push_to_main", "org", "mandatory")
    proj = _c("local/feedback_bypass", "project", "hint")
    res = resolve_conflict([proj, org])
    assert res.winner == org.id
    assert res.rule == 1
    assert "mandatory" in res.reason.lower()


def test_rule_1_org_mandatory_beats_project_default() -> None:
    org = _c("org/acme/feedback_compliance", "org", "mandatory")
    proj = _c("local/feedback_bypass", "project", "default")
    res = resolve_conflict([proj, org])
    assert res.winner == org.id
    assert res.rule == 1


def test_rule_1_most_specific_mandatory_wins_among_mandatories() -> None:
    """When two mandatories collide, rule 1 alone doesn't pick — rule 2 does."""
    org = _c("org/acme/feedback_x", "org", "mandatory")
    user = _c("user/feedback_x", "user", "mandatory")
    team = _c("team/platform/feedback_x", "team", "default")
    res = resolve_conflict([org, user, team])
    assert res.winner == user.id
    assert res.rule == 2  # rule 1 narrows to {org, user}; rule 2 picks user
    assert team.id in res.losers
    assert org.id in res.losers


# ------------------------------------------------------------------
# Rule 2 — hierarchy specificity
# ------------------------------------------------------------------


def test_rule_2_project_beats_team_same_enforcement() -> None:
    proj = _c("local/feedback_pref", "project", "default")
    team = _c("team/platform/feedback_pref", "team", "default")
    res = resolve_conflict([team, proj])
    assert res.winner == proj.id
    assert res.rule == 2


def test_rule_2_user_beats_team_same_enforcement() -> None:
    user = _c("user/feedback_pref", "user", "default")
    team = _c("team/platform/feedback_pref", "team", "default")
    res = resolve_conflict([team, user])
    assert res.winner == user.id
    assert res.rule == 2


def test_rule_2_team_beats_org_same_enforcement() -> None:
    team = _c("team/platform/feedback_pref", "team", "default")
    org = _c("org/acme/feedback_pref", "org", "default")
    res = resolve_conflict([org, team])
    assert res.winner == team.id
    assert res.rule == 2


def test_rule_2_project_beats_user_at_hint_level_too() -> None:
    proj = _c("local/feedback_pref", "project", "hint")
    user = _c("user/feedback_pref", "user", "hint")
    res = resolve_conflict([user, proj])
    assert res.winner == proj.id
    assert res.rule == 2


# ------------------------------------------------------------------
# Rule 3 — pool uses subscribed_at; native beats pool at same level
# ------------------------------------------------------------------


def test_rule_3_pool_at_user_loses_to_project_default() -> None:
    """SPEC §8.4 Example 3 (generalized): pool-at-user still loses to project
    because project is more specific."""
    pool = _c(
        "pools/kernel-work/feedback_rebase",
        "pool",
        "hint",
        subscribed_at="user",
        source="pool/kernel-work",
    )
    proj = _c("local/feedback_merge", "project", "hint")
    res = resolve_conflict([pool, proj])
    assert res.winner == proj.id
    assert res.rule == 2


def test_rule_3_native_team_beats_pool_at_team() -> None:
    pool = _c(
        "pools/kernel-work/feedback_rebase",
        "pool",
        "hint",
        subscribed_at="team",
        source="pool/kernel-work",
    )
    team = _c("team/platform/feedback_merge", "team", "hint")
    res = resolve_conflict([pool, team])
    assert res.winner == team.id
    assert res.rule == 3
    assert "native" in res.reason.lower()


def test_rule_3_native_project_beats_pool_at_project() -> None:
    """SPEC §8.4 rule 3: 'native project still wins over pool-at-project
    because native assets are resolved first.'"""
    pool = _c(
        "pools/template/feedback_x",
        "pool",
        "default",
        subscribed_at="project",
        source="pool/template",
    )
    proj = _c("local/feedback_x", "project", "default")
    res = resolve_conflict([pool, proj])
    assert res.winner == proj.id
    assert res.rule == 3


def test_rule_3_native_org_beats_pool_at_org() -> None:
    pool = _c(
        "pools/compliance/feedback_x",
        "pool",
        "default",
        subscribed_at="org",
        source="pool/compliance",
    )
    org = _c("org/acme/feedback_x", "org", "default")
    res = resolve_conflict([pool, org])
    assert res.winner == org.id
    assert res.rule == 3


# ------------------------------------------------------------------
# Rule 4 — LLM arbitrates
# ------------------------------------------------------------------


def test_rule_4_two_projects_arbitrated() -> None:
    a = _c("local/feedback_tabs", "project", "hint", source="project:a")
    b = _c("local/feedback_spaces", "project", "hint", source="project:b")
    res = resolve_conflict([a, b])
    assert res.winner is None
    assert res.rule == 4
    assert set(res.losers) == {a.id, b.id}
    assert "llm" in res.reason.lower() or "arbitrate" in res.reason.lower()


def test_rule_4_two_pools_at_same_level_arbitrated() -> None:
    """SPEC §8.4 Example 4."""
    a = _c(
        "pools/pool-A/feedback_tabs",
        "pool",
        "hint",
        subscribed_at="user",
        source="pool/pool-A",
    )
    b = _c(
        "pools/pool-B/feedback_spaces",
        "pool",
        "hint",
        subscribed_at="user",
        source="pool/pool-B",
    )
    res = resolve_conflict([a, b])
    assert res.winner is None
    assert res.rule == 4


def test_rule_4_two_mandatories_at_same_level_also_arbitrate() -> None:
    """Rule 4 applies at any enforcement level, not just hint."""
    a = _c("team/platform/feedback_x", "team", "mandatory", source="team:a")
    b = _c("team/infra/feedback_x", "team", "mandatory", source="team:b")
    res = resolve_conflict([a, b])
    assert res.winner is None
    assert res.rule == 4


# ------------------------------------------------------------------
# Rule 5 — same-pool internal conflict → hard error
# ------------------------------------------------------------------


def test_rule_5_same_pool_internal_conflict_raises() -> None:
    a = _c(
        "pools/compliance/feedback_x_a",
        "pool",
        "default",
        subscribed_at="team",
        source="pool/compliance",
    )
    b = _c(
        "pools/compliance/feedback_x_b",
        "pool",
        "default",
        subscribed_at="team",
        source="pool/compliance",
    )
    with pytest.raises(PoolInternalConflict) as exc:
        resolve_conflict([a, b])
    assert "compliance" in str(exc.value)


# ------------------------------------------------------------------
# Mixed — interaction of multiple rules
# ------------------------------------------------------------------


def test_mandatory_beats_native_specificity() -> None:
    """Rule 1 is absolute — a project hint can't beat an org mandatory
    even though project is the most specific scope."""
    org = _c("org/acme/feedback_no_bypass", "org", "mandatory")
    proj = _c("local/feedback_bypass", "project", "hint")
    user = _c("user/feedback_bypass", "user", "default")
    res = resolve_conflict([proj, user, org])
    assert res.winner == org.id
    assert res.rule == 1


def test_resolution_preserves_input_ids_in_losers() -> None:
    """Non-winners must appear in .losers — caller depends on this to
    build 'engram review' warnings."""
    proj = _c("local/feedback_x", "project", "default")
    team = _c("team/platform/feedback_x", "team", "default")
    org = _c("org/acme/feedback_x", "org", "default")
    res: Resolution = resolve_conflict([proj, team, org])
    assert res.winner == proj.id
    assert set(res.losers) == {team.id, org.id}


def test_pool_at_project_with_mandatory_beats_native_project_hint() -> None:
    """Rule 1 is absolute — even the 'native beats pool' tiebreaker
    from rule 3 is irrelevant when enforcement differs."""
    pool = _c(
        "pools/compliance/feedback_x",
        "pool",
        "mandatory",
        subscribed_at="project",
        source="pool/compliance",
    )
    proj = _c("local/feedback_x", "project", "hint")
    res = resolve_conflict([pool, proj])
    assert res.winner == pool.id
    assert res.rule == 1
