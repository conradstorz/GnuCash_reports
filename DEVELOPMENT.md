# GCGAAP Development Guide

## Project Structure

```
gcgaap/
├── gcgaap/                 # Main package
│   ├── __init__.py         # Package initialization
│   ├── cli.py              # Command-line interface (Click-based)
│   ├── config.py           # Configuration and logging setup
│   ├── entity_map.py       # Entity mapping logic
│   ├── entity_inference.py # Smart entity inference (Phase 1.1)
│   ├── gnucash_access.py   # GnuCash data access abstraction
│   ├── validate.py         # Validation engine
│   └── reports/            # Report modules
│       ├── __init__.py
│       └── balance_sheet.py
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

(To be implemented)

```bash
pytest
```

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

### Read-Only Operations

**CRITICAL**: All GnuCash operations must be read-only. The tool NEVER modifies the book.

- `GnuCashBook` opens files with `readonly=True`
- No write operations are exposed

### Error Handling

- Use Python exceptions for unexpected errors
- Return `ValidationResult` for expected validation failures
- Log appropriately at each level
- Provide clear error messages to users

## Implementation Phases

### Phase 1 (Complete)
- ✅ Project setup and structure
- ✅ Entity mapping (load/save/resolve)
- ✅ GnuCash data access abstraction
- ✅ Validation engine (transaction balancing, account mapping)
- ✅ CLI with `entity-scan` and `validate` commands

### Phase 1.1 (Complete - NEW!)
- ✅ Smart entity inference with pattern analysis
- ✅ AI-powered entity detection from account names
- ✅ Business entity identification (LLC, Inc, Corp, etc.)
- ✅ Personal/individual entity detection
- ✅ Confidence scoring and pattern generation
- ✅ CLI `entity-infer` command with merge capability

### Phase 2 (NEXT)
- [ ] Extend `GnuCashBook` to compute account balances as of a date
- [ ] Implement Balance Sheet classification and aggregation
- [ ] Add `report balance-sheet` command
- [ ] Implement accounting equation check (A = L + E)

### Phase 3 (FUTURE)
- [ ] Entity-level Balance Sheet validation
- [ ] Consolidated vs. sum-of-entities verification
- [ ] Additional validation rules

### Phase 4 (FUTURE)
- [ ] Income Statement
- [ ] Cash Flow Statement
- [ ] Additional reports

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
