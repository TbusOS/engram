"""engram adapter system (T-53 / T-54 / T-55).

Generates and refreshes LLM-facing marker-bounded files so tools that
don't speak MCP still see a short, consistent briefing about the store.
The managed region is demarcated by ``<!-- BEGIN engram -->`` /
``<!-- END engram -->``; everything outside is user content and is
preserved verbatim on refresh. This means a user can add personal
notes to ``CLAUDE.md`` without worrying about being overwritten.

Five canonical adapters ship today:

- ``claude-code`` → ``<project>/CLAUDE.md``
- ``codex`` → ``<project>/AGENTS.md`` (shared with Opencode)
- ``gemini-cli`` → ``<project>/GEMINI.md``
- ``cursor`` → ``<project>/.cursor/rules/engram.mdc``
- ``raw-api`` → ``<project>/ENGRAM_PROMPT.md``

Hooks (``adapters/claude-code/hooks/*.sh``) ship as reference files in
the repo root, not under ``cli/``; they're OS-level scripts, not
Python.
"""

from engram.adapters.registry import ADAPTERS, AdapterSpec, find_adapter
from engram.adapters.renderer import (
    BEGIN_MARKER,
    END_MARKER,
    apply_managed_block,
)

__all__ = [
    "ADAPTERS",
    "BEGIN_MARKER",
    "END_MARKER",
    "AdapterSpec",
    "apply_managed_block",
    "find_adapter",
]
