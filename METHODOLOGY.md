[English](METHODOLOGY.md) · [中文](METHODOLOGY.zh.md)

# engram Memory Methodology (v0.2)

**Version**: 0.2 — companion to SPEC v0.2 + DESIGN v0.2
**Audience**: LLMs writing memory; secondarily humans understanding LLM memory discipline
**Last updated**: 2026-04-19

---

## §1. Core Principle

**Memory is a long-term asset, not a scratchpad.**

A good memory is useful six months from now, in a different LLM, possibly read by a new team member who never saw the conversation that created it. Write for that reader.

Three implications follow from this principle:

**1. Write it once, right.** Or write it as a draft and evolve it through supersede chains — never as "I'll fix this later." The `draft` lifecycle state exists precisely for this: mark new memories `draft` if you are uncertain, but commit to eventually resolving them rather than leaving the store in a permanently provisional state.

**2. Generic enough to apply.** If a memory reads as "in this one conversation we agreed X," it is probably too narrow. The test: could this memory meaningfully change behavior in a session that starts with zero context about the originating conversation? If no, it does not belong in the store.

**3. Specific enough to act on.** "Be careful with file operations" is not a rule. "Prompt before `rm -rf` or `git push --force`" is. Vague memories pass the write-time check but fail at load time — the Relevance Gate scores them low, and the LLM that does load them has nothing actionable to do with them.

These three implications compound. A memory that is too narrow to generalize is useless six months from now. A memory that is too vague to act on wastes context budget. A memory written carefully pays forward to every future session, every future LLM, every future teammate who inherits the store.

---

## §2. When to Write a Memory

Write when you learn something that satisfies all three of these conditions:

1. **Will matter in future conversations** — not just this one. Ask: "If the next session starts cold, would knowing this change anything?"
2. **Is not recoverable** from code, git log, or public documentation. If the fact lives in a commit message or a README, a `reference` memory pointing there is enough — do not duplicate the content.
3. **Would cause a repeat mistake if forgotten** — the "surprise" signal. Anything that surprised you is a candidate. Anything that caused a correction is a strong candidate.

### Write immediately — do not batch

When the user corrects you, confirms a non-obvious choice, or shares a durable preference, write the memory in that turn. Batching feels efficient but loses the "why" — by the end of a long session, the context that made the preference intelligible has compressed or dropped entirely.

The cost of writing an unnecessary memory is low (one review cycle surfaces it for cleanup). The cost of losing a signal is high (the behavior regresses, the user corrects again, the conversation repeats).

### Corrections are loud. Confirmations are quiet. Both deserve memories.

- Correction: "No, don't do that" — obvious signal, easy to catch.
- Confirmation: "Yes exactly" / "That was the right call" — quiet signal, easy to miss.
- Pattern signal: if you would risk re-proposing the rejected option two weeks from now, save both the rejection and the reason.

Saving only corrections produces a store that avoids past mistakes but drifts away from patterns the user has already validated. Save confirmations too.

### Save on explicit user request

When the user says "remember this" or "save this," write it in that turn. No clarifying questions unless the scope is genuinely ambiguous (e.g., "is this a project-level rule or a personal one?"). The user's explicit instruction is sufficient authorization.

---

## §3. Picking the Right Subtype

Six subtypes exist. Subtype captures **epistemic status** — who authored the asset and how we know it is true. This is orthogonal to scope: the same claim written by a human becomes `feedback`; written by the LLM from observation, it becomes `agent`.

### `user` — Facts about the human

**When to write:** You learn something about the person — their role, skills, experience level, working context, communication preferences — that would change how you talk to them.

**Required frontmatter:** `name`, `description`, `type: user`, `scope`

**Body:** Free prose, third person from the LLM's perspective ("The user maintains…"). 2–8 paragraphs. No required subsections. `enforcement` defaults to `hint` — user context is advisory.

**Example trigger:** "I've been writing Go for 10 years, I just started picking up Rust." → `user` memory: "user has 10+ years of Go experience; Rust is new to them — calibrate explanations accordingly."

---

### `feedback` — Rules the LLM must follow

**When to write:** The user gives a direct rule, corrects your behavior, or confirms that a non-obvious approach was right.

**Required frontmatter:** `name`, `description`, `type: feedback`, `scope`, `enforcement` (mandatory on this subtype — must be stated explicitly; no default)

**Body structure:**

```
<one-line rule statement>

**Why:** <reason — usually an incident or explicit preference>

**How to apply:** <when and where this rule kicks in; include edge cases>
```

Rules without "Why" become superstitions. A future LLM cannot reason about edge cases without knowing what the rule is protecting against.

**Enforcement levels:**
- `mandatory` — cannot be overridden by a lower scope; `engram validate` errors if violated. Use for company compliance rules, security policies, team-wide hard constraints.
- `default` — may be overridden, but the overriding asset must declare `overrides: <id>`. Use for team conventions, recommended practices.
- `hint` — freely overridable without explanation. Use for personal stylistic preferences.

**Example trigger:** "No force push without asking me first." → `feedback` memory at `scope: user`, `enforcement: mandatory`.

---

### `project` — Ongoing work facts

**When to write:** A decision is made, a deadline is set, an incident is learned from, a stakeholder constraint surfaces — any fact about ongoing work that cannot be recovered from code or git history alone.

**Required frontmatter:** Same as `feedback` minus `enforcement` (defaults to `hint`)

**Body structure:**

```
<one-line fact or decision>

**Why:** <motivation — constraint, deadline, stakeholder requirement>

**How to apply:** <how this shapes future suggestions or plans>
```

**Absolute dates only.** Convert "next Thursday" to `2026-04-23` at write time. Relative dates are meaningless when the memory is read a month later. Set `expires:` when the fact is time-bounded — the Consistency Engine will surface it for review after the date passes.

**Example trigger:** "We're freezing merges after 2026-04-20 for the release." → `project` memory with `expires: 2026-04-21`.

---

### `reference` — Pointers to external resources

**When to write:** The user points you to a system, dashboard, ticket tracker, internal wiki, or authoritative external codebase you will want to consult again.

**Body:** Free prose. Cover three things: how to locate the resource, why it matters, and when to consult it. A reference that omits the "when to consult it" clause scores poorly with the Relevance Gate and is unlikely to load when it should.

**Example trigger:** "Check Linear project INGEST for pipeline bugs." → `reference` memory: name of the system, what it tracks, when to look there.

---

### `workflow_ptr` — Pointer into a Workflow asset

**When to write:** A frequently-used procedural pattern exists as a Workflow asset at `workflows/<name>/`, and needs to be surfaced in `MEMORY.md` so an LLM discovers it without loading the full `workflow.md` into the context budget.

**Required frontmatter:** `workflow_ref` (path to `workflows/<name>/`)

**Body:** 1–3 paragraphs covering: what the workflow does, when to use it, and the expected outcome. Do not reproduce the steps — those live in `workflow.md`. The body answers "should I load this workflow?" not "what does the workflow do in full?"

**Example trigger:** The team has a `workflows/release-checklist/` that covers every step from branch freeze to changelog publication. Add a `workflow_ptr` memory so the LLM sees it at session start when a release-related task arrives.

---

### `agent` — LLM-learned heuristics

**When to write:** You noticed a pattern that works across multiple sessions, but no human explicitly stated it. The source is your own observation, not a user instruction.

**Required frontmatter:** Same as `feedback`, plus `source: agent-learned` (or a specific workflow revision reference), plus a `confidence` block bootstrapped at `{validated_count: 0, contradicted_count: 0}`.

**Body structure:** Same as `feedback` — one-line heuristic + **Why:** + **How to apply:** — but the "Why" must cite concrete observed outcomes. "Observed 5 successful merges using this approach" is a valid Why. "This seems cleaner" is not.

**Default trust is lower than `feedback`.** The Consistency Engine scrutinizes `agent` memories more frequently. An `agent` memory is a hypothesis; a `feedback` memory has human authority behind it.

**Example trigger:** After five deployments where pre-squashing commits eliminated CI flakiness, create an `agent` memory recording that pattern, its evidence base, and its known limitations.

---

### Decision tree: which subtype?

Apply in order:

1. Is this a fact about the person? → `user`
2. Is this a rule to follow, stated or confirmed by a human? → `feedback` (set `enforcement` explicitly)
3. Is this a heuristic the LLM inferred from outcomes without explicit human instruction? → `agent` (add `confidence` block)
4. Is this about ongoing work — deadline, decision, incident? → `project` (use absolute dates)
5. Is this a pointer to an external resource? → `reference`
6. Does a complete, executable procedure exist for this? → NOT a memory — it is a Workflow; surface it with `workflow_ptr`
7. Is this extended domain material — multi-section, read deliberately? → NOT a memory — it is a Knowledge Base article; reference from memory if needed

---

## §4. Scope and Enforcement Discipline

Every memory needs `scope:`. Think before writing.

### Scope decision tree

1. Will this apply to every project you personally work on? → `user` scope
2. Will this apply only within one team or department? → `team` scope
3. Will this apply to all teams in the organization? → `org` scope
4. Does this apply only to this project right now? → `project` scope
5. Could this be useful to people outside your membership hierarchy? → consider creating or subscribing to a `pool`

**Default: `project` scope.** Start local, lift up later. Elevate to `user`, `team`, or `org` only when it is clearly broader — when the rule would help multiple projects, multiple people, or the organization as a whole. Elevating prematurely adds noise to higher-scope contexts.

**The cost of over-scoping.** A `user`-scope memory loads in every project session for this user. An `org`-scope memory loads in every project for every member of the organization. The broader the scope, the more carefully the memory needs to be written, the more essential `limitations:` become, and the more important a clear `**Why:**` clause is.

### Enforcement levels (required on `feedback`, optional elsewhere)

**`mandatory`** — "This MUST be followed; override is a validation error."

Write at `mandatory` when:
- A compliance or legal requirement exists
- A security policy is in force
- A team hard rule that has no legitimate exception in normal work

Do not write at `mandatory` by default. The bar is "there is no legitimate case where this rule should be bypassed." If there is a plausible edge case, use `default`.

**`default`** — "This SHOULD be followed; override is allowed with an explicit declaration."

Write at `default` when:
- This is the team's standard approach
- Deviations are legitimate but should be documented
- The rule is a strong recommendation, not a hard constraint

To override a `default` memory, the overriding asset must include `overrides: <id>`.

**`hint`** — "This is a preference; override freely."

Write at `hint` when:
- This is a personal stylistic preference
- This is a weak suggestion
- You want the rule on record but are comfortable with people ignoring it

### Conflict resolution

When two memories in your loaded context disagree:

1. `mandatory` beats `default` beats `hint` — regardless of scope
2. Within the same enforcement level, **more specific wins**: `project > user > team > org`
3. Pool content participates at its `subscribed_at` level in this resolution order
4. If still tied, the LLM arbitrates with both memories present; `engram consistency scan` flags the situation for human review

**Never override a `mandatory` memory without explicit operator approval.** If you believe a mandatory rule is wrong, write a note to the human — do not silently bypass it.

---

## §5. Confidence Maintenance

Every memory tracks four evidence fields: `validated_count`, `contradicted_count`, `last_validated`, `usage_count`. These form the `confidence` block in frontmatter.

### Your responsibility as LLM

**When you act on a memory and reality confirms it was right:**

```bash
engram memory validate-use <id> --outcome=success
```

**When reality contradicts it** — user corrects you, test fails, the actual behavior differs from what the memory predicts:

```bash
engram memory validate-use <id> --outcome=failure
```

**Passive usage** (memory was loaded into context but you did not act on it specifically) → no call needed.

### Why it matters

The Consistency Engine uses `confidence_score` to surface stale and contradicted memories for human review. The formula:

```
score = (validated_count - 2 × contradicted_count - staleness_penalty) / max(1, total_events)
```

Without outcome signals, the engine cannot distinguish good memories from bad. A memory with `validated_count: 0` and `contradicted_count: 0` and `usage_count: 40` tells the engine nothing about whether the memory is actually helping. A memory with `validated_count: 10` and `contradicted_count: 0` tells it the rule is well-supported. Signal when outcomes happen.

### Bootstrapping new memories

Newly created memories — especially `agent` type — start at `{validated_count: 0, contradicted_count: 0}`. This is intentional: they start as hypotheses and graduate through evidence. After approximately N=3 successful uses without contradiction, a memory becomes eligible for promotion to `stable` lifecycle state. The exact N is configurable; the principle is that stability requires evidence.

### Staleness penalty

The formula applies a staleness penalty based on how long since `last_validated`:

- Within 90 days: no penalty
- 90–365 days: 0.3 penalty
- Beyond 365 days: 0.7 penalty

You do not need to compute this. Just call `validate-use` when outcomes happen. The engine handles scoring. The practical implication: a memory that was right two years ago but has never been re-validated will score poorly and surface for review — that is the intended behavior.

---

## §6. The `limitations:` Field

The optional `limitations:` frontmatter field (a list of strings) is an **honest boundary declaration** — it tells future readers when this memory does not apply.

Use it when a rule has real edge cases. Not as a hedge ("may not always apply"), but as a concrete scoping statement:

```yaml
limitations:
  - benchmarks measured on M1 Pro; x86_64 results may differ
  - written against Tokio v0.4.x; post-v1.0 may change async behavior
  - does not apply to hotfix branches — those have their own flow
```

Without `limitations:`, readers over-apply the rule. With it, they know when to step outside without needing to re-derive the exception from first principles.

**Where `limitations:` is especially important:**

- `feedback` memories: rules that have genuine exceptions you have already thought through
- `project` memories: decisions made under specific constraints that do not hold forever
- `agent` memories: patterns observed in limited contexts — state the context explicitly

**Consistency Engine interaction.** If a memory has high `usage_count`, any `contradicted_count` greater than zero, and no `limitations:` declared, the Consistency Engine proposes adding limitations. It is suggesting that the memory's edge cases have been observed but not documented. Accept or refine the proposal — do not dismiss it without checking whether the contradictions reveal an actual scope restriction.

---

## §7. Inter-Repo Inbox Discipline

You may discover issues in other repositories while working on this one. The Inter-Repo Messenger (`engram inbox send`) lets you send a structured message to another repo's inbox.

### When to send

- `bug-report`: a concrete bug in repo B's API or code is affecting your work on repo A
- `api-change`: you have a concrete proposal to improve repo B's API
- `question`: you need information that only repo B's maintainers can provide
- `update-notify`: you made a change in repo A that repo B's LLM needs to know about
- `task`: you are requesting specific, concrete work in repo B

### When not to send

- Vague reactions without a concrete proposal ("this design seems off")
- Style preferences without direct impact on correctness
- Questions answerable from repo B's existing documentation
- Duplicates of an already-open message (check before sending)
- Open-ended design discussions that belong in GitHub Discussions

### Message discipline

Include `related_code_refs` — use the format `path/file.py:L42@sha` so the recipient can navigate directly to the issue without guessing. Include a concrete resolution path in the `**How to resolve:**` section: "add a check on line 42" is actionable; "this should be better" is not. Use `severity: warning` for most issues and `severity: critical` only when the bug causes data loss, security risk, or hard failure.

```bash
engram inbox send \
  --to=repo-b \
  --intent=bug-report \
  --severity=warning \
  --message="read_config() silently returns {} on missing file — should raise FileNotFoundError." \
  --code-ref="libb/config.py:L42@abc123"
```

### Rate limits

20 pending concurrent messages per sender-recipient pair; 50 per 24 hours total. Hitting these limits is a signal to reconsider your approach — if you are generating that many inbox messages, you may be working at the wrong granularity. Broader design questions belong in discussions, not in individual messages.

---

## §8. Workflows and Knowledge Base — When Memory Is Not Enough

Memory files are short, atomic assertions. Not everything belongs there.

### Use a Workflow when

There is a **repeatable procedure with executable steps** — pre-merge checks, deployment sequences, dependency upgrade routines, incident response scripts. Workflows have a `spine.*` that runs, `fixtures/` that validate it, and `metrics.yaml` that tracks its success rate over time. If you would describe a procedure in memory as a numbered list of shell commands, it is a Workflow.

Location: `.memory/workflows/<name>/`

Surface it in Memory via a `workflow_ptr` so the LLM discovers it without loading the full procedure prematurely.

### Use a Knowledge Base article when

There is **extended domain material** that someone would read deliberately — an architecture overview, a migration guide, a platform conventions reference, a security model explanation. KB articles are multi-section documents. The LLM-generated `_compiled.md` digest enters the context budget efficiently when the full article is too large to load.

Location: `.memory/kb/<topic>/`

### Decision rule

- What you are writing has a single clear assertion that can be independently superseded → Memory
- What you are writing has steps that must run with a measurable outcome → Workflow
- What you are writing is reference material a human would navigate by section heading → Knowledge Base
- What you are writing is more than 3 sections or reads like a tutorial → Knowledge Base, not Memory

Writing a 30-line memory that describes a procedure step-by-step is a sign the asset wants to be a Workflow. The Evolve Engine will eventually propose the promotion — but you can save it the trouble by placing it correctly from the start.

---

## §9. What NOT to Save in Memory

Even when explicitly asked to save, consider whether the request fits the memory system.

**Do not save:**

1. **Code patterns, conventions, or file paths** — derivable by reading the codebase. If the pattern is important enough to memorize, it belongs in a KB article.
2. **Git history or recent changes** — `git log` and `git blame` are authoritative. A memory that says "we merged the auth refactor on 2026-04-15" adds noise; the commit exists.
3. **Debugging solutions for specific bugs** — the fix is in code; the context is in the commit message. A `reference` memory pointing to the commit or issue is sufficient.
4. **Contents of `CLAUDE.md` / `AGENTS.md`** — already loaded by the adapter at session start. Duplicating adapter content in Memory creates `silent-override` conflicts and inflates the context budget.
5. **Transient session state** — current task, temporary decisions, the list of files you just modified, today's working notes.
6. **Summaries of recent activity, PR lists, changelog entries** — the version control system and issue tracker are authoritative. Memory is not a changelog.
7. **Things already stated in SPEC, DESIGN, or other canonical project docs** — write a `reference` memory pointing to the document instead.

**When the user asks you to save something in this list:**

Do not refuse — ask back: "What about this is surprising or non-obvious?" The surprising part is what deserves memory. The rest is already findable.

Example: "Save my PR list" — ask "What about this PR list should I remember? The list itself is in GitHub. Is there a pattern, a decision, or a constraint about these PRs that won't be obvious later?" Whatever they name is the memory.

---

## §10. Evolving Memory Over Time

### Supersede, do not rewrite

When a memory is wrong or outdated:

**Preferred:** Create a new memory with `supersedes: <old-id>`. The old memory's lifecycle transitions to `deprecated`. History is preserved; the lineage is traceable; the Consistency Engine can track the evolution.

**Avoid:** Editing the old memory in place without creating a supersede chain. This breaks references, hides the history, and prevents the Consistency Engine from detecting `silent-override` conflicts.

**How to supersede:**

1. Write a new memory with corrected content
2. Add `supersedes: <old-id>` to the new memory's frontmatter
3. Run `engram memory archive <old-id>` or let the Consistency Engine propose the transition
4. Update `MEMORY.md` to reflect the new entry

### Update without superseding

When a memory is accurate but stale — the facts still hold but details have changed — use `engram memory update` to refresh the content and bump the `updated` field. This does not create a supersede chain and is appropriate for minor corrections, new limitations, or refreshed examples.

### Archive, do not delete

Even when a memory is clearly obsolete, use `engram memory archive <id>` rather than deleting the file directly. Archived memories move to `~/.engram/archive/` with a retention floor of six months before physical removal. This is not ceremony — it is how the Consistency Engine tracks that "we intentionally stopped believing X," which is different from "X was never recorded."

Physical deletion of a memory file without archiving is a protocol violation. Any tool that does this silently is non-compliant.

### When a memory is controversial

Do not silently supersede a memory that other assets depend on. Check with `engram consistency scan` to find inbound references. If other memories or workflows cite the asset you want to change, draft the superseding memory and let `engram review` surface it for human confirmation before the old one is deprecated.

---

## §11. Memory and Cross-Scope Interaction

Before writing, think about scope. The right question is not "what scope is technically correct" but "at what scope does this rule actually apply."

### Elevating scope

- A rule that applies to every project you personally work on belongs at `user` scope, not in a project-specific `project` scope memory that you duplicate in every repo.
- A rule that applies across all projects your team works on belongs at `team` scope. One `team`-scope memory saves every team member from writing the same memory independently.
- A rule that the organization has adopted belongs at `org` scope.

When a pattern recurs across multiple projects, that recurrence is the signal to consider elevation. Propose it to the relevant scope (add to `~/.engram/team/<name>/` or raise it in the team's memory review).

### Pool subscriptions

If knowledge would be useful to people outside your membership hierarchy — to other teams, other organizations, or the broader community — consider whether it belongs in a `pool`. Pools are opt-in, topic-scoped knowledge stores. A pool subscribed at `org` level propagates its content to every project in the org. A pool subscribed at `user` level affects only your own projects.

### Higher scope requires higher care

When writing at `team` or `org` scope, apply a stricter standard:

- `limitations:` is more important, not less — a rule at org scope affects many people and many contexts; unanticipated edge cases are more likely
- `**Why:**` must be detailed — future readers at org scope may not share your context
- `enforcement:` must be set deliberately — `mandatory` at org scope is a strong statement

An org-scope `feedback` memory with `enforcement: mandatory` is the most authoritative thing in the engram system. It takes precedence over every `user`, `team`, and `project` memory. Write it only when that is what you actually mean.

---

## §12. Quick Audit Checklist

Before finishing any memory creation or update, verify:

- [ ] Required frontmatter fields present: `name`, `description`, `type`, `scope`
- [ ] For `feedback`: `enforcement` set explicitly (not defaulted)
- [ ] For `project`: all dates are absolute ISO 8601 (not "next week" or "Q2")
- [ ] Body includes `**Why:**` and `**How to apply:**` sections (for `feedback`, `project`, `agent`)
- [ ] References point to real paths, URLs, or asset IDs (not stale or fabricated)
- [ ] No duplicate of an existing memory — searched first with `engram memory search "<topic>"`
- [ ] Scope is the tightest reasonable level (default to `project`; elevate only when clearly broader)
- [ ] `description` is ≤150 characters (it appears in `MEMORY.md` and must be scannable)
- [ ] No sensitive content (API keys, private credentials, personal information) unless scope is strictly local and access is controlled
- [ ] For `agent`: `confidence` block present with `source: agent-learned` or a specific revision reference
- [ ] For superseding memory: `supersedes: <old-id>` is declared and the old memory is queued for archiving
- [ ] `MEMORY.md` will be updated in the same operation (index out of sync with store is a bug)

---

Memory discipline compounds. One well-written memory prevents hundreds of repeat conversations over the life of a project. Take the 30 seconds to pick the right scope, write a real `**Why:**` clause, and set `enforcement:` deliberately — you are writing for every future session, every future LLM, every future teammate who inherits the store.

Questions about the methodology: [GitHub Discussions](https://github.com/TbusOS/engram/discussions).
Bug in CLI behavior related to memory handling: [GitHub Issues](https://github.com/TbusOS/engram/issues).
