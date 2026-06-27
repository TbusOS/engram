---
name: Production deploy strategy
description: How releases reach production
type: project
scope: project
enforcement: default
created: 2026-01-01
updated: 2026-01-01
---

Production uses a blue-green deploy: the new build goes to the idle green fleet, the smoke suite runs against it, and only then does the load balancer cut traffic over. The old blue fleet stays warm for one hour as an instant rollback target.
