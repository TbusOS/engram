# tests/ — test suites

**Status**: skeleton (populated alongside CLI work in M2)

## Layout

```
tests/
├── conformance/                # spec-level: any engram impl must pass these
│   ├── healthy-store/          # a valid .memory/ that MUST pass validation
│   ├── edge-cases/             # weird-but-legal cases (utf-8 names, empty descriptions, ...)
│   └── broken/                 # each subdir is an intentional violation
│       ├── missing-memory-md/
│       ├── dangling-symlink/
│       ├── oversized-line/
│       └── ...
│
├── fixtures/                   # reusable sample stores for CLI tests
│   ├── empty-project/
│   ├── claude-code-migration-source/
│   └── ...
│
└── e2e/                        # end-to-end workflows (real CLI invocations)
    ├── init_and_review.sh
    ├── migrate_from_v1.sh
    ├── multi_adapter.sh
    ├── share_pool.sh
    └── export_prompt.sh
```

Unit tests live next to the code they test, under `cli/tests/unit/`.

## How to run

```bash
# Unit tests (fast)
cd cli && pytest tests/unit/

# CLI integration tests (slower, real filesystem)
cd cli && pytest tests/integration/

# Conformance tests (runs against any engram impl)
engram validate tests/conformance/healthy-store/       # should exit 0
engram validate tests/conformance/broken/dangling-symlink/  # should exit non-zero

# End-to-end shell workflows
bash tests/e2e/init_and_review.sh
```

## Adding a fixture

When you add a new CLI feature, drop a fixture store under `tests/fixtures/` and reference it by path in your test. This keeps tests reproducible and makes it easy to debug ("oh the fixture's MEMORY.md is malformed").

## Adding a conformance case

Conformance is the contract for "this is a valid engram store". If you find a case the current spec doesn't handle, add a fixture under `conformance/` and — depending on what you found — either:

1. Fix `SPEC.md` to cover the case, add the fixture to `healthy-store/` or `edge-cases/`
2. Declare the case a violation, add it under `broken/<name>/` with a `README.md` explaining which SPEC rule it violates

Every `broken/*/` directory must have a `README.md` naming the exact SPEC section it breaks.
