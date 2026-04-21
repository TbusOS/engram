"""Shared git-backed scope (team + org) logic.

``engram team`` and ``engram org`` are structurally identical: each manages a
set of git-backed directories under ``~/.engram/<kind>/<name>/`` that members
``join``, ``sync``, ``publish``, and check ``status`` on. This module hosts
the one implementation; :mod:`engram.team` and :mod:`engram.org` are thin
wrappers that pick the ``kind`` and export the resulting click group.

Factoring rationale: duplicating two nearly-identical 200-line command
modules would violate the "no compromise" principle the project follows.
The factory approach keeps each scope's public surface discoverable in its
own package while reusing the git plumbing.
"""

from engram.scope.factory import build_scope_group
from engram.scope.git_ops import list_scopes, scope_root

__all__ = ["build_scope_group", "list_scopes", "scope_root"]
