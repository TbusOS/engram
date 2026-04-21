---
name: CI cutover Q2 2026
description: acme-platform drops jenkins for github-actions by 2026-06-30
type: project
created: 2026-02-03
tags: [ci, tooling, platform]
---

Cut over the acme-platform CI from Jenkins to GitHub Actions.

**Why:** the Jenkins controller has hit scaling limits (queue ≥ 30 min
at peak) and the ops team has no capacity to run a larger controller;
GitHub Actions is already in use for open-source projects.

**How to apply:** migration follows service-by-service; pipelines
ported 1:1 before any refactor.
