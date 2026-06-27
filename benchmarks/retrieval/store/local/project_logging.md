---
name: Logging conventions
description: Structured logging rules
type: project
scope: project
enforcement: default
created: 2026-01-01
updated: 2026-01-01
---

Services emit structured JSON log lines to stdout; the collector ships them to the central index. Never write secrets, API keys, or full request bodies into a log line.
