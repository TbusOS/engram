# v0.1_store fixture — 20 assets

A realistic pre-migration store used by `tests/e2e/test_m3_migration_e2e.py`.

The layout is v0.1-shaped:

- `.memory/*.md` flat files (no `local/` subdir)
- no `.engram/version`
- no `scope` field on any asset, no `enforcement` on `feedback`, no
  `confidence` on `agent` (those are what migration must inject)
- a few assets carry custom frontmatter fields to exercise SPEC §4.1
  forward-compat preservation
- 3 `user`, 5 `feedback`, 5 `project`, 4 `reference`, 3 `agent` = **20 total**

All content is synthetic/generic (acme-*, platform-*, example.internal).
Any resemblance to real products is coincidental.
