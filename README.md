# GCGAAP – GnuCash GAAP Validation and Reporting

A Python command-line tool that validates GnuCash books and generates GAAP-compliant financial reports. Think of it as a quality control and reporting layer on top of your GnuCash data.

## What It Does

GCGAAP helps you:

1. **Find and fix data problems** in your GnuCash file before they affect your reports
2. **Map accounts to entities** when you track multiple businesses or people in one GnuCash file
3. **Generate accurate financial reports** with strict accounting equation enforcement
4. **Repair common database issues** that prevent proper reading of GnuCash files

All operations are **read-only** – GCGAAP never modifies your GnuCash file (except the repair-dates command which creates a backup first).

## Key Features

- ✅ **Data quality validation** – Find imbalanced transactions, unmapped accounts, and integrity issues
- ✅ **Smart entity detection** – AI-powered analysis suggests how to map accounts to entities
- ✅ **Balance Sheet reports** – GAAP-compliant reports with accounting equation verification
- ✅ **Database repair** – Fix empty date fields that prevent piecash from reading transactions
- ✅ **Database snapshots** – Track changes to your GnuCash file over time
- ✅ **Multi-entity support** – Handle multiple businesses or individuals in one GnuCash file

## Requirements

- Python 3.10 or higher
- GnuCash book file (SQLite format only)
- Windows, macOS, or Linux

## Installation

Using `uv` (recommended):

```bash
uv pip install -e .
```

Or using pip:

```bash
pip install -e .
```

## Quick Start Guide

### First Time Setup

**Step 1: Check for database issues**

If you're experiencing errors reading your GnuCash file, check for common issues:

```bash
gcgaap repair-dates --file mybook.gnucash --diagnose-only
```

If issues are found, repair them:

```bash
gcgaap repair-dates --file mybook.gnucash
```

This creates a backup before making any changes.

**Step 2: Detect entities automatically**

Let GCGAAP analyze your accounts and suggest entity mappings:

```bash
gcgaap entity-infer --file mybook.gnucash --output entity-map.json
```

Review and edit `entity-map.json` to refine the mappings.

**Step 3: Check data quality**

Run a comprehensive violations report:

```bash
gcgaap violations --file mybook.gnucash --as-of 2026-12-31
```

This shows all data quality issues that need attention.

### Daily Use

**Validate your book**

Before generating reports, validate your data:

```bash
# Standard validation
gcgaap validate --file mybook.gnucash --entity-map entity-map.json

# Strict validation (required for reports)
gcgaap validate --file mybook.gnucash --entity-map entity-map.json --strict
```

**Generate a Balance Sheet**

```bash
# Consolidated balance sheet (all entities combined)
gcgaap balance-sheet --file mybook.gnucash --entity-map entity-map.json --as-of 2026-12-31

# Entity-specific balance sheet
gcgaap balance-sheet --file mybook.gnucash --entity-map entity-map.json --as-of 2026-12-31 --entity my_business

# Export as CSV
gcgaap balance-sheet --file mybook.gnucash --entity-map entity-map.json --as-of 2026-12-31 --format csv

# Export as JSON
gcgaap balance-sheet --file mybook.gnucash --entity-map entity-map.json --as-of 2026-12-31 --format json
```

**Check entity balances quickly**

```bash
# Quick check if all entities balance
gcgaap balance-check --file mybook.gnucash --entity-map entity-map.json --as-of 2026-12-31
```

**Analyze cross-entity transactions**

```bash
# Basic summary of cross-entity transactions
gcgaap cross-entity --file mybook.gnucash --entity-map entity-map.json --as-of 2026-12-31

# Show detailed transaction list
gcgaap cross-entity --file mybook.gnucash --entity-map entity-map.json --as-of 2026-12-31 --verbose

# Show simplified one-line format
gcgaap cross-entity --file mybook.gnucash --entity-map entity-map.json --as-of 2026-12-31 --simple
```

**Track database changes**

Capture snapshots to see what changed:

```bash
# First snapshot (captures "before" state)
gcgaap snapshot --file mybook.gnucash

# Make changes to your GnuCash file...

# Second snapshot (shows what changed)
gcgaap snapshot --file mybook.gnucash

# Or compare specific snapshots
gcgaap diff-snapshots snapshot_before.json snapshot_after.json
```

## Why Track Multiple Businesses in One Database?

At first glance, tracking personal expenses and multiple businesses in a single GnuCash file might seem unconventional. However, this approach offers significant advantages:

**Cash Flow Visibility**  
Money flows between personal accounts, business accounts, and across multiple businesses. Keeping everything in one database lets you see the complete picture. When you transfer funds from your business account to personal savings, or invest personal money in a business, these transactions are immediately visible and properly balanced.

**Automatic Balance Verification**  
Every transaction in GnuCash must balance (debits = credits). By keeping all entities in one file, GnuCash ensures that transfers between entities are always recorded on both sides. You can't accidentally record receiving money in Business A without recording where it came from, whether that's Business B, personal funds, or a loan.

**Simplified Reconciliation**  
Instead of maintaining separate books and trying to reconcile inter-company transactions manually, everything is already recorded once. Your bank accounts reconcile naturally because all the real-world transactions are in one place.

**Tax Time Benefits**  
When preparing taxes, you can generate entity-specific reports for each business while still having access to the complete financial picture. GCGAAP's entity mapping lets you:
- Generate a Balance Sheet for just "Business A"
- Generate a Balance Sheet for just "Personal"
- Generate a consolidated view of everything
- Verify that each entity's books balance independently

**The Trade-off**  
The complexity comes in separating the entities for reporting purposes. That's exactly what GCGAAP's entity mapping feature solves – it lets you maintain one database for operational convenience while generating separate, GAAP-compliant reports for each legal entity.

## Understanding Entity Mapping

If you track multiple businesses or individuals in one GnuCash file, entity mapping tells GCGAAP which accounts belong to which entity. This enables:

- Entity-specific financial reports
- Per-entity accounting equation validation
- Consolidated reports combining all entities

### Entity Map Format

The `entity-map.json` file has three parts:

**1. Entities** – Define each logical entity:

```json
{
  "entities": {
    "personal": {
      "label": "Personal Finances",
      "type": "individual"
    },
    "my_business": {
      "label": "My Business LLC",
      "type": "business"
    }
  }
}
```

**2. Direct account mappings** – Map specific account GUIDs:

```json
{
  "accounts": {
    "abc123-guid-here": "personal",
    "def456-guid-here": "my_business"
  }
}
```

**3. Pattern mappings** – Use regex patterns to match account names:

```json
{
  "patterns": {
    "my_business": [
      "^Assets:Business:MyBusiness.*",
      "^Liabilities:MyBusiness.*",
      "^Equity:MyBusiness.*"
    ],
    "personal": [
      "^Assets:Personal.*",
      "^Liabilities:Personal.*"
    ]
  }
}
```

### Getting Account GUIDs

To find account GUIDs for direct mapping:

```bash
gcgaap entity-scan --file mybook.gnucash --entity-map entity-map.json
```

This lists all unmapped accounts with their GUIDs.

### Regenerating Entity Maps

To regenerate the entire entity mapping from your GnuCash database:

```bash
gcgaap entity-remap --file mybook.gnucash --output entity-map.json
```

This scans all accounts and maps them based on naming patterns with parent-child inheritance.

## Common Commands Reference

| Command | Purpose | Example |
|---------|---------|---------|
| `repair-dates` | Fix empty date fields | `gcgaap repair-dates --file mybook.gnucash` |
| `entity-infer` | Auto-detect entities | `gcgaap entity-infer --file mybook.gnucash --output entity-map.json` |
| `entity-scan` | Find unmapped accounts | `gcgaap entity-scan --file mybook.gnucash --entity-map entity-map.json` |
| `entity-remap` | Regenerate entity mapping | `gcgaap entity-remap --file mybook.gnucash --output entity-map.json` |
| `violations` | Data quality report | `gcgaap violations --file mybook.gnucash --as-of 2026-12-31` |
| `validate` | Validate book integrity | `gcgaap validate --file mybook.gnucash --entity-map entity-map.json --strict` |
| `balance-check` | Quick balance check | `gcgaap balance-check --file mybook.gnucash --entity-map entity-map.json --as-of 2026-12-31` |
| `balance-sheet` | Generate balance sheet | `gcgaap balance-sheet --file mybook.gnucash --entity-map entity-map.json --as-of 2026-12-31` |
| `cross-entity` | Analyze cross-entity transactions | `gcgaap cross-entity --file mybook.gnucash --entity-map entity-map.json --as-of 2026-12-31` |
This error means your GnuCash database has empty date fields. Fix it with:

```bash
gcgaap repair-dates --file mybook.gnucash
```

### "Strict validation FAILED"

This means not all accounts are mapped to entities. Options:

1. Run `entity-scan` to find unmapped accounts
2. Add missing accounts to your entity-map.json
3. Use `entity-infer` to regenerate entity mappings

### "Accounting equation violation"

This indicates data integrity issues. Run the violations report to see details:

```bash
gcgaap violations --file mybook.gnucash --as-of 2026-12-31
```

### Balance Sheet doesn't balance

If Assets ≠ Liabilities + Equity, check:

1. Are all transactions balanced? (Run `validate`)
2. Are all accounts mapped to entities? (Use `--strict`)
3. Are there Imbalance/Orphan accounts? (Check `violations` report)

## Getting Help

```bash
# General help
gcgaap --help

# Command-specific help
gcgaap balance-sheet --help
gcgaap repair-dates --help
```

## Companion Tool: Columbo

Included in this repository is **Columbo** ([COLUMBO_README.md](COLUMBO_README.md)), a standalone database debugging tool that tracks before/after changes to your GnuCash file. Useful for debugging issues or verifying that repairs worked correctly.

## License

Non-Commercial Open Source License - see [LICENSE](LICENSE) file for details.

## Additional Documentation

- [DEVELOPMENT.md](DEVELOPMENT.md) – Developer setup and contribution guidelines
- [QUICKSTART.md](QUICKSTART.md) – Step-by-step tutorial
- [VIOLATIONS_GUIDE.md](VIOLATIONS_GUIDE.md) – Understanding violation types
- [COLUMBO_README.md](COLUMBO_README.md) – Database change tracking tool
