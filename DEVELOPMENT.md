# GCGAAP Development Guide

## Project Structure

```
gcgaap/
├── gcgaap/                 # Main package
│   ├── __init__.py         # Package initialization
│   ├── cli.py              # Main CLI entry point (54 lines)
│   ├── config.py           # Configuration and logging setup
│   ├── entity_map.py       # Entity mapping logic
│   ├── entity_inference.py # Smart entity inference (Phase 1.1)
│   ├── gnucash_access.py   # GnuCash data access abstraction
│   ├── validate.py         # Validation engine
│   ├── violations.py       # Violation reporting
│   ├── balance_xacts.py    # Cross-entity transaction balancing
│   ├── cross_entity.py     # Cross-entity transaction analysis
│   ├── repair.py           # Database repair utilities
│   ├── snapshot.py         # Database snapshot and diff
│   ├── commands/           # Modular CLI commands
│   │   ├── __init__.py
│   │   ├── _options.py      # Shared Click option decorators
│   │   ├── db.py            # Database operations (408 lines)
│   │   ├── entity.py        # Entity management (319 lines)
│   │   ├── report.py        # Report generation (207 lines)
│   │   └── xact.py          # Transaction operations (278 lines)
│   ├── reports/            # Report modules
│   │   ├── __init__.py
│   │   └── balance_sheet.py
│   └── tools/              # Utility tools
│       ├── __init__.py
│       ├── display_entity_tree.py
│       └── entity_account_mapper.py
├── tests/                  # Test suite (236 tests, 2,676 lines)
│   ├── __init__.py
│   ├── conftest.py         # Pytest fixtures
│   ├── helpers.py          # Test utilities
│   ├── test_balance_sheet.py  (624 lines)
│   ├── test_cli.py         (228 lines)
│   ├── test_config.py      (75 lines)
│   ├── test_entity_map.py  (239 lines)
│   ├── test_gnucash_access.py (555 lines)
│   ├── test_repair.py      (343 lines)
│   └── test_validate.py    (612 lines)
├── pyproject.toml          # Project configuration and dependencies
├── README.md               # User documentation
└── DEVELOPMENT.md          # This file
```

## Development Setup

### Prerequisites

- Python 3.10 or higher
- `uv` package manager (recommended) or `pip`
- Windows (primary target platform)

### Initial Setup

1. Clone or create the project directory
2. Install in development mode:

```bash
# Using uv (recommended)
uv pip install -e ".[dev]"

# Or using pip
pip install -e ".[dev]"
```

This installs the package in editable mode with development dependencies.

### Running Commands During Development

After installation, the `gcgaap` command is available:

```bash
gcgaap --help
gcgaap entity-scan --file mybook.gnucash
gcgaap validate --file mybook.gnucash --verbose
```

## Code Style Guidelines

This project prioritizes **readability and maintainability** over cleverness:

### DO:
- Write small, focused functions with descriptive names
- Use explicit variable names
- Add docstrings to all modules, classes, and functions
- Use type hints for function parameters and returns
- Add comments explaining "why", not "what"
- Keep list comprehensions simple and readable

### DON'T:
- Use lambdas for core logic
- Create overly complex list comprehensions
- Use single-letter variable names (except loop indices)
- Sacrifice clarity for brevity

### Example:

```python
# GOOD
def calculate_account_balance(splits: list[GCTransactionSplit]) -> float:
    """
    Calculate the total balance from a list of transaction splits.
    
    Args:
        splits: List of splits to sum.
        
    Returns:
        Total balance.
    """
    total = 0.0
    for split in splits:
        total += split.value
    return total


# AVOID (too clever)
balance = lambda s: sum(x.value for x in s if x.value != 0)
```

## Testing

### Comprehensive Test Suite

The project includes 236 automated tests across 7 test files:

```bash
# Run all tests
pytest

# Run tests with verbose output
pytest -v

# Run specific test file
pytest tests/test_balance_sheet.py

# Run tests matching a pattern
pytest -k "test_validation"
```

### Test Structure

- **conftest.py**: Pytest fixtures including mock GnuCash books
- **helpers.py**: Shared test utilities
- **test_validate.py** (612 lines): Validation logic, all 7 violation types
- **test_balance_sheet.py** (624 lines): Balance sheet calculations, GAAP compliance
- **test_gnucash_access.py** (555 lines): Database access layer, data models
- **test_repair.py** (343 lines): Date repair, database modifications
- **test_entity_map.py** (239 lines): Entity mapping, pattern matching
- **test_cli.py** (228 lines): CLI interface, command integration
- **test_config.py** (75 lines): Configuration, logging

### Writing Tests

Tests use pytest with fixtures for isolation:

```python
def test_balance_sheet_calculates_correctly(mock_book):
    """Test that balance sheet computes correct totals."""
    # Use mock_book fixture from conftest.py
    result = generate_balance_sheet(mock_book, as_of="2026-12-31")
    assert result.total_assets == result.total_liabilities + result.total_equity
```

### Future Testing Priorities

- [ ] Add dedicated test_balance_xacts.py (50+ tests for transaction balancing)
- [ ] Configure pytest-cov for coverage reporting
- [ ] Target 85%+ coverage for core modules

## Code Formatting

Use `black` for consistent formatting:

```bash
black gcgaap/
```

Use `ruff` for linting:

```bash
ruff check gcgaap/
```

## Architecture Principles

### Separation of Concerns

- **CLI layer** (`cli.py`): User interaction, argument parsing, orchestration
- **Data access** (`gnucash_access.py`): GnuCash book reading abstraction
- **Business logic** (`validate.py`, `entity_map.py`): Core accounting rules
- **Reporting** (`reports/`): Report generation and formatting

### Read-Only by Default

**Most operations are read-only**, but two commands modify the database (with automatic backups):

- **Read-only commands**: All validation, reporting, and scanning operations
- **Write commands** (create backup first):
  - `db repair-dates`: Fixes empty date fields
  - `xact balance`: Adds balancing splits to cross-entity transactions

Both write commands:
1. Create automatic timestamped backups before modifications
2. Use `readonly=False` explicitly
3. Provide dry-run mode for preview
4. Require user confirmation (interactive approval)

### Error Handling

- Use Python exceptions for unexpected errors
- Return `ValidationResult` for expected validation failures
- Log appropriately at each level
- Provide clear error messages to users

## Implementation Phases

### Phase 1 (Complete ✅)
- ✅ Project setup and structure
- ✅ Entity mapping (load/save/resolve)
- ✅ GnuCash data access abstraction
- ✅ Validation engine (transaction balancing, account mapping)
- ✅ CLI with `entity-scan` and `validate` commands

### Phase 1.1 (Complete ✅)
- ✅ Smart entity inference with pattern analysis
- ✅ AI-powered entity detection from account names
- ✅ Business entity identification (LLC, Inc, Corp, etc.)
- ✅ Personal/individual entity detection
- ✅ Confidence scoring and pattern generation
- ✅ CLI `entity-infer` command with merge capability

### Phase 2 (Complete ✅)
- ✅ Extended `GnuCashBook` to compute account balances as of a date
- ✅ Balance Sheet classification and aggregation
- ✅ `report balance-sheet` command
- ✅ Accounting equation check (A = L + E)
- ✅ `report balance-check` quick validation command

### Phase 3 (Complete ✅)
- ✅ Entity-level Balance Sheet validation
- ✅ Consolidated vs. sum-of-entities verification
- ✅ Cross-entity transaction analysis
- ✅ Automated cross-entity transaction balancing
- ✅ Comprehensive test suite (236 tests)
- ✅ CLI refactoring into modular command structure

### Phase 4 (Complete ✅)
- ✅ Income Statement / P&L report
- ✅ Trial Balance report
- ✅ Database snapshot and diff utilities
- ✅ Comprehensive violation reporting

### Phase 5 (Future 📅)
- [ ] Cash Flow Statement
- [ ] Budget tracking and comparison
- [ ] Multi-currency support
- [ ] PDF report export
- [ ] Additional export formats (Excel, etc.)

## Common Development Tasks

### Adding a New Validation Rule

1. Add the check logic to `validate.py`
2. Create appropriate `ValidationProblem` instances
3. Add tests
4. Document in user-facing docs

### Adding a New Report

1. Create a new module in `reports/`
2. Define data structures for the report
3. Implement generation logic
4. Add CLI command in `cli.py`
5. Add tests
6. Document

### Modifying Entity Mapping

Edit `entity_map.py`:
- Update `EntityMap` class for new features
- Maintain backward compatibility with existing JSON files
- Update version number if schema changes

## Debugging Tips

### Enable Verbose Logging

```bash
gcgaap validate --file mybook.gnucash --verbose
```

### Test with a Small Book

Create a minimal GnuCash file for testing specific scenarios.

### Use Python Debugger

```python
import pdb; pdb.set_trace()
```

Or use VS Code's built-in debugger with breakpoints.

## GnuCash Library (piecash)

We use `piecash` to read GnuCash files:
- Documentation: https://piecash.readthedocs.io/
- Supports SQLite-based GnuCash files (default since GnuCash 2.4)

The abstraction layer (`gnucash_access.py`) isolates piecash-specific code,
allowing for future library changes if needed.

## Questions?

For design questions, refer to the original Design Document.

For implementation questions, check:
- Code comments and docstrings
- Existing similar implementations in the codebase
- piecash documentation

## Contributing

(Add contribution guidelines when ready for external contributors)
