---
name: prefer small PRs
description: keep diffs under ~400 lines and single-topic
type: feedback
created: 2025-10-20
tags: [review, git]
---

Split work into small, single-concern PRs.

**Why:** reviewers routinely miss issues in diffs above ~500 lines;
single-topic PRs revert cleanly if a regression ships.

**How to apply:** when a feature spans multiple concerns, sequence the
PRs and land them independently rather than bundling.
