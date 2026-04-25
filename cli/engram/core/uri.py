"""Canonical asset URI for cross-project / cross-machine identity (T-180,
issue #4 / SPEC-AMEND v0.2.1).

Form::

    store://<store_root_id>/<scope_kind>/<scope_name>/<asset_path>

Why this exists: with v0.2's project-local ``graph.db`` and assets named
like ``local/feedback_confirm_before_push``, two projects on the same
machine collide on primary key. Cross-machine inboxes / journals cannot
correlate. The canonical URI gives every asset a globally unique
identity that survives moving the project to another path or machine
**iff** the git remote stays the same.

``store_root_id`` reuses the inbox SPEC §10.6 three-tier resolution:

1. ``[project] repo_id`` in ``.engram/config.toml`` — explicit
2. ``git remote get-url origin`` SHA-256 prefix — typical
3. project absolute path SHA-256 prefix — fallback (unique per machine)

The wire format is intentionally close to plain URL syntax so journals
and command output remain greppable; full URL parsing would import
``urllib.parse``, which is overkill — the format is well-defined enough
to tokenize by ``://`` then ``/``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from engram.inbox.identity import resolve_repo_id


__all__ = [
    "CanonicalURI",
    "build_canonical_uri",
    "parse_canonical_uri",
    "resolve_store_root_id",
    "VALID_SCOPE_KINDS",
]


VALID_SCOPE_KINDS: frozenset[str] = frozenset(
    {"project", "user", "team", "org", "pool"}
)
_SCHEME = "store://"


@dataclass(frozen=True)
class CanonicalURI:
    store_root_id: str
    scope_kind: str
    scope_name: str
    asset_path: str

    def __str__(self) -> str:
        return build_canonical_uri(
            store_root_id=self.store_root_id,
            scope_kind=self.scope_kind,
            scope_name=self.scope_name,
            asset_path=self.asset_path,
        )


def build_canonical_uri(
    *,
    store_root_id: str,
    scope_kind: str,
    scope_name: str,
    asset_path: str,
) -> str:
    if scope_kind not in VALID_SCOPE_KINDS:
        raise ValueError(
            f"invalid scope_kind {scope_kind!r}; must be one of "
            f"{sorted(VALID_SCOPE_KINDS)}"
        )
    if not store_root_id:
        raise ValueError("store_root_id must be non-empty")
    if not scope_name:
        raise ValueError("scope_name must be non-empty")
    if not asset_path:
        raise ValueError("asset_path must be non-empty")
    return f"{_SCHEME}{store_root_id}/{scope_kind}/{scope_name}/{asset_path}"


def parse_canonical_uri(uri: str) -> CanonicalURI:
    if not uri.startswith(_SCHEME):
        raise ValueError(f"unsupported scheme: {uri!r} (expected {_SCHEME!r})")
    body = uri[len(_SCHEME) :]
    parts = body.split("/", 3)
    if len(parts) < 4:
        raise ValueError(
            f"canonical URI requires 4 path segments, got {len(parts)}: {uri!r}"
        )
    store_root_id, scope_kind, scope_name, asset_path = parts
    if scope_kind not in VALID_SCOPE_KINDS:
        raise ValueError(
            f"invalid scope_kind {scope_kind!r} in URI {uri!r}; "
            f"must be one of {sorted(VALID_SCOPE_KINDS)}"
        )
    return CanonicalURI(
        store_root_id=store_root_id,
        scope_kind=scope_kind,
        scope_name=scope_name,
        asset_path=asset_path,
    )


def resolve_store_root_id(project_root: Path) -> str:
    """SPEC §10.6 three-tier resolution, reused from inbox identity.

    Returns a stable opaque string that:

    - is identical for two clones of the same git remote
    - differs across distinct git remotes
    - differs across machines for non-git projects (path-hash fallback)
    - can be overridden by ``[project] repo_id`` in ``.engram/config.toml``
    """
    return resolve_repo_id(project_root)
