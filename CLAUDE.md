# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**GCGAAP** is a Python CLI tool that validates GnuCash SQLite books and generates GAAP-compliant financial reports with strict accounting equation enforcement (A = L + E). It supports multi-entity accounting — multiple businesses or individuals tracked in a single GnuCash file, separated by an entity map.

## Development Commands

```bash
# Install (editable mode with dev tools)
uv pip install -e ".[dev]"

# Format
black gcgaap/

# Lint
ruff check gcgaap/

# Test (no tests exist yet — pytest is configured but tests/ is empty)
pytest
```

## Architecture

The project follows a strict layered architecture:

| Layer | Module | Role |
|-------|--------|------|
| CLI entry | `gcgaap/cli.py` | ~50-line main group; registers four subgroups |
| CLI groups | `gcgaap/commands/{entity,report,xact,db}.py` | Thin Click wrappers; no business logic |
| Shared options | `gcgaap/commands/_options.py` | Reusable Click option decorator factories |
| Data Access | `gcgaap/gnucash_access.py` | Abstracts piecash/SQLAlchemy; returns `GCAccount`, `GCTransaction`, `GCTransactionSplit` dataclasses |
| Entity Mapping | `gcgaap/entity_map.py` | Loads `entity-map.json`; maps account GUIDs to entity keys |
| Entity Inference | `gcgaap/entity_inference.py` | Pattern analysis to suggest entity groupings |
| Validation | `gcgaap/validate.py` | 7 violation types; strict mode requires all accounts mapped |
| Reporting | `gcgaap/reports/balance_sheet.py` | Computes balances as-of date, classifies accounts, enforces A = L + E |
| Write Ops | `gcgaap/balance_xacts.py`, `gcgaap/repair.py` | Only modules that write to the GnuCash database; always create a backup first |

**Data flow:** CLI parses args → `EntityMap.load()` → `GnuCashBook` context manager (opens file read-only via piecash) → business logic module → formatted output.

**CLI structure:**
```
gcgaap entity   scan | infer | remap
gcgaap report   balance-sheet | balance-check
gcgaap xact     cross-entity | balance
gcgaap db       validate | violations | repair-dates | snapshot | diff-snapshots
```

## Critical Constraints

- **Read-only by default.** `GnuCashBook` always opens with `readonly=True`. Only `balance-xacts` and `repair-dates` write to the database, and both must create a backup before modifying anything.
- **SQLite only.** piecash only supports the SQLite GnuCash format (default since GnuCash 2.4). XML format books are not supported.
- **No automated tests.** `tests/` directory does not exist. `pytest` is configured pointing to `tests/` — create that directory and test files before running.

## Code Style

- Line length: 100 characters (black + ruff both configured)
- Target: Python 3.10+
- Explicit variable names, full docstrings, type hints on all functions
- Small focused functions — no lambdas for core logic, no complex comprehensions
- Comments explain *why*, not *what*

## Entity Map Format

The `entity-map.json` file has three keys:
- `entities` — defines entity keys with `label` and `type` (`"individual"` or `"business"`)
- `accounts` — maps account GUIDs directly to entity keys
- `patterns` — maps entity keys to lists of regex patterns matched against full account names

Pattern matching and GUID mapping are applied together; direct GUID mappings take precedence.

## Adding New Commands

Commands live in `gcgaap/commands/<group>.py`. Add the new command to the appropriate group file and register it with `@<group>_group.command(name="...")`. Substantial business logic belongs in a dedicated module (e.g., `balance_xacts.py`) — the command file should only parse args, call the module, and handle exit codes.
