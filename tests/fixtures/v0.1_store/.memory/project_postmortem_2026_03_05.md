---
name: postmortem 2026-03-05 outage
description: 37-minute acme-api outage caused by leaked DB connections
type: project
created: 2026-03-06
tags: [incident, postmortem, acme-api]
---

Postmortem for the 2026-03-05 outage.

**Why:** a bulk-import script left DB connections open in an
uncancelled asyncio task group; the connection pool saturated and
acme-api started timing out on every request.

**How to apply:** any bulk-import script this assistant writes must
close connections in a `finally` block and must be reviewed by
platform-db before shipping.
