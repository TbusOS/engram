# cli/ — the engram command-line tool

**Status**: T-10 scaffold landed. Subcommands wired up in T-16 onward (see [`../TASKS.md`](../TASKS.md)).

Python implementation of the `engram` CLI. The SPEC (`../SPEC.md`) is the portable contract; this directory is the reference implementation.

## Layout

```
cli/
├── pyproject.toml                  # package metadata, deps, entry point
└── engram/
    ├── __init__.py                 # exports __version__
    ├── __main__.py                 # `python -m engram` entry
    ├── cli.py                      # click root group
    ├── py.typed                    # PEP 561 marker
    ├── core/                       # paths, frontmatter, fs, graph_db, journal (T-11..T-15)
    └── commands/                   # init, memory, validate, review, status, ... (T-17+)
```

Tests live at the repo root under `../tests/`:

```
tests/
├── unit/cli/                       # fast unit tests (T-23)
├── e2e/                            # end-to-end scenarios (T-24, T-35, T-57, ...)
├── conformance/                    # SPEC-level fixtures (portable across ports)
└── fixtures/                       # shared sample stores
```

## Choice of language

Python + click. Rationale in [`../DESIGN.md`](../DESIGN.md) §4.2. A Go reimplementation may follow once the CLI surface stabilises; the conformance fixtures in `tests/conformance/` guarantee both implementations behave identically.

## Entry point

After install, users run `engram <subcommand>`. The binary is defined in `pyproject.toml`:

```toml
[project.scripts]
engram = "engram.cli:main"
```

## Development install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e "cli[dev]"

engram --version
pytest tests/unit/cli/
```

Run from the repo root (not inside `cli/`). The package is installed in editable mode, so `engram` and `python -m engram` resolve against the source tree.

See [`../CONTRIBUTING.md`](../CONTRIBUTING.md) for the full development workflow, coding style, and CI expectations.
