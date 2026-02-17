# Shared Credit Card Guide

## The Problem

When you use a credit card for expenses that belong to different entities (personal and multiple businesses), it creates accounting imbalances:

- The **credit card liability** is mapped to one entity (usually personal)
- The **expenses** are mapped to different entities (various businesses)
- This violates the accounting equation: Assets = Liabilities + Equity

**Result:** Your entity balance sheets won't balance, and reports will be inaccurate.

## The Solution: Inter-Entity Accounts

To properly track shared credit card transactions, you need to use **inter-entity equity accounts** that track money owed between entities.

### Step 1: Set Up Inter-Entity Accounts

Create these equity accounts in your GnuCash book:

#### For Each Business Entity:
```
Equity:Due to Personal      (tracks money owed to personal entity)
Equity:Due from Personal    (tracks money owed by personal entity)
```

#### For Personal Entity:
```
Equity:Due from [Business Name]  (for each business - tracks money owed by that business)
Equity:Due to [Business Name]    (for each business - tracks money owed to that business)
```

**Example Structure:**
```
Equity
  ├── Due to Personal
  ├── Due from Personal
  ├── Due from Storz Amusements
  ├── Due to Storz Amusements
  ├── Due from Storz Cash
  └── Due to Storz Cash
```

### Step 2: Map Inter-Entity Accounts to Entities

Update your `entity_account_map.json`:

- "Due to Personal" accounts → Map to the **business entity**
- "Due from [Business]" accounts → Map to **personal entity**
- "Due from Personal" accounts → Map to the **business entity**
- "Due to [Business]" accounts → Map to **personal entity**

**Why:** These accounts act as bridges between entities, tracking the flow of value.

### Step 3: Recording Transactions

#### Scenario A: Business Expense Paid with Personal Credit Card

**Traditional (WRONG - causes imbalance):**
```
Date: 2026-02-10
Description: Office supplies for Storz Amusements
  Expenses:Storz Amusements:Office Supplies    $100.00  [→ Business entity]
  Liabilities:Personal:AmEx Card              -$100.00  [→ Personal entity]
```
❌ This splits the transaction across entities, causing imbalance.

**Correct Method - Use Inter-Entity Accounts:**

**Transaction 1: Record the business expense**
```
Date: 2026-02-10
Description: Office supplies for Storz Amusements
  Expenses:Storz Amusements:Office Supplies    $100.00  [→ Business entity]
  Equity:Due to Personal                      -$100.00  [→ Business entity]
```
✓ This transaction stays within the business entity.

**Transaction 2: Record personal credit card payment**
```
Date: 2026-02-10
Description: Credit card charge - office supplies
  Equity:Due from Storz Amusements             $100.00  [→ Personal entity]
  Liabilities:Personal:AmEx Card              -$100.00  [→ Personal entity]
```
✓ This transaction stays within the personal entity.

**Net result:** 
- Business shows $100 expense and $100 owed to Personal
- Personal shows $100 credit card liability and $100 owed from Business
- Both entities balance correctly
- The "Due to/from" accounts track the inter-entity debt

#### Scenario B: Personal Expense Paid with Personal Credit Card

**No special handling needed:**
```
Date: 2026-02-10
Description: Groceries
  Expenses:Personal:Groceries                  $150.00  [→ Personal entity]
  Liabilities:Personal:AmEx Card              -$150.00  [→ Personal entity]
```
✓ Transaction stays within personal entity - no problem.

#### Scenario C: Settling Inter-Entity Balances

When the business pays back the personal entity:

```
Date: 2026-02-15
Description: Transfer to settle inter-entity balance
  Assets:Storz Amusements:Checking Account   -$1,000.00  [→ Business entity]
  Equity:Due to Personal                      $1,000.00  [→ Business entity]

  Assets:Personal:Checking Account            $1,000.00  [→ Personal entity]
  Equity:Due from Storz Amusements           -$1,000.00  [→ Personal entity]
```

This is recorded as two separate transactions in GnuCash, but represents the same physical transfer.

## Alternative Approach: Split Credit Card Accounts

Instead of using inter-entity equity accounts, you can create separate sub-accounts for each credit card:

```
Liabilities:Credit Cards:American Express
  ├── AmEx - Personal Charges     [→ Map to personal entity]
  ├── AmEx - Storz Amusements     [→ Map to Storz Amusements entity]
  └── AmEx - Storz Cash           [→ Map to Storz Cash entity]
```

Then record transactions in the appropriate sub-account:

```
Date: 2026-02-10
Description: Office supplies
  Expenses:Storz Amusements:Office Supplies            $100.00  [→ Business entity]
  Liabilities:Credit Cards:AmEx - Storz Amusements    -$100.00  [→ Business entity]
```

**Pros:**
- Simpler to understand
- Fewer transaction entries
- Each charge goes directly to the correct entity

**Cons:**
- Doesn't match the actual credit card bill structure
- When you pay the credit card, you need to split the payment across multiple accounts
- Less flexible if you need to move charges between entities later

## Using the GCGAAP Tools

### Identify Cross-Entity Problems

Run the cross-entity analysis command:

```bash
gcgaap cross-entity -f yourbook.gnucash -e entity_account_map.json
```

This will show:
- All transactions spanning multiple entities
- Which entities have imbalances
- How much each entity owes/is owed
- Specific recommendations for balancing entries

### Example Output:

```
CROSS-ENTITY TRANSACTION ANALYSIS
================================================================================

Total Cross-Entity Transactions: 47

ENTITY IMBALANCES FROM CROSS-ENTITY TRANSACTIONS
--------------------------------------------------------------------------------
Entity                         Imbalance          Status
--------------------------------------------------------------------------------
storz_amusements                 2,345.67          Owes others
personal                        -2,345.67          Owed by others

INTER-ENTITY BALANCES (Who Owes Whom)
--------------------------------------------------------------------------------
From Entity               To Entity                 Amount     Txns
--------------------------------------------------------------------------------
storz_amusements          personal                2,345.67       47
```

### Fix the Imbalances

The tool will provide specific recommendations like:

```
storz_amusements owes personal: $2,345.67
  Transaction:
  - Debit:  Equity:Due to personal (in storz_amusements) $2,345.67
  - Credit: Equity:Due from storz_amusements (in personal) $2,345.67
```

Create this transaction in GnuCash to balance the entities.

## Best Practices

1. **Decide on One Approach**: Choose either inter-entity accounts OR split credit card accounts, but be consistent.

2. **Regular Reconciliation**: Run `gcgaap cross-entity` monthly to identify and fix imbalances.

3. **Document Your Method**: Note in your GnuCash file which approach you're using for future reference.

4. **Use Automation**: If you frequently split transactions, consider using GnuCash's transaction templates.

5. **Review Before Reports**: Always run `gcgaap violations` before generating financial reports to ensure data integrity.

## Troubleshooting

### Q: My balance sheet still doesn't balance after following this guide

A: Run these commands to diagnose:
```bash
gcgaap violations -f yourbook.gnucash -e entity_account_map.json
gcgaap cross-entity -f yourbook.gnucash -e entity_account_map.json
```

Check for:
- Unmapped accounts
- Imbalanced transactions
- Missing inter-entity balancing entries

### Q: Do I need to create balancing entries for every single transaction?

A: Yes, if you're using the inter-entity account method. Each time you charge a business expense to a personal credit card, you need two entries:
1. The expense in the business entity with credit to "Due to Personal"
2. The matching entry in personal entity

Alternatively, use the split credit card account method for simpler entry.

### Q: Can I fix past transactions all at once?

A: Yes! Run `gcgaap cross-entity` to see the total imbalance, then create one large balancing entry for historical transactions. Going forward, record new transactions properly.

### Q: What if I have multiple credit cards?

A: The same principles apply to all credit cards. Create inter-entity accounts for each shared payment method, or use the split account approach.

## See Also

- [VIOLATIONS_GUIDE.md](VIOLATIONS_GUIDE.md) - Understanding data quality issues
- [QUICKSTART.md](QUICKSTART.md) - Getting started with GCGAAP
- [Entity Mapping Documentation](README.md#entity-mapping) - How entity mapping works
