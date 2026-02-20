# Balance-Xacts Command Usage Guide

**New Feature:** Automatically balance cross-entity transactions by adding inter-entity equity account splits.

## Overview

The `balance-xacts` command identifies 2-split cross-entity transactions and automatically adds two balancing splits using your inter-entity equity accounts (Money In/Out). This eliminates the need to manually create balancing entries for each cross-entity transaction.

## Prerequisites

Before using this command, ensure:

1. **Entity Mapping is Complete**
   - All accounts are properly mapped to entities in `entity_account_map.json`
   - Run `gcgaap entity-scan` to check for unmapped accounts

2. **Inter-Entity Equity Accounts Exist**
   - Each entity must have two equity accounts:
     - `Equity:<EntityName>:Money In (<OtherEntity>)`
     - `Equity:<EntityName>:Money Out (<OtherEntity>)`
   
   For example:
   ```
   Equity:Personal:Money In (Storz Cash)
   Equity:Personal:Money Out (Storz Cash)
   Equity:Storz Cash:Money In (Personal)
   Equity:Storz Cash:Money Out (Personal)
   ```

3. **These Equity Accounts are Mapped**
   - The equity accounts must be mapped to their respective entities in `entity_account_map.json`

## Basic Usage

### Dry Run (Preview Only)

Always start with a dry run to preview what changes will be made:

```bash
gcgaap balance-xacts -f yourbook.gnucash -e entity_account_map.json --dry-run
```

This will:
- Show you which transactions can be fixed
- Group them by entity pair and expense account
- Display each group for approval
- **NOT make any actual changes**

### Actual Execution

Once you're comfortable with the preview, run without `--dry-run`:

```bash
gcgaap balance-xacts -f yourbook.gnucash -e entity_account_map.json
```

This will:
- Create an automatic backup (e.g., `yourbook.backup_20260219_143022.gnucash`)
- Present each group of transactions for approval
- Add balancing splits to approved transactions
- Save changes after each approved group

## Advanced Usage

### Filter by Entity

Process only transactions involving a specific entity:

```bash
gcgaap balance-xacts -f yourbook.gnucash -e entity_account_map.json --entity Personal
```

### Filter by Date Range

Process only transactions within a specific date range:

```bash
gcgaap balance-xacts -f yourbook.gnucash -e entity_account_map.json \
  --date-from 2025-01-01 \
  --date-to 2025-12-31
```

### Combine Filters

```bash
gcgaap balance-xacts -f yourbook.gnucash -e entity_account_map.json \
  --entity "Storz Cash" \
  --date-from 2025-01-01 \
  --dry-run
```

## How It Works

### 1. Transaction Identification

The command finds transactions that:
- Have exactly 2 splits
- Span exactly 2 different entities
- Have an imbalance (not zero after entity split)

### 2. Grouping

Similar transactions are grouped together:
- By entity pair (e.g., Personal ↔ Storz Cash)
- By expense account (e.g., all "Office Supplies" together)
- Maximum 9 transactions per group

### 3. Interactive Approval

For each group, you'll see:
```
Group: Personal ↔ Storz Cash / Office Supplies
Transactions: 5
--------------------------------------------------------------------------------
Date          Amount  Opposing Entity               
--------------------------------------------------------------------------------
2025-01-15  $  123.45  Storz Cash                    
2025-02-03  $   45.67  Storz Cash                    
2025-03-12  $   89.01  Storz Cash                    
...
--------------------------------------------------------------------------------

Balance these 5 transaction(s)? (1/3) [y/N]:
```

### 4. Balancing Splits Added

For each approved transaction, two splits are added:

**Example:** $100 expense paid by Personal for Storz Cash business

Before (imbalanced):
```
Split 1: Expenses:Storz Cash:Office Supplies    $100.00 (Storz Cash entity)
Split 2: Liabilities:Personal:AmEx Card        -$100.00 (Personal entity)
```

After (balanced):
```
Split 1: Expenses:Storz Cash:Office Supplies           $100.00 (Storz Cash entity)
Split 2: Liabilities:Personal:AmEx Card               -$100.00 (Personal entity)
Split 3: Equity:Storz Cash:Money Out (Personal)       -$100.00 (Storz Cash entity)
        Memo: "Inter-entity balance: Personal - Made by gcgaap"
Split 4: Equity:Personal:Money In (Storz Cash)         $100.00 (Personal entity)
        Memo: "Inter-entity balance: Storz Cash - Made by gcgaap"
```

Now the transaction balances:
- Storz Cash entity: $100.00 - $100.00 = $0.00 ✓
- Personal entity: -$100.00 + $100.00 = $0.00 ✓

## Safety Features

### Automatic Backup

Before making any changes, a timestamped backup is created:
```
yourbook.backup_20260219_143022.gnucash
```

If something goes wrong, you can restore from this backup.

### Group-by-Group Processing

Changes are saved after each approved group. If you encounter an issue:
- Already-processed groups are saved
- Not-yet-processed groups remain unchanged
- You can fix the issue and re-run the command

### Dry Run Mode

Always available to preview changes without risk.

## Common Issues

### Error: Missing equity accounts

```
[ERROR] Missing required equity accounts:
  - Personal: Missing 'Money Out' account
  - Storz Cash: Missing 'Money In' account
```

**Solution:** Create the missing equity accounts in GnuCash:
1. Open GnuCash
2. Create accounts under Equity for each entity
3. Follow the naming pattern: `Money In (<OtherEntity>)` and `Money Out (<OtherEntity>)`
4. Map them to entities in `entity_account_map.json`

### Error: Entity not found

```
Error: Entity 'Storz' not found in entity map.
Available entities: Personal, Storz Cash, Storz Amusements, Storz Property
```

**Solution:** Use the exact entity key from your entity mapping. Run `gcgaap entity-scan` to see available entities.

### No fixable transactions found

```
No fixable transactions found!
(Looking for 2-split cross-entity transactions with imbalances)
```

**Possible reasons:**
1. All cross-entity transactions already have balancing splits
2. Your transactions have more than 2 splits (not currently supported)
3. Date or entity filters excluded all transactions

## Verification

After running `balance-xacts`, verify the results:

```bash
# Check cross-entity balances
gcgaap cross-entity -f yourbook.gnucash -e entity_account_map.json

# Run full validation
gcgaap validate -f yourbook.gnucash -e entity_account_map.json --strict
```

You should see significantly reduced or zero imbalances between entities.

## Workflow Example

Complete workflow for balancing historical transactions:

```bash
# 1. Check current state
gcgaap cross-entity -f book.gnucash -e entity_account_map.json

# 2. Preview what will be fixed (dry run)
gcgaap balance-xacts -f book.gnucash -e entity_account_map.json --dry-run

# 3. Fix 2025 transactions first (testing)
gcgaap balance-xacts -f book.gnucash -e entity_account_map.json \
  --date-from 2025-01-01 --date-to 2025-12-31

# 4. Verify results
gcgaap cross-entity -f book.gnucash -e entity_account_map.json

# 5. If good, fix remaining transactions
gcgaap balance-xacts -f book.gnucash -e entity_account_map.json \
  --date-to 2024-12-31

# 6. Final verification
gcgaap cross-entity -f book.gnucash -e entity_account_map.json
gcgaap validate -f book.gnucash -e entity_account_map.json --strict
```

## Limitations

Current version only handles:
- Transactions with exactly 2 splits
- Transactions spanning exactly 2 entities
- Requires pre-existing equity accounts

**Not supported (yet):**
- Transactions with 3+ splits
- Multi-entity transactions (3+ entities)
- Automatic creation of equity accounts

For complex transactions, you'll need to manually create balancing entries following the guidance in [BALANCING_TRANSACTIONS.md](BALANCING_TRANSACTIONS.md).

## See Also

- [BALANCING_TRANSACTIONS.md](BALANCING_TRANSACTIONS.md) - Manual balancing guide
- [SHARED_CREDIT_CARD_GUIDE.md](SHARED_CREDIT_CARD_GUIDE.md) - Shared account best practices
- [README.md](README.md) - Entity mapping documentation
