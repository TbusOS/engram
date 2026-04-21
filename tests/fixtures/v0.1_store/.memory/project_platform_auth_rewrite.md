---
name: platform auth middleware rewrite
description: replace custom session store with oauth-based tokens
type: project
created: 2026-01-22
tags: [auth, security, platform]
---

Rewrite the platform-auth middleware.

**Why:** legal flagged the current session-token storage for failing
new data-residency requirements; the rewrite is compliance-driven, not
a tech-debt cleanup.

**How to apply:** favour compliance correctness over ergonomic niceties
when scoping; reviewer for any PR in this area is platform-security.
