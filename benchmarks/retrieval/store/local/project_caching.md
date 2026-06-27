---
name: Read caching
description: How read-heavy queries are cached
type: project
scope: project
enforcement: default
created: 2026-01-01
updated: 2026-01-01
---

Read-heavy queries are cached in Redis with a five-minute TTL. A write publishes an invalidation message on a pub/sub channel so every node drops the stale entry immediately.
