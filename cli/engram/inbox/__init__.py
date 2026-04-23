"""Inter-Repo Messenger inbox — SPEC §10 (T-50).

Five modules (DESIGN §4.2 layout):

- :mod:`engram.inbox.identity` — repo-id resolution (§10.6).
- :mod:`engram.inbox.messenger` — ``send_message`` + dedup + rate
  limit (§10.2, §10.5).
- :mod:`engram.inbox.lifecycle` — acknowledge / resolve / reject
  transitions (§10.4).
- :mod:`engram.inbox.list_` — read enumeration with SPEC §10.3
  priority ordering.
- CLI: ``engram inbox {send,list,ack,resolve,reject}`` at
  :mod:`engram.commands.inbox`.

The inbox is per-user, not per-project: every message lives at
``~/.engram/inbox/<recipient-repo-id>/<state>/<file>.md``. That is why
``send_message`` does not need a project root on the recipient side —
it only needs the sender's project root (for repo-id resolution) and
the recipient's repo-id string.
"""

from engram.inbox.identity import resolve_repo_id
from engram.inbox.lifecycle import acknowledge, reject, resolve
from engram.inbox.list_ import list_messages
from engram.inbox.messenger import (
    DEDUP_DETECTED,
    MAX_PENDING_PER_SENDER,
    MAX_PER_SENDER_PER_DAY,
    RATE_LIMIT_HIT,
    SENT,
    send_message,
)

__all__ = [
    "DEDUP_DETECTED",
    "MAX_PENDING_PER_SENDER",
    "MAX_PER_SENDER_PER_DAY",
    "RATE_LIMIT_HIT",
    "SENT",
    "acknowledge",
    "list_messages",
    "reject",
    "resolve",
    "resolve_repo_id",
    "send_message",
]
