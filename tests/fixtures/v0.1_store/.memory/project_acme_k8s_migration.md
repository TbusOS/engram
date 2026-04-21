---
name: acme k8s migration
description: move all acme-platform services from nomad to k8s by Q2
type: project
created: 2026-01-14
tags: [acme, kubernetes, migration]
---

Migrate the acme-platform service fleet from Nomad to Kubernetes.

**Why:** Nomad version in prod has been unmaintained for 18 months;
k8s is the standard for all new acme services and migration unlocks
shared autoscaling tooling.

**How to apply:** new services go straight to k8s; existing services
migrate service-by-service behind a feature flag; deadline 2026-06-30.
