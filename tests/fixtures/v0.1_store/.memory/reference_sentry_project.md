---
name: sentry project acme-platform
description: error tracking for every acme-platform service
type: reference
created: 2025-10-17
tags: [observability, errors]
---

All acme-platform service errors report to the sentry project
`acme-platform` at `sentry.internal.example/acme-platform`.

When diagnosing a new crash, check sentry first — the stack trace and
release tag usually pinpoint the offending commit faster than logs do.
