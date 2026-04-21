---
name: confirm before git push
description: never push without explicit user go-ahead
type: feedback
created: 2025-10-12
tags: [git, safety]
---

Ask before pushing to any remote.

**Why:** an earlier unintended force-push lost a colleague's uncommitted
work on a shared branch.

**How to apply:** every `git push`, regardless of branch or remote.
