"""
Database snapshot and comparison utilities.

Provides tools for capturing GnuCash database state and comparing
snapshots to identify what changed during fixes or external utility operations.
"""
import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from .gnucash_access import GnuCashBook

logger = logging.getLogger(__name__)


@dataclass
class TransactionSnapshot:
    """Snapshot of a single transaction's state."""
    
    guid: str
    description: str
    post_date: Optional[str]
    enter_date: Optional[str]
    split_count: int
    splits: list[dict]
    error: Optional[str] = None
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class AccountSnapshot:
    """Snapshot of a single account's state."""
    
    guid: str
    full_name: str
    type: str
    commodity_symbol: str
    parent_guid: Optional[str]
    balance: Optional[float] = None
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


class DatabaseSnapshot:
    """
    Complete snapshot of GnuCash database state.
    
    Captures accounts, transactions, and metadata for comparison.
    """
    
    def __init__(self):
        self.timestamp = datetime.now().isoformat()
        self.accounts: dict[str, AccountSnapshot] = {}
        self.transactions: dict[str, TransactionSnapshot] = {}
        self.metadata = {
            "account_count": 0,
            "transaction_count": 0,
            "error_count": 0
        }
    
    @classmethod
    def capture(cls, book: GnuCashBook) -> "DatabaseSnapshot":
        """
        Capture a snapshot of the current database state.
        
        Args:
            book: Opened GnuCashBook to snapshot.
            
        Returns:
            DatabaseSnapshot with all accounts and transactions.
        """
        logger.info("Capturing database snapshot")
        snapshot = cls()
        
        # Capture accounts
        for account in book.iter_accounts():
            snapshot.accounts[account.guid] = AccountSnapshot(
                guid=account.guid,
                full_name=account.full_name,
                type=account.type,
                commodity_symbol=account.commodity_symbol,
                parent_guid=account.parent_guid
            )
        
        snapshot.metadata["account_count"] = len(snapshot.accounts)
        logger.info(f"Captured {len(snapshot.accounts)} accounts")
        
        # Capture transactions - need to handle errors gracefully
        error_count = 0
        success_count = 0
        
        # Access the underlying piecash book directly to handle errors
        try:
            for transaction in book._book.transactions:
                try:
                    # Try to read transaction data safely
                    trans_guid = str(transaction.guid)
                    trans_desc = transaction.description if transaction.description else ""
                    
                    # Try to get dates
                    post_date = None
                    enter_date = None
                    error = None
                    
                    try:
                        post_date = transaction.post_date.strftime("%Y-%m-%d %H:%M:%S") if transaction.post_date else None
                    except Exception as e:
                        error = f"post_date: {str(e)}"
                    
                    try:
                        enter_date = transaction.enter_date.strftime("%Y-%m-%d %H:%M:%S") if hasattr(transaction, 'enter_date') and transaction.enter_date else None
                    except Exception as e:
                        if error:
                            error += f"; enter_date: {str(e)}"
                        else:
                            error = f"enter_date: {str(e)}"
                    
                    # Try to get splits
                    splits = []
                    split_count = 0
                    try:
                        for split in transaction.splits:
                            split_count += 1
                            try:
                                splits.append({
                                    "account_guid": str(split.account.guid) if split.account else None,
                                    "account_name": split.account.name if split.account else None,
                                    "value": float(split.value) if split.value is not None else None,
                                    "quantity": float(split.quantity) if split.quantity is not None else None,
                                    "memo": split.memo if split.memo else None,
                                    "reconcile_state": split.reconcile_state if hasattr(split, 'reconcile_state') else None
                                })
                            except Exception as e:
                                splits.append({
                                    "error": f"Error reading split: {str(e)}"
                                })
                    except Exception as e:
                        error = f"splits: {str(e)}" if not error else f"{error}; splits: {str(e)}"
                    
                    snapshot.transactions[trans_guid] = TransactionSnapshot(
                        guid=trans_guid,
                        description=trans_desc,
                        post_date=post_date,
                        enter_date=enter_date,
                        split_count=split_count,
                        splits=splits,
                        error=error
                    )
                    
                    if error:
                        error_count += 1
                    else:
                        success_count += 1
                        
                except Exception as e:
                    logger.error(f"Error capturing transaction: {e}")
                    error_count += 1
                    
        except Exception as e:
            logger.error(f"Error iterating transactions: {e}")
        
        snapshot.metadata["transaction_count"] = len(snapshot.transactions)
        snapshot.metadata["error_count"] = error_count
        logger.info(f"Captured {len(snapshot.transactions)} transactions ({success_count} valid, {error_count} with errors)")
        
        return snapshot
    
    def save(self, filepath: Path) -> None:
        """
        Save snapshot to a JSON file.
        
        Args:
            filepath: Path to save the snapshot to.
        """
        data = {
            "timestamp": self.timestamp,
            "metadata": self.metadata,
            "accounts": {guid: acc.to_dict() for guid, acc in self.accounts.items()},
            "transactions": {guid: trans.to_dict() for guid, trans in self.transactions.items()}
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Snapshot saved to {filepath}")
    
    @classmethod
    def load(cls, filepath: Path) -> "DatabaseSnapshot":
        """
        Load a snapshot from a JSON file.
        
        Args:
            filepath: Path to load the snapshot from.
            
        Returns:
            DatabaseSnapshot loaded from file.
        """
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        snapshot = cls()
        snapshot.timestamp = data["timestamp"]
        snapshot.metadata = data["metadata"]
        
        # Reconstruct accounts
        for guid, acc_data in data["accounts"].items():
            snapshot.accounts[guid] = AccountSnapshot(**acc_data)
        
        # Reconstruct transactions
        for guid, trans_data in data["transactions"].items():
            snapshot.transactions[guid] = TransactionSnapshot(**trans_data)
        
        logger.info(f"Snapshot loaded from {filepath}")
        return snapshot


def compare_snapshots(before: DatabaseSnapshot, after: DatabaseSnapshot) -> dict:
    """
    Compare two database snapshots and identify changes.
    
    Args:
        before: Snapshot taken before changes.
        after: Snapshot taken after changes.
        
    Returns:
        Dictionary with change summary and details.
    """
    logger.info("Comparing snapshots")
    
    changes = {
        "timestamp_before": before.timestamp,
        "timestamp_after": after.timestamp,
        "accounts": {
            "added": [],
            "removed": [],
            "modified": []
        },
        "transactions": {
            "added": [],
            "removed": [],
            "modified": [],
            "fixed": [],  # Transactions that had errors before but not after
            "broken": []  # Transactions that were ok before but have errors after
        },
        "summary": {}
    }
    
    # Compare accounts
    before_guids = set(before.accounts.keys())
    after_guids = set(after.accounts.keys())
    
    added_guids = after_guids - before_guids
    removed_guids = before_guids - after_guids
    common_guids = before_guids & after_guids
    
    for guid in added_guids:
        changes["accounts"]["added"].append(after.accounts[guid].to_dict())
    
    for guid in removed_guids:
        changes["accounts"]["removed"].append(before.accounts[guid].to_dict())
    
    for guid in common_guids:
        before_acc = before.accounts[guid]
        after_acc = after.accounts[guid]
        
        if before_acc.to_dict() != after_acc.to_dict():
            changes["accounts"]["modified"].append({
                "guid": guid,
                "before": before_acc.to_dict(),
                "after": after_acc.to_dict()
            })
    
    # Compare transactions
    before_trans_guids = set(before.transactions.keys())
    after_trans_guids = set(after.transactions.keys())
    
    added_trans = after_trans_guids - before_trans_guids
    removed_trans = before_trans_guids - after_trans_guids
    common_trans = before_trans_guids & after_trans_guids
    
    for guid in added_trans:
        changes["transactions"]["added"].append(after.transactions[guid].to_dict())
    
    for guid in removed_trans:
        changes["transactions"]["removed"].append(before.transactions[guid].to_dict())
    
    for guid in common_trans:
        before_trans = before.transactions[guid]
        after_trans = after.transactions[guid]
        
        # Check if transaction was fixed or broken
        before_had_error = before_trans.error is not None
        after_has_error = after_trans.error is not None
        
        if before_had_error and not after_has_error:
            # Transaction was fixed!
            changes["transactions"]["fixed"].append({
                "guid": guid,
                "description": after_trans.description,
                "before": before_trans.to_dict(),
                "after": after_trans.to_dict(),
                "fix_summary": _summarize_fix(before_trans, after_trans)
            })
        elif not before_had_error and after_has_error:
            # Transaction was broken!
            changes["transactions"]["broken"].append({
                "guid": guid,
                "description": after_trans.description,
                "before": before_trans.to_dict(),
                "after": after_trans.to_dict()
            })
        elif before_trans.to_dict() != after_trans.to_dict():
            # Transaction was modified
            changes["transactions"]["modified"].append({
                "guid": guid,
                "description": after_trans.description,
                "before": before_trans.to_dict(),
                "after": after_trans.to_dict()
            })
    
    # Generate summary
    changes["summary"] = {
        "accounts_added": len(changes["accounts"]["added"]),
        "accounts_removed": len(changes["accounts"]["removed"]),
        "accounts_modified": len(changes["accounts"]["modified"]),
        "transactions_added": len(changes["transactions"]["added"]),
        "transactions_removed": len(changes["transactions"]["removed"]),
        "transactions_modified": len(changes["transactions"]["modified"]),
        "transactions_fixed": len(changes["transactions"]["fixed"]),
        "transactions_broken": len(changes["transactions"]["broken"])
    }
    
    logger.info(f"Comparison complete: {changes['summary']}")
    
    return changes


def _summarize_fix(before: TransactionSnapshot, after: TransactionSnapshot) -> dict:
    """
    Summarize what changed to fix a transaction.
    
    Args:
        before: Transaction state before fix.
        after: Transaction state after fix.
        
    Returns:
        Dictionary describing the fix.
    """
    summary = {}
    
    # Check date changes
    if before.post_date != after.post_date:
        summary["post_date"] = {
            "before": before.post_date,
            "after": after.post_date
        }
    
    if before.enter_date != after.enter_date:
        summary["enter_date"] = {
            "before": before.enter_date,
            "after": after.enter_date
        }
    
    # Check split count
    if before.split_count != after.split_count:
        summary["split_count"] = {
            "before": before.split_count,
            "after": after.split_count
        }
    
    # Check error
    summary["error_resolved"] = before.error
    
    return summary


def format_comparison_text(changes: dict) -> str:
    """
    Format comparison results as human-readable text.
    
    Args:
        changes: Changes dictionary from compare_snapshots.
        
    Returns:
        Formatted text report.
    """
    lines = []
    lines.append("=" * 80)
    lines.append("DATABASE SNAPSHOT COMPARISON")
    lines.append("=" * 80)
    lines.append("")
    lines.append(f"Before: {changes['timestamp_before']}")
    lines.append(f"After:  {changes['timestamp_after']}")
    lines.append("")
    
    # Summary
    summary = changes["summary"]
    lines.append("SUMMARY")
    lines.append("-" * 80)
    lines.append(f"Accounts:     +{summary['accounts_added']} / -{summary['accounts_removed']} / ~{summary['accounts_modified']}")
    lines.append(f"Transactions: +{summary['transactions_added']} / -{summary['transactions_removed']} / ~{summary['transactions_modified']}")
    lines.append(f"Fixed:        {summary['transactions_fixed']} transaction(s) repaired")
    lines.append(f"Broken:       {summary['transactions_broken']} transaction(s) damaged")
    lines.append("")
    
    # Fixed transactions (most important!)
    if changes["transactions"]["fixed"]:
        lines.append("=" * 80)
        lines.append(f"FIXED TRANSACTIONS ({len(changes['transactions']['fixed'])})")
        lines.append("=" * 80)
        lines.append("")
        
        for i, fix in enumerate(changes["transactions"]["fixed"], 1):
            lines.append(f"{i}. {fix['description']} (GUID: {fix['guid']})")
            lines.append("")
            lines.append("   BEFORE:")
            lines.append(f"     Post Date:  {fix['before']['post_date']}")
            lines.append(f"     Enter Date: {fix['before']['enter_date']}")
            lines.append(f"     Splits:     {fix['before']['split_count']}")
            lines.append(f"     Error:      {fix['before']['error']}")
            lines.append("")
            lines.append("   AFTER:")
            lines.append(f"     Post Date:  {fix['after']['post_date']}")
            lines.append(f"     Enter Date: {fix['after']['enter_date']}")
            lines.append(f"     Splits:     {fix['after']['split_count']}")
            lines.append(f"     Error:      {fix['after']['error']}")
            lines.append("")
            
            # Show what changed
            fix_summary = fix.get("fix_summary", {})
            if fix_summary:
                lines.append("   CHANGES:")
                for field, change in fix_summary.items():
                    if field == "error_resolved":
                        lines.append(f"     ✓ Resolved: {change}")
                    elif isinstance(change, dict):
                        lines.append(f"     ✓ {field}: '{change['before']}' → '{change['after']}'")
                    else:
                        lines.append(f"     ✓ {field}: {change}")
                lines.append("")
    
    # Broken transactions
    if changes["transactions"]["broken"]:
        lines.append("=" * 80)
        lines.append(f"BROKEN TRANSACTIONS ({len(changes['transactions']['broken'])})")
        lines.append("=" * 80)
        lines.append("")
        
        for i, broken in enumerate(changes["transactions"]["broken"], 1):
            lines.append(f"{i}. {broken['description']} (GUID: {broken['guid']})")
            lines.append(f"   New Error: {broken['after']['error']}")
            lines.append("")
    
    # Modified transactions
    if changes["transactions"]["modified"]:
        lines.append("=" * 80)
        lines.append(f"MODIFIED TRANSACTIONS ({len(changes['transactions']['modified'])})")
        lines.append("=" * 80)
        lines.append("")
        
        for i, mod in enumerate(changes["transactions"]["modified"], 1):
            lines.append(f"{i}. {mod['description']} (GUID: {mod['guid']})")
            
            # Show key differences
            before = mod['before']
            after = mod['after']
            
            if before['post_date'] != after['post_date']:
                lines.append(f"   Post Date: {before['post_date']} → {after['post_date']}")
            if before['description'] != after['description']:
                lines.append(f"   Description: {before['description']} → {after['description']}")
            if before['split_count'] != after['split_count']:
                lines.append(f"   Splits: {before['split_count']} → {after['split_count']}")
            
            lines.append("")
    
    lines.append("=" * 80)
    
    return "\n".join(lines)
