"""``engram team`` — git-backed team scope (SPEC §8.5).

Built on top of :mod:`engram.scope`. See that module for the shared
implementation; this file only picks the scope kind and exposes the
resulting click group.
"""

from engram.scope import build_scope_group

team_group = build_scope_group("team")

__all__ = ["team_group"]
