"""Read-side enumeration + SPEC §10.3 priority ordering."""

from __future__ import annotations

from typing import Any

import yaml

from engram.core.paths import user_root
from engram.inbox.identity import slugify_repo_id

__all__ = ["list_messages"]


# Priority ordering: severity → intent → deadline → created.
_SEVERITY_RANK = {"critical": 0, "warning": 1, "info": 2}
_INTENT_RANK = {
    "bug-report": 0,
    "task": 0,
    "api-change": 1,
    "question": 2,
    "update-notify": 2,
}


def list_messages(
    *,
    recipient_id: str,
    status: str = "pending",
) -> list[dict[str, Any]]:
    """Return messages for ``recipient_id`` in SPEC §10.3 priority order."""
    d = user_root() / "inbox" / slugify_repo_id(recipient_id) / status
    if not d.is_dir():
        return []
    messages: list[dict[str, Any]] = []
    for f in d.glob("*.md"):
        try:
            text = f.read_text(encoding="utf-8")
            fm_text = text[4:].split("\n---\n", 1)[0]
            fm = yaml.safe_load(fm_text)
        except (yaml.YAMLError, ValueError):
            continue
        if not isinstance(fm, dict):
            continue
        fm = dict(fm)
        fm["_path"] = str(f)
        messages.append(fm)

    messages.sort(
        key=lambda m: (
            _SEVERITY_RANK.get(m.get("severity", "info"), 99),
            _INTENT_RANK.get(m.get("intent", ""), 99),
            m.get("deadline") or "9999-12-31",
            m.get("created") or "9999-12-31T00:00:00Z",
        )
    )
    return messages
