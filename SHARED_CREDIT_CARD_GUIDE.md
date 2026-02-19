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

#### For Each Entity (Including Personal):
```
Equity:Inter Entity xfers:[Entity Name]:Money In ([Entity Name])   (tracks money owed TO this entity by others)
Equity:Inter Entity xfers:[Entity Name]:Money Out ([Entity Name])  (tracks money owed BY this entity to others)
```

**Example Structure:**
```
Equity:Inter Entity xfers
  ├── Personal
  │   ├── Money In (Personal)    (others owe money to Personal)
  │   └── Money Out (Personal)   (Personal owes money to others)
  ├── Storz Amusements
  │   ├── Money In (Storz Amusements)
  │   └── Money Out (Storz Amusements)
  └── Storz Cash
      ├── Money In (Storz Cash)
      └── Money Out (Storz Cash)
```

**Interpretation:**
- **Money Out** = This entity owes money (like a liability)
- **Money In** = This entity is owed money (like a receivable)

### Step 2: Map Inter-Entity Accounts to Entities

Update your `entity_account_map.json`:

- "Money In (Personal)" → Map to **personal** entity
- "Money Out (Personal)" → Map to **personal** entity
- "Money In (Storz Amusements)" → Map to **storz_amusements** entity
- "Money Out (Storz Amusements)" → Map to **storz_amusements** entity
- (Continue for all entities...)

**Principle:** Each entity owns its own "Money In" and "Money Out" accounts. This makes entity mapping straightforward and intuitive.

**Why:** These accounts act as bridges between entities, tracking inter-entity obligations (who owes whom).

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

**✅ RECOMMENDED: Single Transaction with Balancing Splits**

Record all splits in ONE transaction to keep related entries together:

```
Date: 2026-02-10
Description: Office supplies for Storz Amusements
  Expenses:Storz Amusements:Office Supplies        $100.00  [→ Business entity]
  Equity:Money Out (Storz Amusements)             -$100.00  [→ Business entity]
  Equity:Money In (Personal)                       $100.00  [→ Personal entity]
  Liabilities:Personal:AmEx Card                  -$100.00  [→ Personal entity]
```

**Why this works:**
- Transaction still balances to $0 (required by GnuCash)
- Business entity sees: $100 expense, $100 going out (owed to Personal)
- Personal entity sees: $100 coming in (owed by Business), $100 credit card liability
- All related information stays together in one transaction
- **Preserves your import and reconciliation workflow** - credit card stays as single account
- Easy to see which expense relates to which balancing entry

**Alternative: Separate Transactions (More Work)**

You can also split this into two separate transactions:

**Transaction 1:**
```
Date: 2026-02-10
Description: Office supplies for Storz Amusements
  Expenses:Storz Amusements:Office Supplies    $100.00  [→ Business entity]
  Equity:Money Out (Storz Amusements)         -$100.00  [→ Business entity]
```

**Transaction 2:**
```
Date: 2026-02-10
Description: Credit card charge - office supplies
  Equity:Money In (Personal)                   $100.00  [→ Personal entity]
  Liabilities:Personal:AmEx Card              -$100.00  [→ Personal entity]
```

This achieves the same result but requires more data entry and splits related information across multiple transactions.

#### Scenario B: Personal Expense Paid with Personal Credit Card

**No special handling needed:**
```
Date: 2026-02-10
Description: Groceries
  Expenses:Personal:Groceries                  $150.00  [→ Personal entity]
  Liabilities:Personal:AmEx Card              -$150.00  [→ Personal entity]
```
✓ Transaction stays within personal entity - no inter-entity balancing required.

#### Scenario C: Settling Inter-Entity Balances

When the business pays back the personal entity, record the transfer:

**Single transaction with all splits:**
```
Date: 2026-02-15
Description: Transfer to settle inter-entity balance
  Assets:Storz Amusements:Checking Account     -$1,000.00  [→ Business entity]
  Equity:Money Out (Storz Amusements)           $1,000.00  [→ Business entity]
  Equity:Money In (Personal)                   -$1,000.00  [→ Personal entity]
  Assets:Personal:Checking Account              $1,000.00  [→ Personal entity]
```

This reduces the inter-entity debt by $1,000.

## Approach Comparison

| Factor | Single Account + Balancing Splits | Split Sub-Accounts |
|--------|-----------------------------------|--------------------|
| **Credit Card Import** | ✅ Works normally - import to single account | ❌ Must manually route each import to correct sub-account |
| **Monthly Reconciliation** | ✅ One account vs one statement | ❌ Reconcile 3+ sub-accounts against one unified statement |
| **Transaction Entry** | ⚠️ Requires 4 splits per cross-entity charge | ✅ Only 2 splits needed |
| **Payment Processing** | ✅ Pay from personal checking normally | ❌ Complex - must allocate payment across sub-accounts |
| **Statement Matching** | ✅ Matches bank's unified view | ❌ Must mentally split unified statement |
| **Data Entry Complexity** | ⚠️ Must remember balancing entries | ✅ Direct entry to entity-specific account |
| **Historical Migration** | ✅ Only need balancing entries for past | ❌ Must re-categorize all historical transactions |
| **Carrying Balances** | ✅ Interest/fees recorded normally | ❌ Must allocate interest/fees across sub-accounts |
| **GnuCash Enforcement** | ❌ Won't warn if you forget balancing | ✅ Account structure enforces split |
| **GCGAAP Detection** | ✅ Reports missing balancing entries | ✅ No detection needed |

**Recommendation:** Use the **single account with balancing splits** approach. The extra data entry overhead is worth it to preserve clean import/reconcile workflow.

---

## ❌ Not Recommended: Split Credit Card Sub-Accounts

Some guides recommend splitting your credit card into entity-specific sub-accounts:

```
Liabilities:Credit Cards:American Express
  ├── AmEx - Personal Charges     [→ Map to personal entity]
  ├── AmEx - Storz Amusements     [→ Map to Storz Amusements entity]
  └── AmEx - Storz Cash           [→ Map to Storz Cash entity]
```

**Why This Doesn't Work Well:**

1. **Import Nightmare**: Credit card downloads (CSV/OFX) come as a single file with all charges mixed together. You'd need to:
   - Import all transactions to a temporary account
   - Manually categorize each one to the correct sub-account
   - Completely breaks automatic import workflow

2. **Reconciliation Hell**: The bank sends ONE statement with ONE balance showing all transactions mixed together. You'd need to:
   - Reconcile 3+ separate GnuCash sub-accounts against a single unified statement
   - Manually check that sub-account balances sum to the statement total
   - Track which statement lines correspond to which sub-account

3. **Payment Complications**: When you pay the credit card bill from your personal checking account:
   - Which sub-account gets reduced?
   - Do you split the payment proportionally across all sub-accounts?
   - Does the business reimburse you? How is that recorded?
   - The payment transaction becomes extremely complex

4. **Statement Mismatch**: Paper/PDF statements don't show entity breakdowns, so you're constantly cross-referencing between the bank's unified view and your split view.

5. **Migration Pain**: Converting existing data requires re-categorizing potentially thousands of historical transactions.

**Verdict:** This approach trades workflow simplicity for theoretical organization, but creates massive practical problems. Stick with the single account + balancing entries method.

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
  - Debit:  Equity:Money Out (Storz Amusements) $2,345.67  [→ Business entity]
  - Credit: Equity:Money In (Personal)          $2,345.67  [→ Personal entity]
```

Create this balancing transaction in GnuCash.

## Best Practices

1. **Use Single Account with Balancing Splits**: Keep your credit card as a single unified account for clean import/reconcile workflow.

2. **Add Balancing Splits Immediately**: When entering a cross-entity transaction, add the balancing "Money In/Out" splits right away. Don't wait!

3. **Create Transaction Templates**: In GnuCash, create templates for common cross-entity transactions (e.g., "Business Expense on Personal Card") to speed up data entry.

4. **Regular Validation**: Run `gcgaap cross-entity` monthly to catch any missed balancing entries.

5. **Fix Imbalances Promptly**: If the report shows imbalances, create the recommended balancing transactions immediately.

6. **Review Before Reports**: Always run `gcgaap violations` before generating financial reports to ensure data integrity.

7. **Note in Descriptions**: Include entity name in transaction descriptions (e.g., "Office supplies for Storz Amusements") to make reviewing easier.

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

A: Yes, every cross-entity transaction needs balancing splits. But you can add them all in the SAME transaction:
```
Expenses:Business:Office Supplies         $100.00  [→ Business]
Equity:Money Out (Business)              -$100.00  [→ Business]
Equity:Money In (Personal)                $100.00  [→ Personal]
Liabilities:Personal:AmEx                -$100.00  [→ Personal]
```

This keeps everything together and maintains your clean import/reconcile workflow.

### Q: Can I fix past transactions all at once?

A: Yes! Run `gcgaap cross-entity` to see the total imbalance, then create one large balancing entry for historical transactions. Going forward, record new transactions properly.

### Q: What if I have multiple credit cards?

A: The same principles apply to all credit cards. Create inter-entity accounts for each shared payment method, or use the split account approach.

## See Also

- [VIOLATIONS_GUIDE.md](VIOLATIONS_GUIDE.md) - Understanding data quality issues
- [QUICKSTART.md](QUICKSTART.md) - Getting started with GCGAAP
- [Entity Mapping Documentation](README.md#entity-mapping) - How entity mapping works
