"""Knowledge Base asset class — multi-chapter reference articles (SPEC §6).

The third of engram's three asset classes (Memory / Workflow / KB). A KB
article is a directory ``<scope-root>/kb/<topic>/`` with a ``README.md``
entry point, numbered chapter files (``NN-slug.md``), an ``assets/``
directory for attachments, and a ``_compiled.md`` digest (a cached
derivation, never authoritative) tracked by ``_compile_state.toml``.

The chapters are the source of truth; ``engram kb compile`` regenerates
the digest. The default compile is rule-based and fully offline
(``model: local/none``); an LLM compile can be layered on later via the
same provider abstraction the observer uses.
"""

from __future__ import annotations

from engram.kb.compiler import (
    CompileResult,
    StalenessReport,
    chapter_hashes,
    check_staleness,
    compile_article,
)
from engram.kb.format import (
    CompileState,
    KbFormatError,
    KbFrontmatter,
    parse_compile_state,
    parse_readme,
    render_compile_state,
    render_readme,
)
from engram.kb.paths import KB_README_NAME, kb_dir, kb_root, validate_topic_name

__all__ = [
    "KB_README_NAME",
    "CompileResult",
    "CompileState",
    "KbFormatError",
    "KbFrontmatter",
    "StalenessReport",
    "chapter_hashes",
    "check_staleness",
    "compile_article",
    "kb_dir",
    "kb_root",
    "parse_compile_state",
    "parse_readme",
    "render_compile_state",
    "render_readme",
    "validate_topic_name",
]
