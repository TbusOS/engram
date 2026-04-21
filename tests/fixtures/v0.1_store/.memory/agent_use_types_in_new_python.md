---
name: use type annotations in new python code
description: typed code catches regressions in review that untyped code hides
type: agent
source: autolearn/python-review-signal/r2
created: 2026-03-01
tags: [python, typing, autolearn]
---

New Python code gets full type annotations.

**Why:** round r2 review data showed three bugs caught by mypy that
reviewers had missed in the same PRs; one of them was a silent None
propagation that would have reached prod.

**How to apply:** every new `.py` file in any acme-platform repo.
Retrofitting old files is out of scope — only new additions.
