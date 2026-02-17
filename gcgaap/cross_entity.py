"""
Cross-entity transaction analysis for GCGAAP.

Provides tools to identify and analyze transactions that span multiple entities,
which is common when:
- Shared credit cards are used for multiple businesses/personal expenses
- One entity pays expenses on behalf of another
- Inter-entity transfers need to be tracked

This module helps identify imbalances caused by cross-entity transactions and
provides guidance on creating proper inter-entity balancing entries.
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional

from .entity_map import EntityMap
from .gnucash_access import GnuCashBook, GCTransaction, parse_date

logger = logging.getLogger(__name__)


@dataclass
class CrossEntityTransaction:
    """
    Represents a transaction with splits across multiple entities.
    
    Attributes:
        transaction: The GnuCash transaction object.
        entities_involved: Set of entity keys involved in this transaction.
        entity_amounts: Mapping of entity key to net amount (negative = credit, positive = debit).
        description: Transaction description.
        post_date: Transaction date.
    """
    
    transaction: GCTransaction
    entities_involved: set[str]
    entity_amounts: dict[str, Decimal]
    description: str
    post_date: date
    
    def is_balanced_per_entity(self, tolerance: float = 0.01) -> bool:
        """Check if all entity amounts sum to zero."""
        total = sum(self.entity_amounts.values())
        return abs(float(total)) <= tolerance
    
    def get_imbalance_by_entity(self) -> dict[str, Decimal]:
        """
        Get the imbalance contribution for each entity.
        
        A positive value means the entity has a debit imbalance (owes other entities).
        A negative value means the entity has a credit imbalance (is owed by other entities).
        """
        return self.entity_amounts.copy()


@dataclass
class InterEntityBalance:
    """
    Tracks the net balance between entities.
    
    Attributes:
        from_entity: Entity that owes money.
        to_entity: Entity that is owed money.
        amount: Net amount owed (always positive).
        transaction_count: Number of transactions contributing to this balance.
    """
    
    from_entity: str
    to_entity: str
    amount: Decimal
    transaction_count: int = 0


@dataclass
class CrossEntityAnalysis:
    """
    Complete analysis of cross-entity transactions.
    
    Attributes:
        cross_entity_transactions: List of all transactions spanning multiple entities.
        entity_imbalances: Net imbalance for each entity from cross-entity transactions.
        inter_entity_balances: Pairwise balances between entities.
        as_of_date: Analysis date.
    """
    
    cross_entity_transactions: list[CrossEntityTransaction] = field(default_factory=list)
    entity_imbalances: dict[str, Decimal] = field(default_factory=dict)
    inter_entity_balances: list[InterEntityBalance] = field(default_factory=list)
    as_of_date: Optional[date] = None
    
    def get_total_cross_entity_transactions(self) -> int:
        """Get count of transactions spanning multiple entities."""
        return len(self.cross_entity_transactions)
    
    def get_entities_with_imbalances(self, tolerance: float = 0.01) -> list[str]:
        """Get list of entities with non-zero imbalances."""
        return [
            entity for entity, amount in self.entity_imbalances.items()
            if abs(float(amount)) > tolerance
        ]
    
    def format_summary(self) -> str:
        """Format a human-readable summary of the analysis."""
        lines = []
        lines.append("=" * 80)
        lines.append("CROSS-ENTITY TRANSACTION ANALYSIS")
        lines.append("=" * 80)
        lines.append("")
        
        if self.as_of_date:
            lines.append(f"Analysis Date: {self.as_of_date}")
            lines.append("")
        
        lines.append(f"Total Cross-Entity Transactions: {self.get_total_cross_entity_transactions()}")
        lines.append("")
        
        # Entity imbalances
        lines.append("-" * 80)
        lines.append("ENTITY IMBALANCES FROM CROSS-ENTITY TRANSACTIONS")
        lines.append("-" * 80)
        lines.append("")
        
        if not self.entity_imbalances:
            lines.append("No entity imbalances detected.")
        else:
            lines.append(f"{'Entity':<30} {'Imbalance':>15} {'Status':<20}")
            lines.append("-" * 80)
            
            for entity, imbalance in sorted(self.entity_imbalances.items()):
                if abs(float(imbalance)) > 0.01:
                    status = "Owes others" if imbalance > 0 else "Owed by others"
                    lines.append(f"{entity:<30} {imbalance:>15.2f} {status:<20}")
        
        lines.append("")
        
        # Inter-entity balances
        if self.inter_entity_balances:
            lines.append("-" * 80)
            lines.append("INTER-ENTITY BALANCES (Who Owes Whom)")
            lines.append("-" * 80)
            lines.append("")
            lines.append(f"{'From Entity':<25} {'To Entity':<25} {'Amount':>15} {'Txns':>8}")
            lines.append("-" * 80)
            
            for balance in sorted(self.inter_entity_balances, key=lambda x: x.amount, reverse=True):
                if float(balance.amount) > 0.01:
                    lines.append(
                        f"{balance.from_entity:<25} {balance.to_entity:<25} "
                        f"{balance.amount:>15.2f} {balance.transaction_count:>8}"
                    )
            
            lines.append("")
        
        lines.append("=" * 80)
        
        return "\n".join(lines)
    
    def format_recommendations(self) -> str:
        """Format recommendations for fixing cross-entity imbalances."""
        lines = []
        lines.append("=" * 80)
        lines.append("RECOMMENDATIONS FOR BALANCING CROSS-ENTITY TRANSACTIONS")
        lines.append("=" * 80)
        lines.append("")
        
        imbalanced_entities = self.get_entities_with_imbalances()
        
        if not imbalanced_entities:
            lines.append("✓ All entities are balanced. No action needed.")
            lines.append("")
            return "\n".join(lines)
        
        lines.append("Your entities have imbalances due to cross-entity transactions.")
        lines.append("This is common when shared credit cards or cross-entity payments occur.")
        lines.append("")
        lines.append("RECOMMENDED APPROACH:")
        lines.append("")
        lines.append("1. Create Inter-Entity Equity Accounts:")
        lines.append("   For each business entity, create these accounts:")
        lines.append("   - Equity:Due to Personal (LIABILITY/EQUITY)")
        lines.append("   - Equity:Due from Personal (ASSET/EQUITY)")
        lines.append("")
        lines.append("2. For Personal Entity, create:")
        lines.append("   - Equity:Due from [Business Name] (for each business)")
        lines.append("   - Equity:Due to [Business Name] (for each business)")
        lines.append("")
        lines.append("3. Create Balancing Transactions:")
        lines.append("")
        
        # Provide specific guidance based on inter-entity balances
        if self.inter_entity_balances:
            lines.append("   Based on your analysis, create these balancing entries:")
            lines.append("")
            
            for balance in self.inter_entity_balances:
                if float(balance.amount) > 0.01:
                    lines.append(f"   * {balance.from_entity} owes {balance.to_entity}: ${balance.amount:.2f}")
                    lines.append(f"     Transaction:")
                    lines.append(f"     - Debit:  Equity:Due to {balance.to_entity} (in {balance.from_entity}) ${balance.amount:.2f}")
                    lines.append(f"     - Credit: Equity:Due from {balance.from_entity} (in {balance.to_entity}) ${balance.amount:.2f}")
                    lines.append("")
        
        lines.append("4. Going Forward - Recording Shared Credit Card Transactions:")
        lines.append("")
        lines.append("   When a business expense is paid from a personal credit card:")
        lines.append("   - Debit:  Business Expense account")
        lines.append("   - Credit: Equity:Due to Personal (in business entity)")
        lines.append("")
        lines.append("   Then record the credit card payment separately:")
        lines.append("   - Debit:  Personal Credit Card (liability)")
        lines.append("   - Credit: Personal Bank Account")
        lines.append("")
        lines.append("   And create a balancing entry:")
        lines.append("   - Debit:  Equity:Due from Business (in personal entity)")
        lines.append("   - Credit: Equity:Due to Personal (in business entity)")
        lines.append("")
        lines.append("5. Alternative Approach - Account Splitting:")
        lines.append("")
        lines.append("   Create separate sub-accounts for each credit card:")
        lines.append("   Example: Liabilities:Credit Cards:AmEx")
        lines.append("   - AmEx:Personal Charges -> personal entity")
        lines.append("   - AmEx:Business Charges -> business entity")
        lines.append("")
        lines.append("For detailed guidance, see: SHARED_CREDIT_CARD_GUIDE.md")
        lines.append("")
        lines.append("=" * 80)
        
        return "\n".join(lines)


def analyze_cross_entity_transactions(
    book: GnuCashBook,
    entity_map: EntityMap,
    as_of_date: Optional[date] = None
) -> CrossEntityAnalysis:
    """
    Analyze transactions that span multiple entities.
    
    Args:
        book: GnuCash book to analyze.
        entity_map: Entity mapping configuration.
        as_of_date: Optional date to analyze as of (default: all transactions).
        
    Returns:
        CrossEntityAnalysis object with detailed findings.
    """
    logger.info("Analyzing cross-entity transactions...")
    
    analysis = CrossEntityAnalysis(as_of_date=as_of_date)
    
    # Build account lookup map (GUID -> account info)
    account_lookup: dict[str, tuple[str, str]] = {}  # guid -> (full_name, entity_key)
    for account in book.iter_accounts():
        entity_key = entity_map.resolve_entity_for_account(account.guid, account.full_name)
        account_lookup[account.guid] = (account.full_name, entity_key)
    
    # Track inter-entity flows
    inter_entity_flows: dict[tuple[str, str], list[Decimal]] = defaultdict(list)
    
    # Analyze each transaction
    for txn in book.iter_transactions():
        # Filter by date if specified
        if as_of_date:
            txn_date = parse_date(txn.post_date)
            if txn_date and txn_date > as_of_date:
                continue
        
        # Determine which entities are involved
        entity_amounts: dict[str, Decimal] = defaultdict(Decimal)
        entities_in_txn = set()
        
        for split in txn.splits:
            # Get entity for this split's account
            account_guid = split.account_guid
            
            # Look up account info and entity
            if account_guid in account_lookup:
                _, entity_key = account_lookup[account_guid]
                
                if entity_key:
                    entities_in_txn.add(entity_key)
                    # Track net amount for this entity (value is already in correct sign)
                    entity_amounts[entity_key] += Decimal(str(split.value))
        
        # If transaction spans multiple entities, it's a cross-entity transaction
        if len(entities_in_txn) > 1:
            cross_txn = CrossEntityTransaction(
                transaction=txn,
                entities_involved=entities_in_txn,
                entity_amounts=entity_amounts,
                description=txn.description,
                post_date=parse_date(txn.post_date) or date.today()
            )
            
            analysis.cross_entity_transactions.append(cross_txn)
            
            # Track flows between entities
            for entity, amount in entity_amounts.items():
                # Accumulate imbalance for each entity
                if entity not in analysis.entity_imbalances:
                    analysis.entity_imbalances[entity] = Decimal(0)
                analysis.entity_imbalances[entity] += amount
                
                # Track pairwise flows
                for other_entity, other_amount in entity_amounts.items():
                    if entity != other_entity and amount > 0 and other_amount < 0:
                        # This entity has a debit, other has a credit
                        # Means this entity receives value from other entity
                        inter_entity_flows[(other_entity, entity)].append(amount)
    
    # Calculate inter-entity balances
    inter_entity_summary: dict[tuple[str, str], Decimal] = {}
    inter_entity_counts: dict[tuple[str, str], int] = defaultdict(int)
    
    for (from_entity, to_entity), amounts in inter_entity_flows.items():
        total = sum(amounts)
        if float(total) > 0.01:  # Only include significant balances
            inter_entity_summary[(from_entity, to_entity)] = total
            inter_entity_counts[(from_entity, to_entity)] = len(amounts)
    
    # Create InterEntityBalance objects
    for (from_entity, to_entity), amount in inter_entity_summary.items():
        balance = InterEntityBalance(
            from_entity=from_entity,
            to_entity=to_entity,
            amount=amount,
            transaction_count=inter_entity_counts[(from_entity, to_entity)]
        )
        analysis.inter_entity_balances.append(balance)
    
    logger.info(f"Found {len(analysis.cross_entity_transactions)} cross-entity transactions")
    logger.info(f"Found {len(analysis.get_entities_with_imbalances())} entities with imbalances")
    
    return analysis
