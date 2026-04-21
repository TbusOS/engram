---
name: squash before merge
description: local squash reduces CI re-run rate on platform service repos
type: agent
source: autolearn/git-merge-standard/r5
created: 2026-02-12
tags: [git, ci, autolearn]
---

Squash feature branches locally before merging.

**Why:** observed 5 consecutive clean merges after adopting squash in
round r5 across acme-platform repos; pre-squash baseline was a ~20%
"merge-then-fix-CI" rate caused by interleaved lint changes.

**How to apply:** applies to any acme-platform service repo; does not
apply to long-lived infra repos where per-commit history matters.
