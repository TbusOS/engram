---
name: quarantine flaky tests promptly
description: flaky tests erode trust in the full suite within weeks
type: agent
source: autolearn/test-discipline/r3
created: 2026-02-20
tags: [testing, discipline, autolearn]
---

When a test flakes twice in a week, quarantine it (`@pytest.mark.flaky`
or equivalent) and open a Linear ticket to root-cause it.

**Why:** in round r3 the assistant observed that three retained-flaky
suites caused engineers to start routinely re-running CI without
reading failures, which then masked a real regression for 4 days.

**How to apply:** rule is active in every acme-platform repo with more
than ~50 tests.
