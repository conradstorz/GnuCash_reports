# Violations Report - Data Quality Guide

## What is the Violations Report?

The violations report is a comprehensive data quality analysis tool that identifies and categorizes all problems in your GnuCash database. It's designed to help you understand what needs to be fixed before you can generate accurate financial reports.

## When to Use It

Run the violations report when:

1. **Starting out** - First step in understanding your data quality
2. **Before generating reports** - Ensure data integrity
3. **After making changes** - Verify your fixes worked
4. **Troubleshooting** - Understand why reports aren't working

## How to Run It

```bash
# Basic usage
gcgaap violations -f path/to/yourbook.gnucash

# With specific date
gcgaap violations -f path/to/yourbook.gnucash --as-of 2026-12-31

# With custom entity map
gcgaap violations -f path/to/yourbook.gnucash -e custom-entities.json
```

## Understanding the Report

### Summary Section

```
SUMMARY
--------------------------------------------------------------------------------
Total Accounts Analyzed:     166
Total Transactions Analyzed: 3208
Entities Analyzed:           0

Critical Violations:         0
Errors:                      166
Warnings:                    1
```

- **Accounts/Transactions Analyzed**: Shows scope of analysis
- **Entities Analyzed**: Number of entities with account mappings
- **Critical/Errors/Warnings**: Severity breakdown of issues

### Entity Balance Summary

Shows accounting equation status for each entity:

```
Entity                         Accounts    Assets       Liab        Equity     Balance
--------------------------------------------------------------------------------
Personal                              45    125,000     -50,000     -75,000    ✓ OK
Alpha LLC                             23     50,000     -20,000     -29,950    ✗ FAIL
```

- ✓ OK = Entity balances (Assets = Liabilities + Equity)
- ✗ FAIL = Entity doesn't balance (accounting equation violated)

### Violation Categories

#### 1. IMBALANCED_TRANSACTION (Critical)

**What it means**: A transaction's splits don't sum to zero

**Example**:
```
[CRITICAL] Transaction does not balance (imbalance: 0.12)
Item: Grocery purchase
ID: abc123...
post_date: 2026-01-15
imbalance_amount: 0.12
```

**Why it matters**: This violates double-entry bookkeeping fundamentals. Every transaction MUST balance.

**How to fix**: 
- Open GnuCash and find the transaction by description or date
- Edit the transaction to ensure all splits sum to zero
- Common causes: data entry errors, rounding issues, incomplete imports

#### 2. UNMAPPED_ACCOUNT (Error)

**What it means**: An account has no entity assignment

**Example**:
```
[ERROR] Account has no entity mapping
Item: Assets:Business:Alpha LLC:Checking
ID: def456...
account_type: BANK
commodity: USD
```

**Why it matters**: Without entity mapping, you can't generate entity-specific reports

**How to fix**:
- Run `gcgaap entity-infer` to get mapping suggestions
- Edit `entity-map.json` to add the account
- Use either GUID-based mapping or regex patterns

#### 3. ENTITY_IMBALANCE (Error)

**What it means**: An entity's accounting equation doesn't balance

**Example**:
```
[ERROR] Entity accounting equation does not balance (imbalance: 50.00)
Item: Alpha LLC
total_assets: 50000.00
total_liabilities: -20000.00
total_equity: -29950.00
imbalance: 50.00
account_count: 23
```

**Why it matters**: Each entity must satisfy Assets = Liabilities + Equity

**How to fix**:
- Usually caused by unmapped accounts or imbalanced transactions
- First fix any CRITICAL violations
- Then ensure all accounts are mapped
- Check if accounts are assigned to correct entities

#### 4. IMBALANCE_ACCOUNT_NONZERO (Warning)

**What it means**: An Imbalance or Orphan account has a non-zero balance

**Example**:
```
[WARNING] Imbalance/Orphan account has non-zero balance (-2852.75)
Item: Imbalance-USD
ID: ghi789...
balance: -2852.75
account_type: BANK
```

**Why it matters**: These accounts should typically be empty. Non-zero balances indicate unbalanced transactions that GnuCash automatically corrected.

**How to fix**:
- Identify the transactions affecting this account
- Find the original imbalanced transaction
- Correct the transaction properly
- The Imbalance account should zero out

#### 5. PLACEHOLDER_HAS_TRANSACTIONS (Error)

**What it means**: A placeholder account contains one or more transactions

**Example**:
```
[ERROR] Placeholder account contains transactions (2 transaction(s) found).
        Placeholder accounts must not contain any transactions.
Item: Assets root:Current Assets root
ID: abc123...
account_type: ASSET
transaction_count: 2
```

**Why it matters**: Placeholder accounts (also called "structural accounts") are organizational containers in GnuCash. They are marked as placeholders specifically to prevent transactions from being posted directly to them. Having transactions in a placeholder account violates GnuCash's design principles.

**How to fix**:
- Open GnuCash and locate the placeholder account
- Review the Account Properties to verify it's marked as a placeholder
- Find the transactions that were incorrectly posted to this account
- Move (reclassify) those transactions to proper child accounts
- Placeholder accounts should only contain sub-accounts, never transactions

**Note**: The entity mapper automatically labels placeholder accounts as `placeholder_only_acct` entity, distinguishing them from regular unmapped accounts.

#### 6. UNKNOWN_ACCOUNT_TYPE (Warning)

**What it means**: An account has an unrecognized type

**Example**:
```
[WARNING] Account has unknown type: TRADING
Item: Trading:CURRENCY:USD
account_type: TRADING
entity_key: personal
```

**Why it matters**: May not be categorized correctly in reports

**How to fix**:
- Usually informational only
- May need to enhance the violations engine to handle this account type

## Recommendations Section

The report provides prioritized recommendations:

```
RECOMMENDATIONS
--------------------------------------------------------------------------------
1. FIX CRITICAL VIOLATIONS FIRST:
   - Imbalanced transactions indicate data integrity issues
   - These MUST be corrected in GnuCash before proceeding

2. MAP ALL ACCOUNTS TO ENTITIES:
   - 166 account(s) need entity mapping
   - Run: gcgaap entity-scan to see unmapped accounts
   - Run: gcgaap entity-infer to generate suggested mappings

3. RESOLVE ENTITY-LEVEL IMBALANCES:
   - Review entity balance summary above
   - Entity imbalances often result from:
     • Unmapped accounts
     • Imbalanced transactions
     • Incorrect entity assignments
```

## Exit Codes

The command exits with different codes based on severity:

- **0**: No errors (may have warnings)
- **1**: Errors found (unmapped accounts, entity imbalances)
- **2**: Critical violations found (imbalanced transactions)

Use these in scripts:

```bash
#!/bin/bash
gcgaap violations -f mybook.gnucash
EXIT_CODE=$?

if [ $EXIT_CODE -eq 2 ]; then
    echo "CRITICAL: Fix imbalanced transactions immediately!"
elif [ $EXIT_CODE -eq 1 ]; then
    echo "ERRORS: Fix mapping issues before reporting"
else
    echo "OK: Ready for report generation"
fi
```

## Workflow: From Violations to Clean Data

### Step 1: Initial Assessment

```bash
gcgaap violations -f mybook.gnucash > violations-initial.txt
```

Review the report to understand the scope of issues.

### Step 2: Fix Critical Issues

If you have imbalanced transactions:
1. Open GnuCash
2. Search for transactions by description from the report
3. Fix each transaction to balance
4. Save and re-run violations report

### Step 3: Map Accounts to Entities

```bash
# Get AI suggestions
gcgaap entity-infer -f mybook.gnucash -o entity-map.json

# Review and edit entity-map.json
# Then verify mappings
gcgaap entity-scan -f mybook.gnucash -e entity-map.json
```

### Step 4: Verify Clean

```bash
gcgaap violations -f mybook.gnucash -e entity-map.json
```

Should see:
```
[OK] No violations found - data quality is excellent!
```

### Step 5: Generate Reports

Now you're ready for strict validation and reporting:

```bash
gcgaap validate -f mybook.gnucash -e entity-map.json --strict
gcgaap balance-sheet -f mybook.gnucash -e entity-map.json --as-of 2026-12-31
```

## Tips and Best Practices

1. **Run violations first** - Before any other command, understand your data
2. **Fix in order** - Critical → Errors → Warnings
3. **Use dates strategically** - Run `--as-of` at year-end to see annual status
4. **Save reports** - Redirect output to files for comparison over time
5. **Automate checks** - Add to CI/CD or scheduled tasks
6. **Document fixes** - Keep notes on what you fixed and why

## Common Scenarios

### Scenario: All Accounts Unmapped

```
Errors: 166
UNMAPPED_ACCOUNT (166 violations)
```

**Solution**: Use `entity-infer` to bootstrap your entity map

### Scenario: Orphan Account with Balance

```
Warnings: 1
IMBALANCE_ACCOUNT_NONZERO (1 violation)
Imbalance-USD: -2852.75
```

**Solution**: 
1. In GnuCash, filter transactions by Imbalance-USD account
2. Find the imbalanced transaction(s)
3. Add the missing split or correct the amounts
4. The Imbalance account should go to $0

### Scenario: Entity Doesn't Balance

```
Entity Imbalance: 50.00
```

**Solution**:
1. Check if all entity's accounts are mapped
2. Verify accounts are assigned to correct entity
3. Check for imbalanced transactions affecting this entity
4. Review the entity balance detail in the report

## Advanced Usage

### Compare Before/After

```bash
# Before fixes
gcgaap violations -f mybook.gnucash > before.txt

# Make fixes in GnuCash...

# After fixes
gcgaap violations -f mybook.gnucash > after.txt

# Compare
diff before.txt after.txt
```

### Filter by Severity

```bash
# Show only critical issues
gcgaap violations -f mybook.gnucash | grep CRITICAL

# Count errors
gcgaap violations -f mybook.gnucash | grep "\[ERROR\]" | wc -l
```

### Monthly Data Quality Checks

```bash
#!/bin/bash
# monthly-quality-check.sh

BOOK="path/to/mybook.gnucash"
YEAR=$(date +%Y)
MONTH=$(date +%m)
DATE=$(date +%Y-%m-%d)

gcgaap violations -f "$BOOK" --as-of "$DATE" > "violations-$YEAR-$MONTH.txt"

# Email report if issues found
if [ $? -ne 0 ]; then
    mail -s "GnuCash Data Quality Issues - $DATE" admin@example.com < "violations-$YEAR-$MONTH.txt"
fi
```

## Summary

The violations report is your primary tool for ensuring data quality. It:

- **Identifies** all data quality issues comprehensively
- **Categorizes** by severity (critical/error/warning)
- **Explains** what each violation means and why it matters
- **Recommends** prioritized actions to fix issues
- **Validates** at transaction, account, and entity levels

Use it regularly to maintain clean, GAAP-compliant accounting data.
