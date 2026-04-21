# docs/ — user-facing documentation

**Status**: skeleton (written during M5–M6)

Deeper documentation that doesn't fit in the top-level README. Organized by audience.

## Planned contents

```
docs/
├── getting-started.md          # step-by-step first project walkthrough
├── cli-reference.md            # every command, every flag
├── format-spec.md              # prose tour of SPEC.md for people who bounce off specs
├── methodology-guide.md        # prose tour of METHODOLOGY.md with real examples
├── migrating-from/
│   ├── claude-code.md
│   ├── chatgpt.md
│   ├── mem0.md
│   └── obsidian.md
└── adapter-guides/
    ├── claude-code.md
    ├── codex.md
    ├── gemini-cli.md
    ├── cursor.md
    └── raw-api.md
```

## Writing style

- **One problem per page**. If a page is titled "Adapter guide for Claude Code", don't also explain what `.memory/` is. Link to the right place instead.
- **Lead with the success path**. 80% of readers want the happy path; put it first. Edge cases, troubleshooting, advanced config go at the bottom or in separate pages.
- **Show real commands, real output**. No `foo` / `bar` placeholders where a concrete example would do.
- **Cross-link liberally**. Docs that sit alone get stale alone.

See [`../CONTRIBUTING.md`](../CONTRIBUTING.md) for more.
