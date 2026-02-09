# Quick Installation and Usage

## Installation

### Option 1: Using uv (Recommended)

```powershell
# Install uv if you haven't already
# See: https://github.com/astral-sh/uv

# Install GCGAAP
uv pip install -e .

# Or with development dependencies
uv pip install -e ".[dev]"
```

### Option 2: Using pip

```powershell
pip install -e .

# Or with development dependencies
pip install -e ".[dev]"
```

## Quick Start

### 1. Verify Installation

```powershell
gcgaap --help
```

### 2. Smart Entity Detection (NEW - Phase 1.1)

**Let GCGAAP analyze your book and suggest entities automatically:**

```powershell
# Analyze and display suggestions
gcgaap entity-infer -f path\to\your\book.gnucash

# Save suggestions directly to entity-map.json
gcgaap entity-infer -f path\to\your\book.gnucash -o entity-map.json
```

This will intelligently detect:
- Business entities based on company names (LLC, Inc, Corp, etc.)
- Personal/individual accounts
- Common patterns in your account structure

### 3. Manual Entity Map (Alternative)

Copy the example entity map and customize it:

```powershell
copy entity-map.example.json entity-map.json
```

Edit `entity-map.json` to define your entities and account patterns.

### 4. Scan for Unmapped Accounts

```powershell
gcgaap entity-scan --file path\to\your\book.gnucash --entity-map entity-map.json
```

This will show accounts that need to be added to your entity map.

### 5. Validate Your Book

```powershell
# Standard validation
gcgaap validate --file path\to\your\book.gnucash --entity-map entity-map.json

# Strict validation (required before reports)
# This ensures ALL accounts are mapped - critical for GAAP compliance
gcgaap validate --file path\to\your\book.gnucash --entity-map entity-map.json --strict
```

**When to use --strict mode:**
- Before generating any financial reports
- To ensure 100% entity mapping coverage
- To guarantee sum of entity reports = total book balances
- For complete GAAP compliance validation
```

Add `--verbose` for detailed logging:

```powershell
gcgaap validate --file path\to\your\book.gnucash --entity-map entity-map.json --verbose
```

## Common Workflows

### Initial Setup with a New Book

1. Run entity-scan to see all accounts
2. Create entity definitions in entity-map.json
3. Add account GUIDs or patterns to map accounts
4. Run entity-scan again to verify all accounts are mapped
5. Run validate to check book integrity

### Regular Validation

```powershell
# Quick validation
gcgaap validate -f mybook.gnucash

# Verbose validation with custom tolerance
gcgaap validate -f mybook.gnucash -t 0.001 --verbose
```

## Troubleshooting

### "piecash library not available"

Install piecash:

```powershell
pip install piecash
```

Or if using uv:

```powershell
uv pip install piecash
```

### "GnuCash book file not found"

Make sure the path to your .gnucash file is correct. Use absolute paths if needed:

```powershell
gcgaap validate -f "D:\Documents\MyBook.gnucash"
```

### GnuCash File Lock

Make sure GnuCash is not currently open with your book file. GCGAAP opens files read-only, but some systems may still lock the file.

## Next Steps

- See [README.md](README.md) for detailed documentation
- See [DEVELOPMENT.md](DEVELOPMENT.md) for development guidelines
- Check [CHANGELOG.md](CHANGELOG.md) for version history
