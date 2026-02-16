# Debugging Database Changes with Snapshots

## Overview

The snapshot tool captures the complete state of your GnuCash database and allows you to compare before/after states to see exactly what changed. This is invaluable for:

- **Debugging transaction fixes**: See what "unpost and repost" actually changed
- **Identifying utility bugs**: Detect what your bill creation utility is doing wrong
- **Data integrity investigation**: Track down the source of corruption

## Quick Start

### 1. Capture a "Before" Snapshot

Before fixing a transaction or running your bill creation utility:

```bash
gcgaap snapshot -f "path/to/mybook.gnucash" -o snapshot_before.json
```

**Output:**
```
Snapshot captured successfully!
Timestamp: 2026-02-11T15:20:55.252186
Accounts: 171
Transactions: 3208
Errors: 10

Saved to: snapshot_before.json
```

### 2. Make Your Change

Now do ONE of the following:
- Fix a transaction in GnuCash (unpost/repost, edit dates, etc.)
- Run your bill creation utility
- Make any database modifications

### 3. Capture an "After" Snapshot

```bash
gcgaap snapshot -f "path/to/mybook.gnucash" -o snapshot_after.json
```

### 4. Compare the Snapshots

```bash
gcgaap diff-snapshots -b snapshot_before.json -a snapshot_after.json
```

**Output:**
```
================================================================================
DATABASE SNAPSHOT COMPARISON
================================================================================

Before: 2026-02-11T15:20:55.252186
After:  2026-02-11T15:25:30.123456

SUMMARY
--------------------------------------------------------------------------------
Accounts:     +0 / -0 / ~0
Transactions: +0 / -0 / ~1
Fixed:        1 transaction(s) repaired
Broken:       0 transaction(s) damaged

================================================================================
FIXED TRANSACTIONS (1)
================================================================================

1. Vic's Cafe (GUID: e32d24595e9348828deb1f156ba6152c)

   BEFORE:
     Post Date:  None
     Enter Date: 2024-01-15 14:23:00
     Splits:     0
     Error:      post_date: Couldn't parse datetime string: ''

   AFTER:
     Post Date:  2024-01-15 00:00:00
     Enter Date: 2024-01-15 14:23:00
     Splits:     2
     Error:      None

   CHANGES:
     ✓ Resolved: post_date: Couldn't parse datetime string: ''
     ✓ post_date: 'None' → '2024-01-15 00:00:00'
     ✓ split_count: '0' → '2'
```

## What the Comparison Shows

### Fixed Transactions
Transactions that **had errors before** but are **now valid**. This shows:
- Exact BEFORE fields (what was wrong)
- Exact AFTER fields (what's correct now)
- Summary of changes made

### Broken Transactions
Transactions that **were valid before** but **now have errors**. This indicates your utility or manual edit introduced a problem.

### Modified Transactions
Valid transactions that changed (date edits, description changes, split modifications, etc.)

## Debugging Your Bill Creation Utility

Since you mentioned your bill creation utility likely has a fault, here's the workflow:

### Step 1: Baseline Snapshot
```bash
# Before running your utility
gcgaap snapshot -f book.gnucash -o before_utility_run.json
```

### Step 2: Run Your Utility
Run your bill creation/posting/payment utility normally.

### Step 3: Compare
```bash
# After utility runs
gcgaap snapshot -f book.gnucash -o after_utility_run.json
gcgaap diff-snapshots -b before_utility_run.json -a after_utility_run.json -o utility_changes.txt
```

### Step 4: Analyze Results

Look for the "BROKEN TRANSACTIONS" section. These are the bugs your utility introduced:

```
BROKEN TRANSACTIONS (3)
======================

1. American Legion Post 28 (GUID: 0c04b49c45714c9fa3a0ec60b48d408d)
   New Error: post_date: Couldn't parse datetime string: ''
```

This tells you **exactly which transactions** your utility corrupted and **what field** has the problem.

### Step 5: Fix Your Utility

Common issues to look for in your bill creation code:
- **Empty/null dates**: `post_date` or `enter_date` not being set
- **Missing splits**: Transactions with 0 splits
- **Date format issues**: Wrong datetime format
- **Timezone problems**: Datetime objects without proper timezone handling

## Saving Comparison Results

### Text Format (default)
```bash
gcgaap diff-snapshots -b before.json -a after.json > fix_report.txt
```

### JSON Format (for automation)
```bash
gcgaap diff-snapshots -b before.json -a after.json --format json -o changes.json
```

The JSON output can be parsed by scripts to track patterns over time.

## Tips

1. **Name snapshots meaningfully**:
   ```bash
   snapshot_before_fix_vics_cafe.json
   snapshot_after_fix_vics_cafe.json
   snapshot_before_bill_run_2026-02-11.json
   ```

2. **Keep a snapshot history** for your utility runs to detect regression patterns

3. **Use with version control** - commit snapshots to track when bugs were introduced

4. **Automate testing**:
   ```bash
   # Test your utility
   gcgaap snapshot -f test.gnucash -o before.json
   python your_bill_utility.py  # Run your utility
   gcgaap snapshot -f test.gnucash -o after.json
   gcgaap diff-snapshots -b before.json -a after.json
   # Check exit code - non-zero if transactions were broken
   ```

## Example: Finding What "Unpost and Repost" Does

You said you fixed a transaction by unposting and reposting but don't know what changed. Now you can find out:

```bash
# Before fix
gcgaap snapshot -f book.gnucash -o before_unpost.json

# (Unpost and repost the transaction in GnuCash)

# After fix
gcgaap snapshot -f book.gnucash -o after_unpost.json

# See the difference
gcgaap diff-snapshots -b before_unpost.json -a after_unpost.json
```

The output will show **exactly** which fields changed during the unpost/repost operation.
