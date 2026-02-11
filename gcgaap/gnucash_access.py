"""
GnuCash data access abstraction layer.

Provides a stable, read-only interface for accessing GnuCash book data,
hiding the specifics of the underlying library (piecash) and allowing
for potential future library changes or multiple backends.
"""

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Optional

logger = logging.getLogger(__name__)


@dataclass
class GCAccount:
    """
    Representation of a GnuCash account.
    
    Attributes:
        guid: Unique identifier for the account.
        full_name: Colon-separated full account name path
                   (e.g., "Assets:Checking:Alpha LLC").
        type: GnuCash account type (e.g., "ASSET", "LIABILITY", "EQUITY").
        commodity_symbol: Currency code or commodity ticker (e.g., "USD", "AAPL").
        parent_guid: GUID of parent account, if any.
    """
    
    guid: str
    full_name: str
    type: str
    commodity_symbol: str
    parent_guid: Optional[str] = None
    
    def is_imbalance_account(self) -> bool:
        """
        Check if this account is an Imbalance or Orphan account.
        
        Returns:
            True if the account name starts with "Imbalance" or "Orphan".
        """
        name_lower = self.full_name.lower()
        return name_lower.startswith("imbalance") or name_lower.startswith("orphan")


@dataclass
class GCTransactionSplit:
    """
    Representation of a split within a GnuCash transaction.
    
    Attributes:
        account_guid: GUID of the account this split belongs to.
        value: Numeric value of the split in the account's commodity.
               Sign conventions follow GnuCash/piecash conventions.
        quantity: Quantity in the transaction's commodity (for multi-commodity).
        memo: Optional memo text for this split.
    """
    
    account_guid: str
    value: float
    quantity: Optional[float] = None
    memo: Optional[str] = None


@dataclass
class GCTransaction:
    """
    Representation of a GnuCash transaction.
    
    Attributes:
        guid: Unique identifier for the transaction.
        post_date: Date the transaction was posted (as string YYYY-MM-DD).
        description: Transaction description.
        splits: List of splits that make up this transaction.
    """
    
    guid: str
    post_date: str
    description: str
    splits: list[GCTransactionSplit]
    
    def total_value(self) -> float:
        """
        Calculate the sum of all split values.
        
        For a balanced transaction, this should be zero (within tolerance).
        
        Returns:
            Sum of all split values.
        """
        total = sum(split.value for split in self.splits)
        return total
    
    def is_balanced(self, tolerance: float = 0.01) -> bool:
        """
        Check if this transaction is balanced.
        
        Args:
            tolerance: Maximum absolute difference to consider balanced.
            
        Returns:
            True if the absolute total is within tolerance of zero.
        """
        return abs(self.total_value()) <= tolerance


class GnuCashBook:
    """
    Context-managed abstraction for read-only access to a GnuCash book.
    
    This class wraps the underlying piecash library and provides a stable
    interface for iterating over accounts and transactions.
    
    Usage:
        with GnuCashBook(path) as book:
            for account in book.iter_accounts():
                print(account.full_name)
    """
    
    def __init__(self, path: Path):
        """
        Initialize the GnuCash book accessor.
        
        Args:
            path: Path to the GnuCash book file (.gnucash or .db).
        """
        self.path = path
        self._book = None
        self._session = None
        
        logger.info(f"Initializing GnuCash book access for: {path}")
    
    def __enter__(self) -> "GnuCashBook":
        """
        Open the GnuCash book for reading.
        
        Returns:
            Self for use in with statement.
            
        Raises:
            FileNotFoundError: If the book file does not exist.
            Exception: If the book cannot be opened.
        """
        if not self.path.exists():
            raise FileNotFoundError(f"GnuCash book file not found: {self.path}")
        
        try:
            import piecash
            
            logger.debug(f"Opening GnuCash book: {self.path}")
            
            # Open in read-only mode with do_backup=False to prevent modifications
            self._book = piecash.open_book(
                str(self.path),
                readonly=True,
                do_backup=False
            )
            
            logger.info("GnuCash book opened successfully")
            
        except ImportError:
            logger.error("piecash library not available. Install with: pip install piecash")
            raise
        except Exception as e:
            logger.error(f"Failed to open GnuCash book: {e}")
            raise
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Close the GnuCash book.
        
        Args:
            exc_type: Exception type if an exception occurred.
            exc_val: Exception value if an exception occurred.
            exc_tb: Exception traceback if an exception occurred.
        """
        if self._book is not None:
            try:
                self._book.close()
                logger.debug("GnuCash book closed")
            except Exception as e:
                logger.warning(f"Error closing GnuCash book: {e}")
            finally:
                self._book = None
    
    def iter_accounts(self) -> Iterable[GCAccount]:
        """
        Iterate over all accounts in the book.
        
        Yields:
            GCAccount instances for each account in the book.
            
        Raises:
            RuntimeError: If called outside of context manager.
        """
        if self._book is None:
            raise RuntimeError("Book not opened. Use within 'with' statement.")
        
        logger.debug("Iterating over accounts")
        
        for account in self._book.accounts:
            # Build full account name path
            full_name = account.fullname if hasattr(account, 'fullname') else str(account)
            
            # Get parent GUID if it exists
            parent_guid = None
            if account.parent and account.parent.guid:
                parent_guid = str(account.parent.guid)
            
            yield GCAccount(
                guid=str(account.guid),
                full_name=full_name,
                type=account.type,
                commodity_symbol=account.commodity.mnemonic,
                parent_guid=parent_guid
            )
    
    def iter_transactions(self) -> Iterable[GCTransaction]:
        """
        Iterate over all transactions in the book.
        
        Yields:
            GCTransaction instances for each transaction in the book.
            Skips transactions with data integrity issues (logged as errors).
            
        Raises:
            RuntimeError: If called outside of context manager.
            ValueError: If a transaction has critical data corruption that prevents iteration.
        """
        if self._book is None:
            raise RuntimeError("Book not opened. Use within 'with' statement.")
        
        logger.debug("Iterating over transactions")
        
        transaction_count = 0
        error_transactions = []  # Collect all error details
        
        for transaction in self._book.transactions:
            try:
                # Try to access basic transaction properties first
                trans_guid = str(transaction.guid)
                trans_desc = transaction.description if transaction.description else "(No description)"
                
                # Try to get account names from splits BEFORE trying to parse date
                # (the error might happen when accessing splits due to datetime issues)
                account_info = []
                split_count = 0
                try:
                    for split in transaction.splits:
                        split_count += 1
                        try:
                            account_name = split.account.name if split.account else "Unknown"
                            account_info.append(account_name)
                        except Exception:
                            account_info.append("(Error reading account)")
                except Exception as split_error:
                    # Error accessing splits - collect details and continue
                    accounts_str = ", ".join(account_info) if account_info else "(Unable to read splits)"
                    
                    error_details = (
                        f"GUID: {trans_guid}\n"
                        f"    Description: {trans_desc}\n"
                        f"    Accounts: {accounts_str}\n"
                        f"    Split Count: {split_count}\n"
                        f"    Error: {str(split_error)}"
                    )
                    
                    logger.error(f"Transaction has data integrity error:\n{error_details}")
                    error_transactions.append(error_details)
                    continue  # Skip this transaction and continue with next
                
                # Try to access post_date - this is where datetime errors occur
                try:
                    post_date_str = transaction.post_date.strftime("%Y-%m-%d")
                except (ValueError, AttributeError, TypeError) as e:
                    # Invalid or missing date - collect details and continue
                    
                    accounts_str = ", ".join(account_info[:3]) if account_info else "Unable to read accounts"
                    if len(account_info) > 3:
                        accounts_str += f" (and {len(account_info) - 3} more)"
                    
                    error_details = (
                        f"GUID: {trans_guid}\n"
                        f"    Description: {trans_desc}\n"
                        f"    Accounts: {accounts_str}\n"
                        f"    Error: {str(e)}"
                    )
                    
                    logger.error(f"Transaction has invalid date:\n{error_details}")
                    error_transactions.append(error_details)
                    continue  # Skip this transaction and continue with next
                
                # Convert splits - this can also fail with datetime errors
                splits = []
                for split in transaction.splits:
                    # Convert Decimal to float for simplicity
                    value = float(split.value) if isinstance(split.value, Decimal) else split.value
                    quantity = float(split.quantity) if isinstance(split.quantity, Decimal) else split.quantity
                    
                    splits.append(GCTransactionSplit(
                        account_guid=str(split.account.guid),
                        value=value,
                        quantity=quantity,
                        memo=split.memo if split.memo else None
                    ))
                
                transaction_count += 1
                yield GCTransaction(
                    guid=trans_guid,
                    post_date=post_date_str,
                    description=trans_desc,
                    splits=splits
                )
                
            except ValueError:
                # Should not happen anymore since we're catching and continuing
                raise
            except Exception as e:
                # Log other unexpected errors
                logger.error(f"Unexpected error processing transaction: {e}", exc_info=True)
                # Try to collect details if possible
                try:
                    error_details = (
                        f"GUID: {trans_guid}\n"
                        f"    Description: {trans_desc}\n"
                        f"    Error: {str(e)}"
                    )
                    error_transactions.append(error_details)
                except:
                    error_transactions.append(f"Unknown transaction error: {str(e)}")
                continue
        
        # After processing all transactions, report errors if any
        if error_transactions:
            error_summary = "\n\n".join([f"Transaction {i+1}:\n{details}" for i, details in enumerate(error_transactions)])
            logger.error(f"Found {len(error_transactions)} transaction(s) with data integrity issues")
            raise ValueError(
                f"Found {len(error_transactions)} transaction(s) with data integrity errors:\n\n{error_summary}"
            )
        
        logger.debug(f"Successfully iterated {transaction_count} transactions")
    
    def get_account_by_guid(self, guid: str) -> Optional[GCAccount]:
        """
        Retrieve a specific account by its GUID.
        
        Args:
            guid: The account GUID to look up.
            
        Returns:
            GCAccount if found, None otherwise.
            
        Raises:
            RuntimeError: If called outside of context manager.
        """
        if self._book is None:
            raise RuntimeError("Book not opened. Use within 'with' statement.")
        
        # This is a simple implementation; could be optimized with caching
        for account in self.iter_accounts():
            if account.guid == guid:
                return account
        
        return None
    
    def get_account_balances(
        self, 
        as_of_date: date,
        account_guids: Optional[list[str]] = None
    ) -> dict[str, float]:
        """
        Calculate account balances as of a specific date.
        
        Computes the balance for each account by summing all transaction splits
        up to and including the specified date. Only includes transactions where
        post_date <= as_of_date.
        
        Args:
            as_of_date: Date for balance calculation (inclusive).
            account_guids: Optional list of specific account GUIDs to calculate.
                          If None, calculates for all accounts.
        
        Returns:
            Dictionary mapping account GUID to balance (float).
            Accounts with zero balance are included.
            
        Raises:
            RuntimeError: If called outside of context manager.
        """
        if self._book is None:
            raise RuntimeError("Book not opened. Use within 'with' statement.")
        
        logger.debug(f"Calculating account balances as of {as_of_date}")
        
        # Initialize balances for all requested accounts
        balances = defaultdict(float)
        
        # If specific accounts requested, initialize them
        if account_guids:
            for guid in account_guids:
                balances[guid] = 0.0
        else:
            # Initialize all accounts to zero
            for account in self.iter_accounts():
                balances[account.guid] = 0.0
        
        # Process all transactions up to the specified date
        transaction_count = 0
        for transaction in self.iter_transactions():
            # Parse transaction date
            txn_date = datetime.strptime(transaction.post_date, "%Y-%m-%d").date()
            
            # Skip transactions after the as_of_date
            if txn_date > as_of_date:
                continue
            
            transaction_count += 1
            
            # Add splits to account balances
            for split in transaction.splits:
                # If filtering by account_guids, skip others
                if account_guids and split.account_guid not in account_guids:
                    continue
                
                balances[split.account_guid] += split.value
        
        logger.debug(
            f"Processed {transaction_count} transactions for balance calculation"
        )
        
        return dict(balances)
    
    def get_account_balance(
        self, 
        account_guid: str,
        as_of_date: date
    ) -> float:
        """
        Get the balance of a single account as of a specific date.
        
        Convenience method that wraps get_account_balances() for a single account.
        
        Args:
            account_guid: The account GUID.
            as_of_date: Date for balance calculation (inclusive).
            
        Returns:
            Account balance as float.
            
        Raises:
            RuntimeError: If called outside of context manager.
            KeyError: If account_guid is not found.
        """
        balances = self.get_account_balances(as_of_date, [account_guid])
        
        if account_guid not in balances:
            raise KeyError(f"Account GUID not found: {account_guid}")
        
        return balances[account_guid]


def parse_date(date_str: str) -> date:
    """
    Parse a date string in YYYY-MM-DD format.
    
    Args:
        date_str: Date string in YYYY-MM-DD format.
        
    Returns:
        date object.
        
    Raises:
        ValueError: If date_str is not in correct format.
    """
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError as e:
        raise ValueError(
            f"Invalid date format: '{date_str}'. Expected YYYY-MM-DD."
        ) from e
