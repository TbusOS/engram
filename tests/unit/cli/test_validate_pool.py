"""T-37 tests: pools.toml schema validation in ``engram validate``.

Covers SPEC §12.10 POOL rule family (M3 subset):

- E-POOL-001: ``propagation_mode = "pinned"`` with null / missing
  ``pinned_revision``.
- E-POOL-002: subscription references a pool that is not present under
  ``~/.engram/pools/<name>/``.
- E-POOL-003: pool's ``rev/current`` symlink is dangling (points at a
  revision that does not exist). Only flagged when the subscription
  actually resolves through ``rev/current`` (auto-sync / notify).
- E-POOL-004: ``subscribed_at`` value is not one of
  ``{org, team, user, project}``. (New code — SPEC §9.2 specifies the
  enum but §12.10 had no dedicated code; documented in the T-37 commit.)
- E-POOL-005: ``propagation_mode`` value is not one of
  ``{auto-sync, notify, pinned}``. (New code, same rationale.)
- E-POOL-006: ``pinned_revision`` set while ``propagation_mode`` is not
  ``pinned`` (SPEC §9.2 requires null). (New code.)
- E-POOL-007: ``pinned_revision`` targets a ``rev/<id>/`` directory that
  does not exist in the pool. (New code.)
- W-POOL-002: pool directory missing ``.engram-pool.toml`` manifest.

Also covers the malformed-pools.toml case — validate must surface a
parse error as an Issue rather than crashing with a ClickException.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from engram.cli import cli
from engram.commands.init import init_project


def _seed_project(root: Path) -> None:
    init_project(root)
    # Give .memory/local/ at least one valid asset so the project
    # passes STR-* / FM-* checks and we observe only POOL issues.
    asset = root / ".memory" / "local" / "user_role.md"
    asset.write_text(
        "---\n"
        "name: role\n"
        "description: role asset for pool-validate tests\n"
        "type: user\n"
        "scope: project\n"
        "---\n\n"
        "body\n",
        encoding="utf-8",
    )
    index = root / ".memory" / "MEMORY.md"
    index.write_text(
        index.read_text(encoding="utf-8") + "\n- [role](local/user_role.md)\n",
        encoding="utf-8",
    )


def _make_pool(home: Path, name: str, *, with_manifest: bool = True) -> Path:
    pool = home / ".engram" / "pools" / name
    pool.mkdir(parents=True, exist_ok=True)
    if with_manifest:
        (pool / ".engram-pool.toml").write_text("# pool manifest\n", encoding="utf-8")
    return pool


def _make_pool_rev(home: Path, name: str, revs: list[str], current: str | None) -> Path:
    pool = _make_pool(home, name)
    for r in revs:
        (pool / "rev" / r).mkdir(parents=True, exist_ok=True)
    if current:
        link = pool / "rev" / "current"
        if link.exists() or link.is_symlink():
            link.unlink()
        link.symlink_to(current)
    return pool


def _write_pools_toml(root: Path, text: str) -> None:
    (root / ".memory" / "pools.toml").write_text(text, encoding="utf-8")


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    fake = tmp_path / "home"
    fake.mkdir()
    monkeypatch.setenv("HOME", str(fake))
    return fake


@pytest.fixture
def project(tmp_path: Path, home: Path) -> Path:
    root = tmp_path / "proj"
    _seed_project(root)
    return root


def _issue_codes(project: Path) -> list[str]:
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "--dir", str(project), "validate"])
    assert result.exit_code in (0, 1, 2), result.output
    return [i["code"] for i in json.loads(result.output)["issues"]]


# ------------------------------------------------------------------
# No pools.toml + clean fixture → no POOL issues.
# ------------------------------------------------------------------


def test_no_subscriptions_no_pool_issues(project: Path) -> None:
    codes = _issue_codes(project)
    pool_codes = [c for c in codes if "-POOL-" in c]
    assert pool_codes == []


# ------------------------------------------------------------------
# Valid subscription passes.
# ------------------------------------------------------------------


def test_valid_auto_sync_subscription_is_clean(
    project: Path, home: Path
) -> None:
    _make_pool_rev(home, "compliance", ["r1"], current="r1")
    _write_pools_toml(
        project,
        "[subscribe.compliance]\n"
        'subscribed_at = "team"\n'
        'propagation_mode = "auto-sync"\n',
    )
    codes = _issue_codes(project)
    assert not any("POOL" in c for c in codes), codes


def test_valid_pinned_subscription_is_clean(project: Path, home: Path) -> None:
    _make_pool_rev(home, "playbook", ["r1", "r2", "r3"], current="r3")
    _write_pools_toml(
        project,
        "[subscribe.playbook]\n"
        'subscribed_at = "project"\n'
        'propagation_mode = "pinned"\n'
        'pinned_revision = "r2"\n',
    )
    codes = _issue_codes(project)
    assert not any("POOL" in c for c in codes), codes


# ------------------------------------------------------------------
# E-POOL-001: pinned without pinned_revision
# ------------------------------------------------------------------


def test_pinned_without_revision_is_error(project: Path, home: Path) -> None:
    _make_pool_rev(home, "playbook", ["r1"], current="r1")
    _write_pools_toml(
        project,
        "[subscribe.playbook]\n"
        'subscribed_at = "project"\n'
        'propagation_mode = "pinned"\n',
    )
    assert "E-POOL-001" in _issue_codes(project)


# ------------------------------------------------------------------
# E-POOL-002: subscription references missing pool directory
# ------------------------------------------------------------------


def test_missing_pool_directory_is_error(project: Path) -> None:
    _write_pools_toml(
        project,
        "[subscribe.missing]\n"
        'subscribed_at = "project"\n'
        'propagation_mode = "auto-sync"\n',
    )
    assert "E-POOL-002" in _issue_codes(project)


# ------------------------------------------------------------------
# E-POOL-003: dangling rev/current
# ------------------------------------------------------------------


def test_dangling_rev_current_is_error(project: Path, home: Path) -> None:
    pool = _make_pool(home, "broken")
    (pool / "rev").mkdir()
    (pool / "rev" / "current").symlink_to("r-not-there")
    _write_pools_toml(
        project,
        "[subscribe.broken]\n"
        'subscribed_at = "project"\n'
        'propagation_mode = "auto-sync"\n',
    )
    assert "E-POOL-003" in _issue_codes(project)


def test_pinned_subscription_ignores_rev_current(
    project: Path, home: Path
) -> None:
    """E-POOL-003 targets subscribers resolving through rev/current; a
    pinned subscriber that resolves through rev/<id>/ is unaffected."""
    pool = _make_pool(home, "pin")
    (pool / "rev" / "r1").mkdir(parents=True)
    (pool / "rev" / "current").symlink_to("gone")  # dangling but ignored
    _write_pools_toml(
        project,
        "[subscribe.pin]\n"
        'subscribed_at = "project"\n'
        'propagation_mode = "pinned"\n'
        'pinned_revision = "r1"\n',
    )
    codes = _issue_codes(project)
    assert "E-POOL-003" not in codes


# ------------------------------------------------------------------
# E-POOL-004: invalid subscribed_at
# ------------------------------------------------------------------


def test_invalid_subscribed_at_is_error(project: Path, home: Path) -> None:
    _make_pool_rev(home, "compliance", ["r1"], current="r1")
    _write_pools_toml(
        project,
        "[subscribe.compliance]\n"
        'subscribed_at = "household"\n'
        'propagation_mode = "auto-sync"\n',
    )
    assert "E-POOL-004" in _issue_codes(project)


# ------------------------------------------------------------------
# E-POOL-005: invalid propagation_mode
# ------------------------------------------------------------------


def test_invalid_propagation_mode_is_error(project: Path, home: Path) -> None:
    _make_pool_rev(home, "compliance", ["r1"], current="r1")
    _write_pools_toml(
        project,
        "[subscribe.compliance]\n"
        'subscribed_at = "project"\n'
        'propagation_mode = "eager"\n',
    )
    assert "E-POOL-005" in _issue_codes(project)


# ------------------------------------------------------------------
# E-POOL-006: pinned_revision set without pinned mode
# ------------------------------------------------------------------


def test_pinned_revision_with_auto_sync_is_error(
    project: Path, home: Path
) -> None:
    _make_pool_rev(home, "compliance", ["r1"], current="r1")
    _write_pools_toml(
        project,
        "[subscribe.compliance]\n"
        'subscribed_at = "project"\n'
        'propagation_mode = "auto-sync"\n'
        'pinned_revision = "r1"\n',
    )
    assert "E-POOL-006" in _issue_codes(project)


# ------------------------------------------------------------------
# E-POOL-007: pinned_revision references non-existent rev
# ------------------------------------------------------------------


def test_pinned_revision_pointing_at_missing_dir_is_error(
    project: Path, home: Path
) -> None:
    _make_pool_rev(home, "compliance", ["r1", "r2"], current="r2")
    _write_pools_toml(
        project,
        "[subscribe.compliance]\n"
        'subscribed_at = "project"\n'
        'propagation_mode = "pinned"\n'
        'pinned_revision = "r99"\n',
    )
    assert "E-POOL-007" in _issue_codes(project)


# ------------------------------------------------------------------
# W-POOL-002: pool missing .engram-pool.toml
# ------------------------------------------------------------------


def test_missing_pool_manifest_is_warning(project: Path, home: Path) -> None:
    _make_pool(home, "bare", with_manifest=False)
    (home / ".engram" / "pools" / "bare" / "rev" / "r1").mkdir(parents=True)
    (home / ".engram" / "pools" / "bare" / "rev" / "current").symlink_to("r1")
    _write_pools_toml(
        project,
        "[subscribe.bare]\n"
        'subscribed_at = "project"\n'
        'propagation_mode = "auto-sync"\n',
    )
    assert "W-POOL-002" in _issue_codes(project)


# ------------------------------------------------------------------
# Malformed pools.toml — must surface as a single Issue, not crash.
# ------------------------------------------------------------------


def test_malformed_pools_toml_surfaces_as_issue(project: Path) -> None:
    _write_pools_toml(project, "this = is not [valid toml ===")
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "--dir", str(project), "validate"])
    # Should NOT abort with exit 1 due to an unhandled exception; must
    # report a POOL issue and exit with the standard validate code.
    assert result.exit_code in (1, 2), result.output
    codes = [i["code"] for i in json.loads(result.output)["issues"]]
    assert "E-POOL-000" in codes


# ------------------------------------------------------------------
# Multiple subscriptions each get their own issue.
# ------------------------------------------------------------------


def test_multiple_subscriptions_each_reported(project: Path, home: Path) -> None:
    _make_pool_rev(home, "good", ["r1"], current="r1")
    _write_pools_toml(
        project,
        "[subscribe.good]\n"
        'subscribed_at = "project"\n'
        'propagation_mode = "auto-sync"\n'
        "\n"
        "[subscribe.gone]\n"
        'subscribed_at = "team"\n'
        'propagation_mode = "auto-sync"\n'
        "\n"
        "[subscribe.bogus]\n"
        'subscribed_at = "martian"\n'
        'propagation_mode = "auto-sync"\n',
    )
    codes = _issue_codes(project)
    assert "E-POOL-002" in codes
    assert "E-POOL-004" in codes
