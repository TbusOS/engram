"""T-55 tests: marker-bounded adapter file rewriter.

The rewriter owns a block delimited by ``<!-- BEGIN engram -->`` /
``<!-- END engram -->`` (or language-appropriate equivalents). Anything
between the markers is engram-managed and replaced on each refresh.
Anything outside is user content and must be preserved verbatim.
"""

from __future__ import annotations

from engram.adapters.renderer import (
    BEGIN_MARKER,
    END_MARKER,
    apply_managed_block,
)


MANAGED = "managed content v1"


def test_creates_block_in_empty_file() -> None:
    out = apply_managed_block("", MANAGED)
    assert BEGIN_MARKER in out
    assert END_MARKER in out
    assert MANAGED in out


def test_prepends_block_when_file_has_user_content_without_markers() -> None:
    existing = "# My notes\n\nSome user content.\n"
    out = apply_managed_block(existing, MANAGED)
    assert out.startswith(BEGIN_MARKER)
    # User content preserved after the managed block.
    assert "# My notes" in out
    assert "Some user content." in out


def test_replaces_existing_managed_block() -> None:
    initial = apply_managed_block("# Title\n\nbody\n", "old content")
    assert "old content" in initial
    refreshed = apply_managed_block(initial, "new content")
    assert "new content" in refreshed
    assert "old content" not in refreshed
    # User text still there.
    assert "# Title" in refreshed
    assert "body" in refreshed


def test_preserves_user_content_before_and_after_markers() -> None:
    user_before = "# Top notes\n\npersonal reminder\n\n"
    user_after = "\n\n# Bottom notes\n\nanother personal reminder\n"
    existing = (
        user_before
        + BEGIN_MARKER
        + "\n\nOLD managed content\n\n"
        + END_MARKER
        + user_after
    )
    out = apply_managed_block(existing, "NEW managed content")
    assert "personal reminder" in out
    assert "another personal reminder" in out
    assert "NEW managed content" in out
    assert "OLD managed content" not in out


def test_idempotent_when_managed_block_unchanged() -> None:
    first = apply_managed_block("", MANAGED)
    second = apply_managed_block(first, MANAGED)
    assert first == second


def test_managed_block_is_clearly_demarcated() -> None:
    """The markers must be on their own lines so a reader can eyeball
    the engram section."""
    out = apply_managed_block("", MANAGED)
    lines = out.splitlines()
    assert BEGIN_MARKER in lines
    assert END_MARKER in lines


def test_multiple_markers_in_input_uses_outermost() -> None:
    """If the file has a malformed second marker pair, replace everything
    between the first BEGIN and the last END — the goal is "managed region
    is one contiguous block"."""
    existing = (
        "user top\n"
        + BEGIN_MARKER
        + "\nold1\n"
        + END_MARKER
        + "\nuser middle\n"
        + BEGIN_MARKER
        + "\nold2\n"
        + END_MARKER
        + "\nuser bottom\n"
    )
    out = apply_managed_block(existing, "new managed")
    # User-top and user-bottom preserved; middle chunk between the outer
    # markers is treated as engram-owned.
    assert "user top" in out
    assert "user bottom" in out
    assert out.count(BEGIN_MARKER) == 1
    assert out.count(END_MARKER) == 1
    assert "new managed" in out
    assert "old1" not in out
    assert "old2" not in out
