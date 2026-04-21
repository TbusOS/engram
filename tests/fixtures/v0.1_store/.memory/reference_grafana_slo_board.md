---
name: grafana SLO board
description: primary latency + error-rate dashboard for acme-platform
type: reference
created: 2025-10-02
tags: [observability, slo]
origin_tool: dashboard-inventory-scanner
---

The primary SLO dashboard is at
`grafana.internal.example/d/acme-platform-slo`.

If a change touches request-path code in any acme-platform service,
check this board before and after rollout — it's the dashboard the
oncall engineer watches during deploys.
