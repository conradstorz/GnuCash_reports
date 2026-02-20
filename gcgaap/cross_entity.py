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
class SplitInfo:
    """Information about a split in a cross-entity transaction."""
    account_name: str
    account_guid: str
    entity: str
    value: Decimal


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
        splits_info: Detailed information about each split.
    """
    
    transaction: GCTransaction
    entities_involved: set[str]
    entity_amounts: dict[str, Decimal]
    description: str
    post_date: date
    splits_info: list[SplitInfo] = field(default_factory=list)
    
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
    
    def get_max_entity_imbalance(self) -> Decimal:
        """Get the maximum absolute imbalance among all entities in this transaction."""
        if not self.entity_amounts:
            return Decimal(0)
        return max(abs(amount) for amount in self.entity_amounts.values())
    
    def has_significant_imbalance(self, tolerance: float = 0.01) -> bool:
        """Check if any entity has a significant non-zero balance."""
        return float(self.get_max_entity_imbalance()) > tolerance


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
    
    def filter_by_entity(self, entity_key: str) -> "CrossEntityAnalysis":
        """
        Create a filtered analysis containing only transactions involving the specified entity.
        
        Args:
            entity_key: The entity key to filter by.
            
        Returns:
            New CrossEntityAnalysis with filtered transactions.
        """
        # Filter transactions to only those involving the specified entity
        filtered_txns = [
            txn for txn in self.cross_entity_transactions
            if entity_key in txn.entities_involved
        ]
        
        # Create new analysis with filtered transactions
        filtered_analysis = CrossEntityAnalysis(as_of_date=self.as_of_date)
        filtered_analysis.cross_entity_transactions = filtered_txns
        
        # Recalculate entity imbalances
        entity_imbalances: dict[str, Decimal] = defaultdict(Decimal)
        for txn in filtered_txns:
            for entity, amount in txn.entity_amounts.items():
                entity_imbalances[entity] += amount
        filtered_analysis.entity_imbalances = dict(entity_imbalances)
        
        # Recalculate inter-entity balances
        inter_entity_flows: dict[tuple[str, str], list[Decimal]] = defaultdict(list)
        for txn in filtered_txns:
            entities = list(txn.entities_involved)
            if len(entities) >= 2:
                for i, entity1 in enumerate(entities):
                    for entity2 in entities[i+1:]:
                        amount1 = txn.entity_amounts.get(entity1, Decimal("0"))
                        amount2 = txn.entity_amounts.get(entity2, Decimal("0"))
                        
                        # Track flow from entity1 perspective
                        flow = -amount1
                        
                        # Normalize entity pair order
                        pair = tuple(sorted([entity1, entity2]))
                        if entity1 != pair[0]:
                            flow = -flow
                        
                        inter_entity_flows[pair].append(flow)
        
        # Create inter-entity balances
        inter_entity_balances = []
        for (entity1, entity2), flows in inter_entity_flows.items():
            net_flow = sum(flows)
            if abs(float(net_flow)) > 0.01:  # Only include significant flows
                inter_entity_balances.append(InterEntityBalance(
                    from_entity=entity1 if net_flow < 0 else entity2,
                    to_entity=entity2 if net_flow < 0 else entity1,
                    amount=abs(net_flow),
                    transaction_count=len([f for f in flows if abs(float(f)) > 0.01])
                ))
        
        filtered_analysis.inter_entity_balances = sorted(
            inter_entity_balances,
            key=lambda x: x.amount,
            reverse=True
        )
        
        return filtered_analysis
    
    def format_transaction_details(self, limit: Optional[int] = None, tolerance: float = 0.01) -> str:
        """
        Format detailed information about cross-entity transactions.
        
        Args:
            limit: Optional limit on number of transactions to show.
            tolerance: Tolerance for filtering out balanced transactions.
            
        Returns:
            Formatted string with transaction details.
        """
        lines = []
        lines.append("=" * 80)
        lines.append("DETAILED CROSS-ENTITY TRANSACTIONS")
        lines.append("=" * 80)
        lines.append("")
        
        if not self.cross_entity_transactions:
            lines.append("No cross-entity transactions found.")
            lines.append("")
            return "\n".join(lines)
        
        # Filter out balanced transactions (where all entities have ~0 net)
        unbalanced_txns = [
            txn for txn in self.cross_entity_transactions
            if txn.has_significant_imbalance(tolerance)
        ]
        
        if not unbalanced_txns:
            lines.append("All cross-entity transactions are balanced.")
            lines.append(f"(Filtered out {len(self.cross_entity_transactions)} balanced cross-entity transactions)")
            lines.append("")
            return "\n".join(lines)
        
        # Sort by largest imbalance first, then by date
        sorted_txns = sorted(
            unbalanced_txns,
            key=lambda x: (x.get_max_entity_imbalance(), x.post_date),
            reverse=True
        )
        
        # Apply limit if specified
        txns_to_show = sorted_txns[:limit] if limit else sorted_txns
        
        balanced_count = len(self.cross_entity_transactions) - len(unbalanced_txns)
        if balanced_count > 0:
            lines.append(f"Filtered out {balanced_count} balanced cross-entity transaction(s)")
            lines.append("")
        
        lines.append(f"Showing {len(txns_to_show)} of {len(sorted_txns)} unbalanced cross-entity transactions")
        lines.append("(Sorted by largest imbalance)")
        lines.append("")
        
        for i, cross_txn in enumerate(txns_to_show, 1):
            max_imbalance = cross_txn.get_max_entity_imbalance()
            lines.append(f"Transaction #{i} [Max Imbalance: ${max_imbalance:,.2f}]")
            lines.append(f"Date: {cross_txn.post_date}")
            lines.append(f"Description: {cross_txn.description}")
            lines.append(f"GUID: {cross_txn.transaction.guid}")
            lines.append(f"Entities: {', '.join(sorted(cross_txn.entities_involved))}")
            lines.append("")
            
            # Show net amounts per entity
            lines.append("Net by Entity:")
            for entity in sorted(cross_txn.entities_involved):
                amount = cross_txn.entity_amounts.get(entity, Decimal(0))
                sign = "+" if amount >= 0 else ""
                lines.append(f"  {entity:<30} {sign}{amount:>15.2f}")
            
            # Show individual splits grouped by entity
            lines.append("")
            lines.append("Splits by Account:")
            for split_info in cross_txn.splits_info:
                value = split_info.value
                sign = "+" if value >= 0 else ""
                lines.append(f"  [{split_info.entity}]")
                lines.append(f"    {split_info.account_name:<60} {sign}{value:>15.2f}")
            
            lines.append("")
            lines.append("-" * 80)
            lines.append("")
        
        if limit and len(sorted_txns) > limit:
            lines.append(f"... and {len(sorted_txns) - limit} more transactions")
            lines.append(f"Use --limit with a higher value to see more, or omit --limit to see all")
            lines.append("")
        
        lines.append("=" * 80)
        
        return "\n".join(lines)
    
    def format_simple_list(self, tolerance: float = 0.01) -> str:
        """
        Format unbalanced transactions as a simple list with one split per line.
        
        Args:
            tolerance: Tolerance for filtering out balanced transactions.
            
        Returns:
            Formatted string with account name, date, and amount per line.
        """
        lines = []
        lines.append("=" * 80)
        lines.append("UNBALANCED CROSS-ENTITY TRANSACTIONS - SIMPLE LIST")
        lines.append("=" * 80)
        lines.append("")
        
        if not self.cross_entity_transactions:
            lines.append("No cross-entity transactions found.")
            return "\n".join(lines)
        
        # Filter out balanced transactions
        unbalanced_txns = [
            txn for txn in self.cross_entity_transactions
            if txn.has_significant_imbalance(tolerance)
        ]
        
        if not unbalanced_txns:
            lines.append("All cross-entity transactions are balanced.")
            return "\n".join(lines)
        
        # Filter to only 2-split transactions and sort by Account 2 name
        two_split_txns = [txn for txn in unbalanced_txns if len(txn.splits_info) == 2]
        sorted_txns = sorted(two_split_txns, key=lambda x: x.splits_info[1].account_name.split(':')[-1])
        
        lines.append(f"{'Date':<12} {'Account 1':<45} {'Amount 1':>12}   {'Account 2':<45} {'Amount 2':>12}")
        lines.append("-" * 130)
        
        # Output each transaction on a single line with both accounts
        for cross_txn in sorted_txns:
            split1 = cross_txn.splits_info[0]
            split2 = cross_txn.splits_info[1]
            
            # Extract leaf account names
            account1 = split1.account_name.split(':')[-1]
            account2 = split2.account_name.split(':')[-1]
            
            lines.append(
                f"{cross_txn.post_date} "
                f"{account1:<45} "
                f"{split1.value:>12.2f}   "
                f"{account2:<45} "
                f"{split2.value:>12.2f}"
            )
        
        lines.append("-" * 130)
        lines.append(f"Total 2-split unbalanced transactions: {len(sorted_txns)}")
        
        multi_split_count = len(unbalanced_txns) - len(two_split_txns)
        if multi_split_count > 0:
            lines.append(f"(Excluded {multi_split_count} transactions with more than 2 splits)")
        lines.append("")
        
        return "\n".join(lines)
    
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
        
        # Count unbalanced transactions
        unbalanced_count = sum(
            1 for txn in self.cross_entity_transactions
            if txn.has_significant_imbalance()
        )
        balanced_count = len(self.cross_entity_transactions) - unbalanced_count
        
        lines.append(f"Total Cross-Entity Transactions: {self.get_total_cross_entity_transactions()}")
        lines.append(f"  - Unbalanced (problematic): {unbalanced_count}")
        lines.append(f"  - Balanced (proper inter-entity): {balanced_count}")
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
            lines.append("[OK] All entities are balanced. No action needed.")
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
        splits_info_list = []
        
        for split in txn.splits:
            # Get entity for this split's account
            account_guid = split.account_guid
            
            # Look up account info and entity
            if account_guid in account_lookup:
                account_name, entity_key = account_lookup[account_guid]
                
                if entity_key:
                    entities_in_txn.add(entity_key)
                    # Track net amount for this entity (value is already in correct sign)
                    split_value = Decimal(str(split.value))
                    entity_amounts[entity_key] += split_value
                    
                    # Store split details
                    splits_info_list.append(SplitInfo(
                        account_name=account_name,
                        account_guid=account_guid,
                        entity=entity_key,
                        value=split_value
                    ))
        
        # If transaction spans multiple entities, it's a cross-entity transaction
        if len(entities_in_txn) > 1:
            cross_txn = CrossEntityTransaction(
                transaction=txn,
                entities_involved=entities_in_txn,
                entity_amounts=entity_amounts,
                description=txn.description,
                post_date=parse_date(txn.post_date) or date.today(),
                splits_info=splits_info_list
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
