# engram Website Maintenance Guide

This document is for developers maintaining the GitHub Pages site at `docs/`.

---

## File layout

```
docs/
├── .nojekyll          # empty; disables Jekyll on GitHub Pages
├── index.html         # language chooser with auto-redirect
├── en/index.html      # English landing page
├── zh/index.html      # Chinese mirror (same structure, translated)
├── assets/
│   ├── fonts.css      # copied from anthropic-design skill
│   ├── anthropic.css  # copied from anthropic-design skill
│   └── app.css        # engram-specific additions only
└── WEBSITE-MAINT.md   # this file
```

---

## Section-to-source-of-truth map

| Section ID | Section title | Source of truth | File(s) to sync |
|---|---|---|---|
| A | Header nav | n/a (static links) | en/ + zh/ nav bar |
| B | Announcement banner | n/a (release status) | en/ + zh/ banner |
| C | Hero — headline + architecture SVG | README.md §Five-layer architecture, DESIGN.md §2 | en/ + zh/ hero section |
| D | Problem statement | README.md §What engram is | en/ + zh/ problem section |
| E | Five-layer architecture detail | DESIGN.md §2.1 layer diagram + roles | en/ + zh/ architecture section |
| F | Three asset classes | SPEC.md §3, README.md §Three asset classes | en/ + zh/ asset classes section |
| G | Two-axis scope model SVG | README.md §Scope, SPEC.md §8 (when written) | en/ + zh/ scope section |
| H | Consistency Engine — 7 conflict classes | SPEC.md §11, README.md §Consistency | en/ + zh/ consistency section |
| I | Cross-repo inbox flow SVG | README.md §Cross-repo collaboration, SPEC.md §cross-repo | en/ + zh/ inbox section |
| J | Differentiators table | README.md §Differentiators table | en/ + zh/ comparison section |
| K | Wisdom Metrics sparklines | DESIGN.md §5 Wisdom Metrics | en/ + zh/ wisdom section |
| L | Philosophy principles | README.md §Philosophy, SPEC.md §2 core principles | en/ + zh/ philosophy section |
| M | Quick Start code blocks | README.md §Quick start | en/ + zh/ quick start section |
| N | Roadmap milestones | docs/superpowers/plans/2026-04-18-engram-v0.2-rewrite.md | en/ + zh/ roadmap section |
| O | Inspirations | README.md §Inspiration | en/ + zh/ inspirations section |
| P | CTA + Footer links | GitHub URLs | en/ + zh/ footer |

---

## When to update the site

- **SPEC §3 or §8 changes** (asset classes, scope model) → update sections F, G in both en/ and zh/
- **SPEC §11 conflict class taxonomy changes** → update section H conflict grid in both pages
- **DESIGN.md §2 layer diagram changes** → update hero SVG (section C) and detail SVG (section E)
- **DESIGN.md §5 Wisdom Metrics renamed/added** → update section K sparklines
- **README.md differentiators table changes** → update section J capability matrix
- **New milestone added to roadmap** → update section N roadmap strip
- **New inspiration credit** → update section O inspiration cards

Always update **both** `en/index.html` and `zh/index.html` in the same commit. They must stay structurally in sync.

---

## How to update inline SVG diagrams

Each SVG in the pages is self-contained inline SVG with a `role="img"` and `aria-label`. To update:

1. Find the SVG by its `aria-label` string (e.g. `"engram five-layer architecture overview"`).
2. Edit the SVG directly in the HTML file. Use the anthropic-design color palette:
   - Layer 3 Intelligence: `#d97757` (orange)
   - Layer 1/2 Data/Control: `#6a9bcc` (blue)
   - Layer 4/5 Access/Observation: `#788c5d` (green)
   - Background / subtle: `#f0ede3`
   - Labels: `#6b6a5f`
3. Keep `font-size` ≥ 12 in SVG `<text>` elements (renders ≥ 9px at 1440px viewport).
4. Run verify + visual-audit after changes (see Verification section).

Diagrams and their sections:

| aria-label | Section | Both pages? |
|---|---|---|
| `engram five-layer architecture overview` | Hero (C) | yes |
| `Detailed five-layer architecture diagram` | Architecture (E) | yes |
| `Two-axis scope model diagram` | Scope (G) | yes |
| `factual-conflict icon` (and 6 siblings) | Consistency (H) | yes |
| `Cross-repo inbox flow` | Inbox (I) | yes |
| `Workflow Mastery sparkline chart` (and 3 siblings) | Wisdom (K) | yes |

---

## Verification (run before every deploy)

The anthropic-design skill provides three verification scripts. Run from the repo root:

```bash
# 1. Structural validation (placeholder check, ghost classes, SVG balance, container rules)
python3 /path/to/sky-skills/skills/anthropic-design/scripts/verify.py docs/en/index.html
python3 /path/to/sky-skills/skills/anthropic-design/scripts/verify.py docs/zh/index.html

# 2. Visual audit (WCAG contrast, hero SVG sizing, orphan card detection)
node /path/to/sky-skills/skills/anthropic-design/scripts/visual-audit.mjs docs/en/index.html
node /path/to/sky-skills/skills/anthropic-design/scripts/visual-audit.mjs docs/zh/index.html

# 3. Full-page screenshot for eyeball review
node /path/to/sky-skills/skills/anthropic-design/scripts/screenshot.mjs docs/en/index.html /tmp/engram-en.png
node /path/to/sky-skills/skills/anthropic-design/scripts/screenshot.mjs docs/zh/index.html /tmp/engram-zh.png
```

All three scripts must exit 0. Visual-audit `[error]` items (contrast < 3) must be fixed. `[warn]` items are advisory.

---

## Local preview

```bash
python3 -m http.server 8000 --directory docs/
# then open http://localhost:8000/
```

The language chooser at `index.html` will auto-redirect based on `navigator.language`. To force English: open `http://localhost:8000/en/` directly.

---

## GitHub Pages deployment

1. Push `main` branch with the `docs/` directory present.
2. In the GitHub repository: **Settings → Pages → Source = main branch, /docs folder**.
3. The site will be live at `https://<owner>.github.io/engram/`.
4. `docs/.nojekyll` disables Jekyll processing — required because the directory names (en/, zh/) and assets do not follow Jekyll conventions.

---

## CSS notes

`docs/assets/anthropic.css` and `docs/assets/fonts.css` are copied verbatim from the anthropic-design skill. Do not edit them directly; re-copy from the skill when the design system updates.

`docs/assets/app.css` contains only engram-specific class additions (`.engram-*` prefix). Keep it under 200 lines. Every class defined here must be referenced by at least one element in the HTML pages.
