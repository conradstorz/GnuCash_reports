"""
Cross-entity transaction balancing utility for GCGAAP.

Provides tools to automatically balance 2-split cross-entity transactions
by adding inter-entity equity account splits.
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional
import shutil

from .entity_map import EntityMap
from .cross_entity import CrossEntityTransaction, analyze_cross_entity_transactions
from .gnucash_access import GnuCashBook, parse_date

logger = logging.getLogger(__name__)


@dataclass
class EquityAccounts:
    """Container for entity equity account information."""
    entity_key: str
    money_in_guid: Optional[str] = None  # GUID of Money In account
    money_out_guid: Optional[str] = None  # GUID of Money Out account
    money_in_name: Optional[str] = None  # Full name of Money In account
    money_out_name: Optional[str] = None  # Full name of Money Out account
    
    def has_both_accounts(self) -> bool:
        """Check if both Money In and Money Out accounts exist."""
        return self.money_in_guid is not None and self.money_out_guid is not None


@dataclass
class TransactionGroup:
    """Group of similar cross-entity transactions for batch approval."""
    entity_pair: tuple[str, str]  # Sorted tuple of entity keys
    expense_account: str  # Common expense account name
    transactions: list[CrossEntityTransaction] = field(default_factory=list)
    
    def get_display_name(self) -> str:
        """Get a human-readable name for this group."""
        entity1, entity2 = self.entity_pair
        expense_leaf = self.expense_account.split(':')[-1] if ':' in self.expense_account else self.expense_account
        return f"{entity1} <-> {entity2} / {expense_leaf}"


def create_backup(db_path: Path) -> Path:
    """
    Create a timestamped backup of the GnuCash database.
    
    Args:
        db_path: Path to the GnuCash database file.
        
    Returns:
        Path to the backup file.
        
    Raises:
        IOError: If backup creation fails.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.with_suffix(f'.backup_{timestamp}.gnucash')
    
    logger.info(f"Creating backup: {backup_path}")
    
    try:
        shutil.copy2(db_path, backup_path)
        logger.info("Backup created successfully")
        return backup_path
    except Exception as e:
        logger.error(f"Failed to create backup: {e}")
        raise IOError(f"Could not create backup: {e}")


def find_equity_accounts(book_obj, entity_map: EntityMap) -> dict[str, EquityAccounts]:
    """
    Find Money In and Money Out equity accounts for all entities.
    
    Args:
        book_obj: piecash Book object (opened with readonly=False).
        entity_map: Entity mapping configuration.
        
    Returns:
        Dictionary mapping entity_key to EquityAccounts object.
    """
    logger.info("Looking for inter-entity equity accounts...")
    
    equity_accounts = {}
    
    # Initialize EquityAccounts for each entity
    for entity_key in entity_map.entities.keys():
        equity_accounts[entity_key] = EquityAccounts(entity_key=entity_key)
    
    # Scan all accounts for Money In/Out patterns
    for account in book_obj.accounts:
        if account.type != 'EQUITY':
            continue
        
        fullname = account.fullname if hasattr(account, 'fullname') else str(account)
        
        # Resolve which entity this account belongs to
        entity_key = entity_map.resolve_entity_for_account(str(account.guid), fullname)
        
        if not entity_key or entity_key not in equity_accounts:
            continue
        
        # Check if it's a Money In or Money Out account
        account_name_lower = fullname.lower()
        
        # Pattern: "Equity:EntityName:Money In (OtherEntity)"
        # Pattern: "Equity:EntityName:Money Out (OtherEntity)"
        if 'money in' in account_name_lower:
            equity_accounts[entity_key].money_in_guid = str(account.guid)
            equity_accounts[entity_key].money_in_name = fullname
            logger.debug(f"Found Money In account for {entity_key}: {fullname}")
        elif 'money out' in account_name_lower:
            equity_accounts[entity_key].money_out_guid = str(account.guid)
            equity_accounts[entity_key].money_out_name = fullname
            logger.debug(f"Found Money Out account for {entity_key}: {fullname}")
    
    return equity_accounts


def identify_fixable_transactions(
    analysis,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    entity_filter: Optional[str] = None
) -> list[CrossEntityTransaction]:
    """
    Identify 2-split cross-entity transactions that need balancing.
    
    Args:
        analysis: CrossEntityAnalysis object from analyze_cross_entity_transactions.
        date_from: Optional start date filter.
        date_to: Optional end date filter.
        entity_filter: Optional entity key to filter by.
        
    Returns:
        List of CrossEntityTransaction objects that are fixable.
    """
    logger.info("Identifying fixable transactions...")
    
    fixable = []
    
    for txn in analysis.cross_entity_transactions:
        # Must be exactly 2 splits
        if len(txn.splits_info) != 2:
            logger.debug(f"Skipping txn {txn.transaction.guid}: not 2 splits ({len(txn.splits_info)})")
            continue
        
        # Must involve exactly 2 entities
        if len(txn.entities_involved) != 2:
            logger.debug(f"Skipping txn {txn.transaction.guid}: not 2 entities ({len(txn.entities_involved)})")
            continue
        
        # Must have an imbalance
        if not txn.has_significant_imbalance():
            logger.debug(f"Skipping txn {txn.transaction.guid}: already balanced")
            continue
        
        # Skip transactions involving excluded entities (unassigned, placeholder_only_acct)
        excluded_entities = {'unassigned', 'placeholder_only_acct'}
        if any(entity in excluded_entities for entity in txn.entities_involved):
            logger.debug(f"Skipping txn {txn.transaction.guid}: involves excluded entity")
            continue
        
        # Apply date filters
        if date_from and txn.post_date < date_from:
            continue
        if date_to and txn.post_date > date_to:
            continue
        
        # Apply entity filter
        if entity_filter and entity_filter not in txn.entities_involved:
            continue
        
        fixable.append(txn)
    
    logger.info(f"Found {len(fixable)} fixable transactions")
    return fixable


def group_transactions(transactions: list[CrossEntityTransaction]) -> list[TransactionGroup]:
    """
    Group transactions by entity pair and expense account.
    
    Args:
        transactions: List of CrossEntityTransaction objects.
        
    Returns:
        List of TransactionGroup objects, with max 9 transactions per group.
    """
    logger.info("Grouping transactions...")
    
    # First group by entity pair and expense account
    groups_dict: dict[tuple[tuple[str, str], str], list[CrossEntityTransaction]] = defaultdict(list)
    
    for txn in transactions:
        # Get entity pair (sorted for consistency)
        entity_pair = tuple(sorted(txn.entities_involved))
        
        # Get the expense account (find first Expenses: account in the splits)
        expense_account = None
        for split_info in txn.splits_info:
            if split_info.account_name.startswith('Expenses:'):
                expense_account = split_info.account_name
                break
        
        # If no expense account found, use first account
        if not expense_account and txn.splits_info:
            expense_account = txn.splits_info[0].account_name
        
        if not expense_account:
            expense_account = "(Unknown)"
        
        # Group by entity pair and expense account
        key = (entity_pair, expense_account)
        groups_dict[key].append(txn)
    
    # Convert to TransactionGroup objects and split large groups
    all_groups = []
    
    for (entity_pair, expense_account), txns in groups_dict.items():
        # Sort transactions by date
        txns.sort(key=lambda t: t.post_date)
        
        # Split into groups of max 9 transactions
        for i in range(0, len(txns), 9):
            chunk = txns[i:i+9]
            group = TransactionGroup(
                entity_pair=entity_pair,
                expense_account=expense_account,
                transactions=chunk
            )
            all_groups.append(group)
    
    # Sort groups by entity pair and expense account
    all_groups.sort(key=lambda g: (g.entity_pair, g.expense_account))
    
    logger.info(f"Created {len(all_groups)} transaction groups")
    return all_groups


def format_group_for_approval(group: TransactionGroup) -> str:
    """
    Format a transaction group for user approval.
    
    Args:
        group: TransactionGroup to format.
        
    Returns:
        Formatted string for display.
    """
    lines = []
    lines.append(f"\nGroup: {group.get_display_name()}")
    lines.append(f"Transactions: {len(group.transactions)}")
    lines.append("-" * 100)
    lines.append(f"{'Date':<12} {'Amount':>12}  {'Opposing Entity':<30}")
    lines.append("-" * 100)
    
    for txn in group.transactions:
        # Get the other entity (not the one in the expense account)
        entities = list(txn.entities_involved)
        
        # Determine which entity and amount to show
        # Show the entity and amount for the non-expense split
        display_entity = None
        display_amount = Decimal(0)
        
        for split_info in txn.splits_info:
            if not split_info.account_name.startswith('Expenses:'):
                display_entity = split_info.entity
                display_amount = abs(split_info.value)
                break
        
        if not display_entity and len(entities) > 0:
            display_entity = entities[0]
            display_amount = abs(list(txn.entity_amounts.values())[0])
        
        lines.append(f"{txn.post_date}  ${display_amount:>11.2f}  {display_entity:<30}")
    
    lines.append("-" * 100)
    
    return "\n".join(lines)


def add_balancing_splits(
    book_obj,
    txn: CrossEntityTransaction,
    equity_accounts_map: dict[str, EquityAccounts],
    dry_run: bool = False
) -> bool:
    """
    Add two balancing splits to a cross-entity transaction.
    
    Args:
        book_obj: piecash Book object (opened with readonly=False).
        txn: CrossEntityTransaction to balance.
        equity_accounts_map: Dictionary of entity equity accounts.
        dry_run: If True, don't actually modify the transaction.
        
    Returns:
        True if successful, False otherwise.
    """
    if len(txn.entities_involved) != 2:
        logger.error(f"Transaction {txn.transaction.guid} has {len(txn.entities_involved)} entities, expected 2")
        return False
    
    entities = list(txn.entities_involved)
    entity1, entity2 = entities[0], entities[1]
    
    # Calculate the imbalance for each entity
    imbalance1 = txn.entity_amounts.get(entity1, Decimal(0))
    imbalance2 = txn.entity_amounts.get(entity2, Decimal(0))
    
    # Verify imbalances are opposite and equal (within tolerance)
    if abs(float(imbalance1 + imbalance2)) > 0.01:
        logger.error(f"Transaction {txn.transaction.guid} has mismatched imbalances: {imbalance1} + {imbalance2}")
        return False
    
    # Get equity accounts for both entities
    if entity1 not in equity_accounts_map or entity2 not in equity_accounts_map:
        logger.error(f"Missing equity accounts for entities: {entity1}, {entity2}")
        return False
    
    equity1 = equity_accounts_map[entity1]
    equity2 = equity_accounts_map[entity2]
    
    if not equity1.has_both_accounts() or not equity2.has_both_accounts():
        logger.error(f"Missing Money In/Out accounts for {entity1} or {entity2}")
        return False
    
    # Determine which equity account GUID to use for each entity
    # If entity1 has positive imbalance (debit side), it received value from entity2
    # So entity1 needs Money In account (credit to show money came in from entity2)
    # And entity2 needs Money Out account (debit to show money went out to entity1)
    
    if imbalance1 > 0:
        # Entity1 received benefit from Entity2 (Entity1 owes Entity2)
        account1_guid = equity1.money_in_guid   # Credit (money came IN from entity2)
        account1_name = equity1.money_in_name
        account2_guid = equity2.money_out_guid  # Debit (money went OUT to entity1)
        account2_name = equity2.money_out_name
        amount = abs(imbalance1)  # Keep as Decimal
    else:
        # Entity2 received benefit from Entity1 (Entity2 owes Entity1)
        account1_guid = equity1.money_out_guid  # Debit (money went OUT to entity2)
        account1_name = equity1.money_out_name
        account2_guid = equity2.money_in_guid   # Credit (money came IN from entity1)
        account2_name = equity2.money_in_name
        amount = abs(imbalance2)  # Keep as Decimal
    
    if dry_run:
        logger.info(f"[DRY RUN] Would add balancing splits to transaction {txn.transaction.guid}")
        logger.info(f"  Split 1: {account1_name} = ${amount:.2f}")
        logger.info(f"  Split 2: {account2_name} = ${amount:.2f}")
        return True
    
    try:
        # Find the actual piecash transaction object
        import piecash
        
        piecash_txn = None
        for t in book_obj.transactions:
            if str(t.guid) == txn.transaction.guid:
                piecash_txn = t
                break
        
        if not piecash_txn:
            logger.error(f"Could not find piecash transaction for GUID {txn.transaction.guid}")
            return False
        
        # Look up the equity accounts by GUID in the current session
        account1 = None
        account2 = None
        for account in book_obj.accounts:
            if str(account.guid) == account1_guid:
                account1 = account
            if str(account.guid) == account2_guid:
                account2 = account
            if account1 and account2:
                break
        
        if not account1 or not account2:
            logger.error(f"Could not find equity accounts in book: {account1_guid}, {account2_guid}")
            return False
        
        # Create the two balancing splits
        # In GnuCash/piecash, splits must balance to zero
        # So if entity1 has +100 imbalance (received benefit), we add:
        #   - Split for account1 with value -100 (credit Money IN)
        #   - Split for account2 with value +100 (debit Money OUT)
        
        if imbalance1 > 0:
            value1 = -amount  # Credit entity1's Money IN account (money received from entity2)
            value2 = amount   # Debit entity2's Money OUT account (money given to entity1)
        else:
            value1 = amount   # Debit entity1's Money OUT account (money given to entity2)
            value2 = -amount  # Credit entity2's Money IN account (money received from entity1)
        
        memo1 = f"Inter-entity balance: {entity2} - Made by gcgaap"
        memo2 = f"Inter-entity balance: {entity1} - Made by gcgaap"
        
        # Create splits using piecash
        split1 = piecash.Split(
            account=account1,
            value=value1,
            memo=memo1,
            reconcile_state='n'  # Not reconciled
        )
        
        split2 = piecash.Split(
            account=account2,
            value=value2,
            memo=memo2,
            reconcile_state='n'  # Not reconciled
        )
        
        # Add splits to transaction
        piecash_txn.splits.append(split1)
        piecash_txn.splits.append(split2)
        
        logger.info(f"Added balancing splits to transaction {txn.transaction.guid}")
        logger.debug(f"  Split 1: {account1_name} = {value1:.2f} ({memo1})")
        logger.debug(f"  Split 2: {account2_name} = {value2:.2f} ({memo2})")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to add balancing splits to transaction {txn.transaction.guid}: {e}")
        return False


def run_balance_xacts_workflow(
    book_file: Path,
    entity_map: EntityMap,
    entity_filter: Optional[str],
    date_from: Optional[date],
    date_to: Optional[date],
    dry_run: bool,
) -> tuple[int, int, Optional[Path]]:
    """
    Orchestrate the 6-step balance cross-entity transactions workflow.

    Args:
        book_file: Path to the GnuCash book file.
        entity_map: Loaded EntityMap.
        entity_filter: Optional entity key to filter transactions.
        date_from: Optional start date filter (already parsed).
        date_to: Optional end date filter (already parsed).
        dry_run: If True, preview changes without writing to the database.

    Returns:
        Tuple of (fixed_count, failed_count, backup_path_or_None).
    """
    import click

    # Step 1: Analyze cross-entity transactions
    click.echo("\n" + "=" * 80)
    click.echo("STEP 1: Analyzing cross-entity transactions...")
    click.echo("=" * 80)

    with GnuCashBook(book_file) as book:
        analysis = analyze_cross_entity_transactions(book, entity_map)

    # Step 2: Identify fixable transactions
    click.echo("\n" + "=" * 80)
    click.echo("STEP 2: Identifying fixable 2-split transactions...")
    click.echo("=" * 80)

    fixable = identify_fixable_transactions(
        analysis,
        date_from=date_from,
        date_to=date_to,
        entity_filter=entity_filter
    )

    if not fixable:
        click.echo("\nNo fixable transactions found!")
        click.echo("(Looking for 2-split cross-entity transactions with imbalances)")
        return 0, 0, None

    click.echo(f"\nFound {len(fixable)} fixable transaction(s)")

    # Step 3: Check for required equity accounts
    click.echo("\n" + "=" * 80)
    click.echo("STEP 3: Checking for inter-entity equity accounts...")
    click.echo("=" * 80)

    import piecash

    book_obj = piecash.open_book(str(book_file), readonly=True, do_backup=False)
    equity_accounts_map = find_equity_accounts(book_obj, entity_map)
    book_obj.close()

    # Check which entities are involved in fixable transactions
    involved_entities = set()
    for txn in fixable:
        involved_entities.update(txn.entities_involved)

    # Verify all involved entities have equity accounts
    missing_accounts = []
    for entity_key in involved_entities:
        if entity_key not in equity_accounts_map:
            missing_accounts.append(f"  - {entity_key}: No equity accounts found")
        elif not equity_accounts_map[entity_key].has_both_accounts():
            equity = equity_accounts_map[entity_key]
            if not equity.money_in_account:
                missing_accounts.append(f"  - {entity_key}: Missing 'Money In' account")
            if not equity.money_out_account:
                missing_accounts.append(f"  - {entity_key}: Missing 'Money Out' account")

    if missing_accounts:
        click.echo("\n[ERROR] Missing required equity accounts:")
        for msg in missing_accounts:
            click.echo(msg)
        click.echo("\nRequired account pattern for each entity:")
        click.echo("  Equity:<EntityName>:Money In (<OtherEntity>)")
        click.echo("  Equity:<EntityName>:Money Out (<OtherEntity>)")
        click.echo("\nCreate these accounts in GnuCash and map them to entities.")
        return 0, len(fixable), None

    click.echo(f"\n[OK] All {len(involved_entities)} involved entities have required equity accounts")

    # Step 4: Group transactions
    click.echo("\n" + "=" * 80)
    click.echo("STEP 4: Grouping similar transactions...")
    click.echo("=" * 80)

    groups = group_transactions(fixable)

    click.echo(f"\nCreated {len(groups)} group(s) for approval")

    # Step 5: Create backup (unless dry-run)
    backup_path: Optional[Path] = None
    if not dry_run:
        click.echo("\n" + "=" * 80)
        click.echo("STEP 5: Creating backup...")
        click.echo("=" * 80)

        backup_path = create_backup(book_file)
        click.echo(f"\n[OK] Backup created: {backup_path}")
    else:
        click.echo("\n[DRY RUN] Skipping backup creation")

    # Step 6: Process groups with user approval
    click.echo("\n" + "=" * 80)
    if dry_run:
        click.echo("STEP 6: Processing groups (DRY RUN - no changes will be made)...")
    else:
        click.echo("STEP 6: Processing groups (you will approve each group)...")
    click.echo("=" * 80)

    fixed_count, failed_count = balance_transaction_groups(
        book_file,
        groups,
        equity_accounts_map,
        dry_run=dry_run
    )

    return fixed_count, failed_count, backup_path


def balance_transaction_groups(
    book_path: Path,
    groups: list[TransactionGroup],
    equity_accounts_map: dict[str, EquityAccounts],
    dry_run: bool = False
) -> tuple[int, int]:
    """
    Process transaction groups with user approval and balance them.
    
    Args:
        book_path: Path to the GnuCash book file.
        groups: List of TransactionGroup objects to process.
        equity_accounts_map: Dictionary of entity equity accounts.
        dry_run: If True, don't actually modify transactions.
        
    Returns:
        Tuple of (number of transactions fixed, number of transactions failed).
    """
    import piecash
    import click
    
    fixed_count = 0
    failed_count = 0
    
    # Open book for writing (unless dry run)
    if not dry_run:
        logger.info(f"Opening GnuCash book for writing: {book_path}")
        book_obj = piecash.open_book(str(book_path), readonly=False, do_backup=False)
    else:
        logger.info(f"Opening GnuCash book in read-only mode (dry run): {book_path}")
        book_obj = piecash.open_book(str(book_path), readonly=True, do_backup=False)
    
    try:
        for i, group in enumerate(groups, 1):
            # Display group information
            click.echo(format_group_for_approval(group))
            
            # Ask for approval (or auto-approve in dry run)
            if dry_run:
                # In dry run, automatically process all groups
                click.echo(f"\n[DRY RUN] Auto-processing group {i}/{len(groups)}")
                response = True
            else:
                response = click.confirm(
                    f"\nBalance these {len(group.transactions)} transaction(s)? ({i}/{len(groups)})",
                    default=True
                )
            
            if not response:
                click.echo(f"Skipped group {i}/{len(groups)}")
                continue
            
            # Process each transaction in the group
            for txn in group.transactions:
                success = add_balancing_splits(
                    book_obj,
                    txn,
                    equity_accounts_map,
                    dry_run=dry_run
                )
                
                if success:
                    fixed_count += 1
                else:
                    failed_count += 1
            
            # Save after each group (unless dry run)
            if not dry_run:
                try:
                    book_obj.save()
                    book_obj.flush()
                    click.echo(f"[OK] Saved changes for group {i}/{len(groups)}")
                except Exception as e:
                    click.echo(f"[ERROR] Error saving changes: {e}")
                    logger.error(f"Failed to save changes: {e}")
                    failed_count += len(group.transactions)
                    fixed_count -= len(group.transactions)
        
    finally:
        book_obj.close()
    
    return fixed_count, failed_count
