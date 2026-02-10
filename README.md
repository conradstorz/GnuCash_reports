# GCGAAP – GnuCash GAAP Validation and Reporting

A Python-based command-line tool for validating GnuCash books and generating GAAP-style financial reports.

## Overview

GCGAAP provides:

- **Validation** of GnuCash book integrity (double-entry consistency, transaction balancing)
- **Entity mapping** to handle multiple logical entities within a single GnuCash file
- **GAAP-style reporting** including Balance Sheets (with Income Statement and Cash Flow planned)
- **Strict balancing enforcement** at transaction, entity, and consolidated levels

## Features

- ✅ Read-only GnuCash book access
- ✅ Persistent JSON-based entity mapping
- ✅ **Smart entity inference with AI pattern analysis**
- ✅ Transaction-level validation
- ✅ Imbalance/Orphan account detection
- ✅ **Comprehensive violations reporting with entity-level analysis**
- ✅ Entity scanning for unmapped accounts
- 🚧 Balance Sheet reporting (planned)
- 🚧 Multi-entity accounting equation validation (planned)

## Requirements

- Python 3.10 or higher
- GnuCash book file (SQLite format)
- Windows (primary target), though should work cross-platform

## Installation

Using `uv` (recommended):

```bash
uv pip install -e .
```

Or using pip:

```bash
pip install -e .
```

## Quick Start

### 1. Intelligently detect entities (NEW!)

```bash
# Analyze your book and get entity suggestions
gcgaap entity-infer --file mybook.gnucash

# Save the suggestions to a file
gcgaap entity-infer --file mybook.gnucash --output entity-map.json
```

### 2. Run violations report (recommended)

```bash
# Get comprehensive data quality report
gcgaap violations --file mybook.gnucash --as-of 2026-12-31

# The vScan for unmapped accounts

```bash
gcgaap entity-scan --file mybook.gnucash --entity-map entity-map.json
```

### 4. iolations report identifies:
# - Imbalanced transactions (critical)
# - Unmapped accounts (errors)
# - Entity-level accounting equation violations (errors)
# - Imbalance/Orphan accounts with non-zero balances (warnings)
```

The violations report provides:
- Summary of all data quality issues by category
- Entity balance summary showing which entities don't balance
- Detailed violation information with context
- Actionable recommendations for fixing issues

This is the best starting point to understand what needs to be fixed in your GnuCash data.

### 3. Scan for unmapped accounts

```bash
gcgaap entity-scan --file mybook.gnucash --entity-map entity-map.json
```

### 3. Validate your book

```bash
# Standard validation (warnings for unmapped accounts)
gcgaap validate --file mybook.gnucash --entity-map entity-map.json

# Strict validation (required before generating reports)
# En5ures 100% entity mapping - errors if any account is unmapped
gcgaap validate --file mybook.gnucash --entity-map entity-map.json --strict
```

**Important**: Use `--strict` mode before generating any reports to ensure complete entity mapping and GAAP compliance.

### 4. Generate a Balance Sheet (coming soon)

```bash
gcgaap report balance-sheet --file mybook.gnucash --entity-map entity-map.json --as-of 2026-12-31
```

## Entity Mapping

GCGAAP uses a JSON configuration file to map accounts to logical entities (e.g., personal, various businesses).

Example `entity-map.json`:

```json
{
  "version": 1,
  "entities": {
    "personal": {
      "label": "Personal Finances",
      "type": "individual"
    },
    "alpha_llc": {
      "label": "Alpha LLC",
      "type": "business"
    }
  },
  "accounts": {
    "abc123-guid-here": "personal",
    "def456-guid-here": "alpha_llc"
  },
  "patterns": {
    "alpha_llc": ["^Assets:Business:Alpha.*", "^Liabilities:Alpha.*"]
  }
}
```

## Development

### Setup development environment

```bash
uv pip install -e ".[dev]"
```

### Run tests

```bash
pytest
```

### Code formatting

```bash
black gcgaap/
ruff check gcgaap/
```

## Architecture

```
gcgaap/
├── gcgaap/
│   ├── __init__.py
│   ├── cli.py              # CLI entrypoint and commands
│   ├── config.py           # Configuration management
│   ├── entity_map.py       # Entity mapping logic
│   ├── entity_inference.py # Smart entity detection
│   ├── gnucash_access.py   # GnuCash data access abstraction
│   ├── validate.py         # Validation engine
│   ├── violations.py       # Comprehensive violations reporting
│   └── reports/
│       ├── __init__.py
│       └── balance_sheet.py
├── pyproject.toml
└── README.md
```

## Design Principles

- **Correctness**: Strict GAAP compliance and double-entry validation
- **Transparency**: Readable code with explicit accounting logic
- **Safety**: Read-only operations, no book modifications
- **Extensibility**: Modular design for additional reports and validations

## License

MIT License - see [LICENSE](LICENSE) file for details.

Copyright (c) 2026 Conrad Storz

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.
