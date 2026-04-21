[English](CONTRIBUTING.md) · [中文](CONTRIBUTING.zh.md)

# Contributing to engram

Thank you for considering contributing. This document covers: how to pick something to work on, how to set up your environment, how to submit changes, and what quality bars we maintain.

If in doubt about anything here, open a GitHub Discussion. Nothing below is set in stone — the community can change the rules via PR.

---

## 1. How to get started

Two paths:

### Path A: I have a specific idea

1. Open a GitHub Discussion in the **Ideas** category.
2. Wait for community or maintainer response — usually within 3 days.
3. If the idea is accepted in principle, file an Issue with a concrete, bounded scope.
4. Fork the repo, create a branch, write code, open a PR.

### Path B: I want to help but don't know where

1. Read [`TASKS.md`](TASKS.md) — 105+ tasks across 9 milestones.
2. Find a task with an empty Owner column and `status=todo`.
3. Open an Issue titled `Claim T-XX` and self-assign it.
4. Update the Owner and status fields in `TASKS.md` as part of your first commit.
5. Fork, branch, PR.

**Good starting tasks for new contributors:**

- Writing an additional `migrate` source (T-140 subtasks — each is a self-contained Python module)
- Improving a glossary entry or adding a translation in [`docs/glossary.md`](docs/glossary.md)
- Contributing a conformance fixture to `tests/conformance/`
- Writing a Playbook sample in `playbooks/`
- Adding a test for an existing CLI command

Pick anything in M1–M3 first. M4+ tasks are more likely to require understanding of multiple system layers.

---

## 2. Development setup

**Requirements:**

- Python 3.10+ (tested on 3.10, 3.11, 3.12, 3.13)
- Node.js 18+ (only if working on `web/frontend/` or `sdk-ts/`)
- Git 2.20+

**Clone and install:**

```bash
git clone https://github.com/TbusOS/engram.git
cd engram
pip install -e "cli/[dev]"        # editable install with dev dependencies
pre-commit install                # runs linters before each commit
```

**Running tests:**

```bash
cd cli
pytest                            # unit + integration
pytest --cov=engram               # with coverage report
pytest -k test_memory             # specific test by name
pytest tests/e2e/                 # E2E tests only
```

**Running the Web UI locally (only if working on it):**

```bash
# Backend
cd web/backend
pip install -e ".[dev]"
uvicorn engram_web.app:create_app --reload --factory

# Frontend — in another terminal
cd web/frontend
npm install
npm run dev
```

**Linters:**

```bash
ruff check .                      # Python lint
ruff format --check .             # Python format check
mypy cli/engram                   # Python type check
npm run lint                      # TypeScript/Svelte lint
npm run format:check              # Prettier format check
```

**All checks should pass before opening a PR.** CI runs the same commands.

---

## 3. Branching and commit conventions

**Branch names:**

| Pattern | Use for |
|---------|---------|
| `feat/<name>` | new features |
| `fix/<name>` | bug fixes |
| `docs/<name>` | documentation-only changes |
| `refactor/<name>` | non-behavioral refactoring |
| `test/<name>` | test-only changes |

`main` is the stable branch. Every commit on `main` must pass CI.

**Commit format — Conventional Commits:**

```
type(scope): subject
```

- Subject: imperative mood, ≤72 characters
- Body (optional): wrap at ~72 characters; explain *why*, not *what*
- No AI co-authorship lines (`Co-Authored-By: Claude ...`, etc.)

**Types:**

| Type | When to use |
|------|-------------|
| `feat` | new feature (SPEC changes are always `feat`) |
| `fix` | bug fix |
| `docs` | documentation only (README, SPEC clarifications) |
| `refactor` | code change that is neither a feature nor a bug fix |
| `test` | test-only changes |
| `chore` | build scripts, CI, scaffolding |
| `perf` | performance improvement |
| `ci` | CI configuration changes |
| `spec` | updates to SPEC.md content |
| `design` | updates to DESIGN.md content |
| `methodology` | updates to METHODOLOGY.md content |

**Examples:**

```
feat(cli): add engram migrate for Claude Code sources
fix(spec): clarify MEMORY.md required fields
docs(glossary): add knowledge-base terms for v0.2
test(e2e): cover multi-adapter init flow
spec(§13): add migration default for agent subtype
```

**One commit, one logical change.** If the commit message needs "and also", split the commit.

---

## 4. Pull requests

### Before opening

- Rebase on latest `main`
- Run `pytest` and `ruff check .` locally — both must pass
- Update `TASKS.md` if you claimed or completed a task (Owner + status fields)
- Add or update tests for any behavior change
- Coverage must not drop more than 2% from the stored baseline (`tests/.coverage-baseline.json`)
- If your PR changes `SPEC.md` or `DESIGN.md` structurally, read §5 first

### PR body template

Copy this into your PR description:

```markdown
## Summary
<1–3 sentences describing what this PR does>

## Task(s)
Closes T-XX. Relates to T-YY.

## Changes
- <significant change 1>
- <significant change 2>

## Testing
- <what you tested locally>
- <CI results confirm green>

## Checklist
- [ ] Tests added or updated
- [ ] Docs updated (SPEC / DESIGN / METHODOLOGY / TASKS as applicable)
- [ ] Coverage ≥ baseline
- [ ] No jargon (checked against the engram language guide in docs/glossary.md)
- [ ] Glossary terms used verbatim for any new user-facing content
```

### Review SLA

- Initial response: within 3 days
- Substantive review: within 7 days (for non-trivial PRs)
- Merge: after 1 maintainer approval + CI green; SPEC changes require 2 approvals

### What reviewers will push back on

- Missing tests for new behavior
- Jargon or vague language in prose (see §7)
- SPEC or DESIGN changes without a prior Discussion
- New CLI commands without at least one E2E test
- Coverage regressions

---

## 5. SPEC / DESIGN changes — lightweight RFC process

Changes to `SPEC.md` or `DESIGN.md` that are structural — not typo fixes or example additions — go through a lightweight RFC before implementation.

**What counts as structural:**

Required RFC:
- New frontmatter field (required or optional)
- New Memory subtype or asset class
- Changes to conflict resolution rules (DESIGN §8.4)
- Changes to Consistency Engine taxonomy (SPEC §11)
- New validation error codes
- Changes to MCP tool signatures

Regular PR only (no RFC required):
- Typo fixes and prose clarifications
- Adding examples or improving existing ones
- Correcting or extending glossary terms
- Non-normative commentary

### RFC steps

**Step 1 — Open a GitHub Discussion** in the **Design Review** category.

- Title: `RFC: <description>`
- Body: problem statement / proposed change / alternatives considered / whether this is a breaking change
- Tag maintainers with `@`

**Step 2 — Community feedback** (minimum 3 days open, typically 1 week).

- Maintainers respond with questions or concerns
- Anyone can comment
- Reach rough consensus before writing code

**Step 3 — Implementation PR**

- Link to the Discussion in the PR body
- PR includes the SPEC or DESIGN update + tests + any component code that implements the new rule
- SPEC changes require 2 maintainer approvals; DESIGN changes require 1

**Step 4 — Announcement**

- Update `docs/HISTORY.md` if the change affects existing users
- If breaking (per SPEC §13.1): bump the MAJOR spec version and provide a migration path per SPEC §13.3–13.4

---

## 6. Testing requirements

Per DESIGN §10 testing strategy.

**Coverage targets:**

| Component | Target |
|-----------|--------|
| Python `cli/engram/` | ≥80% line coverage |
| TypeScript `sdk-ts/` | ≥80% line coverage |
| Svelte `web/frontend/` | ≥70% component coverage |

Coverage is enforced in CI. PRs that drop coverage more than 2% below the stored baseline are blocked.

**For every new CLI command:**

- At least one unit test for the command logic in `cli/tests/`
- At least one E2E test in `tests/e2e/`
- Tests verify both the success path and at least one failure path

**For every new SPEC rule:**

- At least one conformance fixture in `tests/conformance/`
- Fixture set must include: a valid example, one or more invalid examples, and the expected `engram validate --json` output

**For every Intelligence Layer component change** (Relevance Gate, Consistency Engine, Autolearn Engine, Evolve Engine, Wisdom Metrics):

- Benchmark test if the change may affect scoring or ranking output
- Regression test against the committed baseline in `benchmarks/results_*.jsonl`

**Test isolation rules:**

- Unit tests: pure functions, no filesystem side effects — use fixtures or `tmp_path`
- E2E tests: each test gets its own `pytest.tmp_path`; never modify the real `~/.engram/`
- Integration tests: may use SQLite in-memory or temporary directories; no shared state across test functions

---

## 7. Code review guidelines

**For reviewers:**

- Focus on correctness, clarity, and compatibility with the twelve invariants (DESIGN §8)
- Challenge prose containing jargon — point to the language guide in [`docs/glossary.md`](docs/glossary.md) if needed
- Ask "does this need a new primitive, or does an existing one cover it?" before accepting new complexity
- Verify that tests check actual behavior, not just lines executed
- Accept "good enough" on formatting; reserve substantive pushback for logic and spec compliance

**For contributors receiving review:**

- Respond within 7 days and re-request review after you have addressed comments
- Push back on review comments you disagree with — cite SPEC, DESIGN, or README as needed
- Resolve threads explicitly; do not leave them open silently

**Merge rules:**

- 1 maintainer approval + CI green → eligible to merge
- SPEC changes: 2 maintainer approvals required
- Contentious PRs: bring the discussion to GitHub Discussions before merging

---

## 8. Release flow

**Version cadence:**

| Type | When |
|------|------|
| Patch (v0.2.1, v0.2.2, ...) | Bug fixes, as needed |
| Minor (v0.3, v0.4, ...) | When a milestone M5+ completes |
| Major (v1.0, v2.0, ...) | Breaking SPEC changes (per SPEC §13.1) |

**Release checklist:**

- [ ] All milestone tasks marked `done` in `TASKS.md`
- [ ] `CHANGELOG.md` updated with user-facing changes
- [ ] `docs/HISTORY.md` notes any corrections or retractions from the cycle
- [ ] Benchmarks run and results committed to `benchmarks/results_*`
- [ ] Manual checklist at `tests/manual-checklist.md` completed
- [ ] Release tag created: `git tag -s v0.X.Y -m "engram v0.X.Y"`
- [ ] Tag pushed → triggers `.github/workflows/release.yaml` → PyPI publish
- [ ] Release notes posted to GitHub Releases and announced in Discussions

---

## 9. Community

**Discussions** — https://github.com/TbusOS/engram/discussions

Use for:
- Design review questions (before filing an Issue or PR)
- Ideas and feature proposals
- Q&A
- Sharing how you use engram

**Issues** — https://github.com/TbusOS/engram/issues

Use Issues for:
- Concrete bug reports
- Specific feature requests (after an Ideas Discussion in Discussions)
- Task claims: open an Issue titled `Claim T-XX`

**PRs** — https://github.com/TbusOS/engram/pulls

Use for:
- Code, documentation, test contributions
- Follow the PR checklist in §4

If you are not sure whether something belongs in Discussions or Issues: a vague idea goes to Discussions; a concrete report or bounded request goes to Issues.

**Code of conduct:**

Be kind, direct, and constructive. No personal attacks, no trolling, no gatekeeping. If someone's behavior makes you uncomfortable, contact the maintainers privately.

---

## 10. License

engram is MIT licensed. By contributing, you agree your contributions are also MIT-licensed.

If you are contributing on behalf of an employer and need CLA language, open a Discussion — we will work it out.

---

Thank you for reading. engram is a long-term project to give LLM memory back to the people generating it. Every contribution — code, tests, documentation, design review comments, translations, benchmark fixtures — compounds over time.

Questions about this guide: GitHub Discussions.
