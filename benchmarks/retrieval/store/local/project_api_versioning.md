---
name: API versioning
description: How HTTP API versions are managed
type: project
scope: project
enforcement: default
created: 2026-01-01
updated: 2026-01-01
---

The HTTP API is versioned in the path, /v1 and /v2. A version stays supported for twelve months after its successor ships, then returns HTTP 410 Gone.
