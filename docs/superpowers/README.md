# docs/superpowers/

Design specs and implementation plans for non-trivial initiatives that
span multiple milestones or need explicit upfront design. Separate from
`TASKS.md` (rolling task board) and `DESIGN.md` (architecture reference).

Pattern borrowed from `~/linux-kernel/ai-doc/docs/superpowers/`.

## Layout

- `specs/` — Design documents. *What* we're building and *why*.
- `plans/` — Step-by-step execution plans written for a Claude subagent
  or a developer with zero prior context.

## Current entries

| Topic | Spec | Plan | Status |
|---|---|---|---|
| Productization + quality plan | [specs/2026-04-22-productization-plan.md](specs/2026-04-22-productization-plan.md) | — | draft 2026-04-22 |
| Self-dogfood dashboard | [specs/2026-04-22-self-dogfood-dashboard.md](specs/2026-04-22-self-dogfood-dashboard.md) | — | **frozen design, deferred to M7** |

## Filename convention

`YYYY-MM-DD-<topic>-<spec|plan|notes>.md`

Specs live until the initiative ships; then move the entry to a
"Shipped" section at the bottom of this index rather than deleting.
The decision trail is useful reading for whoever picks up the next
initiative.

## Shipped

(none yet)
