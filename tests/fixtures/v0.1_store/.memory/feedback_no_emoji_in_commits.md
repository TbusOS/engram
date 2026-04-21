---
name: no emoji in commit messages
description: conventional commit prefixes only, no gitmoji
type: feedback
created: 2025-12-11
tags: [git, style]
---

Commit messages use conventional prefixes (`feat:`, `fix:`, `docs:`)
and contain no emoji.

**Why:** the maintainer's tooling `grep`s commit subjects routinely;
emojis break that grep and add nothing the prefix doesn't already say.

**How to apply:** every commit message across every repo this assistant
helps with.
