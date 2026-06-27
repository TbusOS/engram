---
name: On-call runbook
description: First steps when the pager fires
type: reference
scope: project
enforcement: default
created: 2026-01-01
updated: 2026-01-01
---

When the pager fires on an error-rate spike, check three things in order: the recent deploy timeline, the database connection pool saturation, then the upstream payment provider status page. Escalate to the secondary on-call after fifteen minutes without a lead.
