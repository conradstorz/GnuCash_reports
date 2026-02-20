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
| CLI | `gcgaap/cli.py` | All 12 commands via Click; orchestration only — no business logic |
| Data Access | `gcgaap/gnucash_access.py` | Abstracts piecash/SQLAlchemy; returns `GCAccount`, `GCTransaction`, `GCTransactionSplit` dataclasses |
| Entity Mapping | `gcgaap/entity_map.py` | Loads `entity-map.json`; maps account GUIDs to entity keys via direct GUID mappings and regex patterns |
| Validation | `gcgaap/validate.py` | 7 violation types; strict mode requires all accounts mapped |
| Reporting | `gcgaap/reports/balance_sheet.py` | Computes balances as-of date, classifies accounts, enforces A = L + E |
| Write Ops | `gcgaap/balance_xacts.py`, `gcgaap/repair.py` | Only modules that write to the GnuCash database; always create a backup first |

**Data flow:** CLI parses args → `EntityMap.load()` → `GnuCashBook` context manager (opens file read-only via piecash) → business logic module → formatted output.

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

## cli.py Size Warning

`cli.py` is 1,743 lines and contains all command implementations inline. When adding new commands, follow the existing pattern but be aware this file is a refactoring candidate — new substantial commands should ideally be implemented as separate modules (like `balance_xacts.py`) with thin CLI wrappers in `cli.py`.
