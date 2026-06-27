---
name: API rate limiting
description: Per-key request limits on public endpoints
type: project
scope: project
enforcement: default
created: 2026-01-01
updated: 2026-01-01
---

Public endpoints are limited to 100 requests per minute per API key using a token-bucket counter in Redis. Callers over the limit receive HTTP 429 with a Retry-After header.
