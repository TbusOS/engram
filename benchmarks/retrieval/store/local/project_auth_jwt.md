---
name: Acme API authentication
description: How the Acme API authenticates requests
type: project
scope: project
enforcement: default
created: 2026-01-01
updated: 2026-01-01
---

The Acme API authenticates every request with a JWT bearer token in the Authorization header. Access tokens live 15 minutes; refresh tokens live 7 days. Tokens are signed with RS256 and verified against the rotating public key set.
