---
name: prefer stdlib over third-party
description: avoid adding dependencies for things stdlib already covers
type: feedback
created: 2025-11-08
tags: [python, dependencies]
---

Reach for the standard library first.

**Why:** every added dependency is a CVE, upgrade, and vendor-risk
surface; the maintainer prefers boring tools that ship with Python.

**How to apply:** before `pip install foo`, check whether `foo` can be
done in ≤30 lines with stdlib.
