"""T-180 tests for ``engram.core.uri`` — canonical asset URI for
cross-project / cross-machine identity (issue #4).

URI shape::

    store://<store_root_id>/<scope_kind>/<scope_name>/<asset_path>

- ``store_root_id`` reuses ``inbox.identity.resolve_repo_id`` (SPEC §10.6
  three-step resolution: explicit config > git remote SHA > path hash)
- ``scope_kind`` ∈ {project, user, team, org, pool}
- ``scope_name`` is project name / user / team-name / org-name / pool-name
- ``asset_path`` is the relative path inside ``.memory/`` (or under the
  scope's home), e.g. ``local/feedback_x.md``

Roundtrip: ``parse_canonical_uri(build_canonical_uri(parts...))`` returns
the same parts. Two clones of the same git remote get the same
``store_root_id`` (so journals can correlate across machines). Two
projects with no git remote get distinct ``store_root_id`` values
because path hashes diverge.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from engram.core.uri import (
    CanonicalURI,
    build_canonical_uri,
    parse_canonical_uri,
    resolve_store_root_id,
)


@pytest.fixture
def tmp_project(tmp_path: Path) -> Iterator[Path]:
    proj = tmp_path / "p"
    proj.mkdir()
    (proj / ".memory").mkdir()
    (proj / ".engram").mkdir()
    yield proj


def _git_init(repo: Path, remote_url: str | None = None) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@e.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, check=True)
    if remote_url:
        subprocess.run(
            ["git", "remote", "add", "origin", remote_url], cwd=repo, check=True
        )


# ------------------------------------------------------------------
# build / parse roundtrip
# ------------------------------------------------------------------


class TestBuildAndParse:
    def test_simple_roundtrip(self) -> None:
        uri = build_canonical_uri(
            store_root_id="abcd1234",
            scope_kind="project",
            scope_name="acme-platform",
            asset_path="local/feedback_x.md",
        )
        assert uri.startswith("store://")
        parsed = parse_canonical_uri(uri)
        assert parsed.store_root_id == "abcd1234"
        assert parsed.scope_kind == "project"
        assert parsed.scope_name == "acme-platform"
        assert parsed.asset_path == "local/feedback_x.md"

    def test_pool_scope(self) -> None:
        uri = build_canonical_uri(
            store_root_id="user-home-hash",
            scope_kind="pool",
            scope_name="kernel-work",
            asset_path="feedback_no_force_push.md",
        )
        parsed = parse_canonical_uri(uri)
        assert parsed.scope_kind == "pool"
        assert parsed.scope_name == "kernel-work"

    def test_invalid_scope_kind_rejected(self) -> None:
        with pytest.raises(ValueError, match="scope_kind"):
            build_canonical_uri(
                store_root_id="x",
                scope_kind="not-a-real-kind",
                scope_name="y",
                asset_path="z.md",
            )

    def test_parse_invalid_scheme_rejected(self) -> None:
        with pytest.raises(ValueError, match="scheme"):
            parse_canonical_uri("https://example.com/foo")

    def test_parse_missing_segments_rejected(self) -> None:
        with pytest.raises(ValueError, match="segments"):
            parse_canonical_uri("store://only-one-segment")


# ------------------------------------------------------------------
# resolve_store_root_id — SPEC §10.6 three-tier resolution
# ------------------------------------------------------------------


class TestResolveStoreRootId:
    def test_path_hash_when_no_git(self, tmp_project: Path) -> None:
        out = resolve_store_root_id(tmp_project)
        assert out
        # Same path → same id (deterministic)
        assert out == resolve_store_root_id(tmp_project)

    def test_git_remote_drives_id(self, tmp_path: Path) -> None:
        proj_a = tmp_path / "a"
        proj_b = tmp_path / "b"
        for p in (proj_a, proj_b):
            p.mkdir()
            (p / ".memory").mkdir()
            (p / ".engram").mkdir()
            _git_init(p, remote_url="git@github.com:acme/example.git")
        assert resolve_store_root_id(proj_a) == resolve_store_root_id(proj_b)

    def test_different_remotes_produce_different_ids(
        self, tmp_path: Path
    ) -> None:
        proj_a = tmp_path / "a"
        proj_b = tmp_path / "b"
        for p, remote in (
            (proj_a, "git@github.com:acme/foo.git"),
            (proj_b, "git@github.com:acme/bar.git"),
        ):
            p.mkdir()
            (p / ".memory").mkdir()
            (p / ".engram").mkdir()
            _git_init(p, remote_url=remote)
        assert resolve_store_root_id(proj_a) != resolve_store_root_id(proj_b)

    def test_explicit_config_wins(self, tmp_project: Path) -> None:
        cfg = tmp_project / ".engram" / "config.toml"
        cfg.write_text('[project]\nrepo_id = "explicit-id-here"\n', encoding="utf-8")
        assert resolve_store_root_id(tmp_project) == "explicit-id-here"


# ------------------------------------------------------------------
# CanonicalURI dataclass
# ------------------------------------------------------------------


class TestCanonicalURI:
    def test_string_form_matches_build(self) -> None:
        u = CanonicalURI(
            store_root_id="abc",
            scope_kind="project",
            scope_name="proj",
            asset_path="local/x.md",
        )
        assert str(u) == build_canonical_uri(
            store_root_id="abc",
            scope_kind="project",
            scope_name="proj",
            asset_path="local/x.md",
        )

    def test_equality(self) -> None:
        u1 = CanonicalURI("a", "project", "n", "p.md")
        u2 = CanonicalURI("a", "project", "n", "p.md")
        assert u1 == u2
