---
name: Secret management
description: Where credentials live and how they rotate
type: project
scope: project
enforcement: default
created: 2026-01-01
updated: 2026-01-01
---

Credentials live in the vault and are injected as environment variables at process boot. Never commit a credential to the repository. Production secrets rotate every quarter.
