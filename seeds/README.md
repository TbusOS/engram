# seeds/ — reusable starter memories

**Status**: skeleton (empty placeholders for M3)

Seeds are pre-written memory files that `engram init` copies into a fresh `.memory/` directory. They give new projects a baseline so the user doesn't start from zero.

## The three seed tiers

```
seeds/
├── base/           # neutral, universal — everyone gets these by default
├── opinionated/    # the author's personal preferences — opt-in only
└── profiles/       # project-type-specific bundles — opt-in, selectable
    └── embedded-linux/
    └── ...
```

### `base/` — safe defaults

Truly neutral content that most users would want. Current plan:

- `user_profile.md.tmpl` — a templated "write your own profile here" skeleton the LLM fills in during early conversation

**What does NOT belong in `base/`**: anything that's an opinion. "Always ask before pushing" is an opinion, however reasonable.

### `opinionated/` — author's preferences

The project author's personal working rules. Shipped as a reference but **never enabled by default**. Users must opt in with `engram init --seeds=base,opinionated`.

Planned entries (examples, not exhaustive):

- `feedback_push_explicit_consent.md` — require user approval before any `git push`
- `feedback_no_destructive_without_confirm.md` — never run `reset --hard` / `push --force` / `rm -rf` without approval
- `feedback_check_before_delete.md` — inspect unknown files before deleting
- `feedback_no_side_effect_tests.md` — tests must be idempotent and reversible

If you disagree with any of these, don't enable `opinionated`. That's the whole point of keeping it separate.

### `profiles/` — project-type bundles

Bundles for specific project types. User opts in:

```bash
engram init --profile=embedded-linux
engram init --profile=web-frontend,ai-research
```

A profile is a directory of seed files plus a `profile.yaml` describing it:

```yaml
name: embedded-linux
description: Common context for embedded Linux / BSP engineers
author: <github-handle>
files:
  - reference_kernel_docs.md
  - feedback_no_kernel_panics_in_examples.md
```

Profiles are community-contributed. Good candidates:

- `embedded-linux` / `android-bsp`
- `web-frontend` (React / Vue / Svelte conventions)
- `ai-research` (paper-reading workflow, experiment tracking)
- `devops` (deployment safety, incident response)
- `data-science` (notebook conventions, reproducibility)

See [`../CONTRIBUTING.md`](../CONTRIBUTING.md) for how to contribute a profile.

## Template variables

Seed files are `.md.tmpl` — identical to a memory file, with `{{variables}}` replaced at init time:

| Variable | Example |
|----------|---------|
| `{{project_name}}` | `my-new-project` |
| `{{date}}` | `2026-04-17` |
| `{{user_name}}` | `sky` (from git config or prompt) |
| `{{profile}}` | `embedded-linux` (only inside a profile) |
