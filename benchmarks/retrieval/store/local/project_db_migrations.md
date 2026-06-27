---
name: Database schema changes
description: Migration discipline for the platform database
type: project
scope: project
enforcement: default
created: 2026-01-01
updated: 2026-01-01
---

All database schema changes ship as ordered Alembic migrations. Never edit a migration that has already shipped — add a new forward migration instead. Every migration must have a tested downgrade path.
