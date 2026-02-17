# Balancing Transactions for Cross-Entity Imbalances

**Generated:** February 16, 2026
**Source:** Cross-Entity Transaction Analysis

## Summary of Imbalances

Based on the analysis of 680 cross-entity transactions:

| Entity | Net Imbalance | Status |
|--------|---------------|---------|
| Personal | +$62,423.51 | Owed by businesses |
| Storz Cash | -$52,469.63 | Owes personal |
| Storz Amusements | -$11,905.05 | Owes personal |
| Storz Property | +$1,951.17 | Owes personal |

**Net Check:** $62,423.51 - $52,469.63 - $11,905.05 + $1,951.17 = $0.00 ✓

## Step 1: Create Inter-Entity Equity Accounts

First, create these accounts in GnuCash if they don't already exist:

### For Storz Cash (Business Entity):
```
Equity:Storz Cash:Due to Personal
Equity:Storz Cash:Due from Personal
```

### For Storz Amusements (Business Entity):
```
Equity:Storz Amusements:Due to Personal
Equity:Storz Amusements:Due from Personal
```

### For Storz Property (Business Entity):
```
Equity:Storz Property:Due to Personal
Equity:Storz Property:Due from Personal
```

### For Personal Entity:
```
Equity:Personal:Due from Storz Cash
Equity:Personal:Due to Storz Cash
Equity:Personal:Due from Storz Amusements
Equity:Personal:Due to Storz Amusements
Equity:Personal:Due from Storz Property
Equity:Personal:Due to Storz Property
```

**Important:** Map these accounts to entities in your `entity_account_map.json`:
- "Due to Personal" accounts → Map to the **business** entity
- "Due from [Business]" accounts → Map to **personal** entity
- "Due from Personal" accounts → Map to the **business** entity
- "Due to [Business]" accounts → Map to **personal** entity

## Step 2: Enter Balancing Transactions

Enter these transactions in GnuCash to balance the inter-entity accounts:

---

### Transaction 1: Balance Storz Cash ↔ Personal

**Date:** 2026-02-16 (or your preferred date)  
**Description:** Balancing entry - Historical cross-entity transactions for Storz Cash

**Net:** Storz Cash owes Personal $52,469.63

#### Split 1 (in Storz Cash entity):
```
Account:  Equity:Storz Cash:Due to Personal
Debit:    $52,469.63
Credit:   
```

#### Split 2 (in Personal entity):
```
Account:  Equity:Personal:Due from Storz Cash
Debit:    $52,469.63
Credit:   
```

**GnuCash Entry Format:**
```
Date: 2026-02-16
Description: Balance Storz Cash inter-entity account
Splits:
  1. Equity:Storz Cash:Due to Personal         | Increase | $52,469.63
  2. Equity:Personal:Due from Storz Cash       | Increase | $52,469.63
```

---

### Transaction 2: Balance Storz Amusements ↔ Personal

**Date:** 2026-02-16  
**Description:** Balancing entry - Historical cross-entity transactions for Storz Amusements

**Net:** Storz Amusements owes Personal $11,905.05

#### Split 1 (in Storz Amusements entity):
```
Account:  Equity:Storz Amusements:Due to Personal
Debit:    $11,905.05
Credit:   
```

#### Split 2 (in Personal entity):
```
Account:  Equity:Personal:Due from Storz Amusements
Debit:    $11,905.05
Credit:   
```

**GnuCash Entry Format:**
```
Date: 2026-02-16
Description: Balance Storz Amusements inter-entity account
Splits:
  1. Equity:Storz Amusements:Due to Personal   | Increase | $11,905.05
  2. Equity:Personal:Due from Storz Amusements | Increase | $11,905.05
```

---

### Transaction 3: Balance Storz Property ↔ Personal

**Date:** 2026-02-16  
**Description:** Balancing entry - Historical cross-entity transactions for Storz Property

**Net:** Personal owes Storz Property $1,951.17

#### Split 1 (in Personal entity):
```
Account:  Equity:Personal:Due to Storz Property
Debit:    $1,951.17
Credit:   
```

#### Split 2 (in Storz Property entity):
```
Account:  Equity:Storz Property:Due from Personal
Debit:    $1,951.17
Credit:   
```

**GnuCash Entry Format:**
```
Date: 2026-02-16
Description: Balance Storz Property inter-entity account
Splits:
  1. Equity:Personal:Due to Storz Property     | Increase | $1,951.17
  2. Equity:Storz Property:Due from Personal   | Increase | $1,951.17
```

---

## Step 3: Verify the Balancing

After entering these three transactions, run the cross-entity analysis again:

```bash
gcgaap cross-entity -f yourbook.gnucash -e entity_account_map.json
```

You should see:
- All entity imbalances reduced to near-zero (within a few cents for rounding)
- The inter-entity "Due to/from" accounts showing the correct balances

## Step 4: Understanding the Results

After these transactions:

### Personal Entity Balance Sheet will show:
- **Assets:** Due from Storz Cash: $52,469.63
- **Assets:** Due from Storz Amusements: $11,905.05
- **Liabilities:** Due to Storz Property: $1,951.17
- **Net:** Personal is owed $62,423.51 by the businesses

### Storz Cash Balance Sheet will show:
- **Liabilities:** Due to Personal: $52,469.63
- This represents expenses paid by personal funds that should be reimbursed

### Storz Amusements Balance Sheet will show:
- **Liabilities:** Due to Personal: $11,905.05
- This represents expenses paid by personal funds that should be reimbursed

### Storz Property Balance Sheet will show:
- **Assets:** Due from Personal: $1,951.17
- This represents income or benefits received by personal that should be paid back

## Step 5: Going Forward

Now that historical imbalances are fixed, record new shared credit card transactions correctly:

### When Recording a Business Expense on Personal Credit Card:

**Example:** $100 office supplies for Storz Amusements paid with personal AmEx

**Transaction 1:** Record the expense in the business
```
Date: [Transaction Date]
Description: Office supplies
Splits:
  1. Expenses:Storz Amusements:Office Supplies     | Increase | $100.00
  2. Equity:Storz Amusements:Due to Personal       | Increase | $100.00
```

**Transaction 2:** Record the credit card charge in personal
```
Date: [Transaction Date]
Description: Office supplies - Storz Amusements expense
Splits:
  1. Equity:Personal:Due from Storz Amusements     | Increase | $100.00
  2. Liabilities:Personal:AmEx Card                | Increase | $100.00
```

This keeps both entities balanced and properly tracks the inter-entity debt.

### When the Business Reimburses Personal:

```
Date: [Payment Date]
Description: Reimbursement to personal for expenses
Splits (in Storz Amusements):
  1. Assets:Storz Amusements:Checking              | Decrease | $500.00
  2. Equity:Storz Amusements:Due to Personal       | Decrease | $500.00

Splits (in Personal):
  1. Assets:Personal:Checking                      | Increase | $500.00
  2. Equity:Personal:Due from Storz Amusements     | Decrease | $500.00
```

## Troubleshooting

### Q: The amounts don't add up exactly

Run the violations report to check for other data quality issues:
```bash
gcgaap violations -f yourbook.gnucash -e entity_account_map.json
```

### Q: After entering these transactions, balances still don't match

Verify:
1. All inter-entity equity accounts are correctly mapped to entities
2. The account types are correct (Equity accounts)
3. All splits were entered with correct signs (increases vs. decreases)
4. Run the analysis again: `gcgaap cross-entity -f yourbook.gnucash -e entity_account_map.json`

### Q: Should I really enter three separate transactions?

Yes! In GnuCash, you cannot have a single transaction with splits from different entities. Each inter-entity transfer requires mirror transactions in both entities.

However, you can think of them as two entries per relationship:
- Transaction 1 & 2 together represent: Storz Cash ↔ Personal settlement
- Transaction 3 & 4 together represent: Storz Amusements ↔ Personal settlement  
- Transaction 5 & 6 together represent: Storz Property ↔ Personal settlement

The transactions are numbered 1-3 above for clarity, but each one actually contains splits from both entities.

## Additional Notes

### Why Equity Accounts?

Inter-entity balances are tracked in Equity because:
- They don't represent external liabilities (not true debt)
- They don't represent external assets (not true receivables)
- They represent owner's equity adjustments between related entities
- They maintain the accounting equation: Assets = Liabilities + Equity

### Tax Implications

Consult with your accountant about:
- Whether these inter-entity transfers need to be formally documented
- If interest should be charged on inter-entity balances
- How to properly document loans vs. capital contributions
- State-specific requirements for multi-entity bookkeeping

### Future Maintenance

Run the cross-entity analysis monthly:
```bash
gcgaap cross-entity -f yourbook.gnucash -e entity_account_map.json
```

Small imbalances ($5-$10) are normal from ongoing transactions. Larger imbalances indicate you're not recording shared expenses correctly.

## See Also

- [SHARED_CREDIT_CARD_GUIDE.md](SHARED_CREDIT_CARD_GUIDE.md) - Comprehensive guide to shared accounts
- [VIOLATIONS_GUIDE.md](VIOLATIONS_GUIDE.md) - Understanding data quality issues
- [README.md](README.md) - Entity mapping documentation
