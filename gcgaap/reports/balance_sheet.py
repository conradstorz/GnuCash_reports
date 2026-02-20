"""
Balance Sheet report generation.

Generates GAAP-style Balance Sheets with strict accounting equation
enforcement (Assets = Liabilities + Equity).
"""

import csv
import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from io import StringIO
from typing import Optional

from ..config import GCGAAPConfig
from ..entity_map import EntityMap
from ..gnucash_access import GnuCashBook, GCAccount, parse_date
from ..validate import validate_for_reporting

logger = logging.getLogger(__name__)


# Account type classification mappings
ASSET_TYPES = {
    "ASSET", "BANK", "CASH", "STOCK", "MUTUAL", "RECEIVABLE",
    "TRADING", "CREDIT"  # Credit cards are negative liabilities = assets in some contexts
}

LIABILITY_TYPES = {
    "LIABILITY", "PAYABLE", "CREDIT"  # Credit cards are typically liabilities
}

EQUITY_TYPES = {
    "EQUITY"
}

INCOME_TYPES = {
    "INCOME"
}

EXPENSE_TYPES = {
    "EXPENSE"
}


def classify_account_type(account: GCAccount) -> str:
    """
    Classify a GnuCash account into Balance Sheet or Income Statement category.
    
    Args:
        account: Account to classify.
        
    Returns:
        One of: "ASSET", "LIABILITY", "EQUITY", "INCOME", "EXPENSE", or "OTHER"
    """
    acct_type = account.type.upper()
    
    # Direct classification
    if acct_type in ASSET_TYPES:
        # Special case: CREDIT type can be either asset or liability
        # If named "Credit Card", it's a liability
        if acct_type == "CREDIT" and "credit" in account.full_name.lower():
            return "LIABILITY"
        return "ASSET"
    elif acct_type in LIABILITY_TYPES:
        return "LIABILITY"
    elif acct_type in EQUITY_TYPES:
        return "EQUITY"
    elif acct_type in INCOME_TYPES:
        return "INCOME"
    elif acct_type in EXPENSE_TYPES:
        return "EXPENSE"
    else:
        logger.warning(
            f"Unknown account type '{acct_type}' for account: {account.full_name}"
        )
        return "OTHER"


@dataclass
class BalanceSheetLine:
    """
    A single line item in a Balance Sheet.
    
    Attributes:
        account_guid: Account GUID.
        account_name: Full account name.
        account_type: GnuCash account type.
        balance: Account balance.
        level: Indentation level for display (0 = top-level).
    """
    
    account_guid: str
    account_name: str
    account_type: str
    balance: float
    level: int = 0


@dataclass
class BalanceSheet:
    """
    GAAP-style Balance Sheet representation.
    
    Attributes:
        as_of_date: Balance sheet date.
        entity_key: Entity key (None for consolidated).
        entity_label: Human-readable entity name.
        assets: List of asset line items.
        liabilities: List of liability line items.
        equity: List of equity line items.
        currency: Currency symbol (e.g., "USD").
    """
    
    as_of_date: date
    entity_key: Optional[str] = None
    entity_label: str = "Consolidated"
    assets: list[BalanceSheetLine] = field(default_factory=list)
    liabilities: list[BalanceSheetLine] = field(default_factory=list)
    equity: list[BalanceSheetLine] = field(default_factory=list)
    currency: str = "USD"
    
    @property
    def total_assets(self) -> float:
        """Sum of all asset balances."""
        return sum(line.balance for line in self.assets)
    
    @property
    def total_liabilities(self) -> float:
        """Sum of all liability balances."""
        return sum(line.balance for line in self.liabilities)
    
    @property
    def total_equity(self) -> float:
        """Sum of all equity balances."""
        return sum(line.balance for line in self.equity)
    
    @property
    def total_liabilities_and_equity(self) -> float:
        """Sum of liabilities and equity."""
        return self.total_liabilities + self.total_equity
    
    def check_balance(self, tolerance: float = 0.01) -> tuple[bool, float]:
        """
        Check if the accounting equation holds: Assets = Liabilities + Equity.
        
        Args:
            tolerance: Numeric tolerance for balance check.
            
        Returns:
            Tuple of (is_balanced, delta) where delta = Assets - (Liabilities + Equity).
        """
        delta = self.total_assets - self.total_liabilities_and_equity
        is_balanced = abs(delta) <= tolerance
        return is_balanced, delta


def generate_balance_sheet(
    book: GnuCashBook,
    entity_map: EntityMap,
    as_of_date_str: str,
    entity_key: Optional[str] = None,
    config: Optional[GCGAAPConfig] = None
) -> BalanceSheet:
    """
    Generate a GAAP-compliant Balance Sheet.
    
    CRITICAL: This function enforces strict validation to ensure:
    - 100% of accounts are mapped to entities
    - All transactions are balanced
    - Complete accounting equation compliance
    
    Args:
        book: Opened GnuCashBook.
        entity_map: EntityMap for account resolution.
        as_of_date_str: Date string in YYYY-MM-DD format.
        entity_key: Optional entity key for entity-specific report.
                   If None, generates consolidated report.
        config: Optional configuration; uses default if not provided.
        
    Returns:
        BalanceSheet instance.
        
    Raises:
        RuntimeError: If strict validation fails (unmapped accounts exist).
        ValueError: If accounting equation doesn't balance.
    """
    if config is None:
        from ..config import default_config
        config = default_config
    
    # Parse date
    as_of_date = parse_date(as_of_date_str)
    
    logger.info(f"Generating Balance Sheet as of {as_of_date}")
    if entity_key:
        logger.info(f"Entity: {entity_key}")
    else:
        logger.info("Type: Consolidated (all entities)")
    
    # STEP 1: MANDATORY strict validation
    logger.info("Step 1: Running strict validation (required for GAAP compliance)")
    validate_for_reporting(book, entity_map, config)
    logger.info("[OK] Strict validation passed")
    
    # STEP 2: Get all accounts and balances
    logger.info("Step 2: Calculating account balances")
    all_accounts = {acc.guid: acc for acc in book.iter_accounts()}
    balances = book.get_account_balances(as_of_date)
    logger.info(f"Calculated balances for {len(balances)} accounts")
    
    # STEP 3: Filter accounts by entity (if specified)
    filtered_accounts = {}
    for guid, account in all_accounts.items():
        resolved_entity = entity_map.resolve_entity_for_account(guid, account.full_name)
        
        if entity_key:
            # Entity-specific report
            if resolved_entity == entity_key:
                filtered_accounts[guid] = account
        else:
            # Consolidated report - include all accounts
            filtered_accounts[guid] = account
    
    logger.info(f"Filtered to {len(filtered_accounts)} accounts for this report")
    
    # STEP 4: Classify and organize accounts
    balance_sheet = BalanceSheet(
        as_of_date=as_of_date,
        entity_key=entity_key,
        entity_label=(
            entity_map.entities[entity_key].label 
            if entity_key and entity_key in entity_map.entities 
            else "Consolidated"
        )
    )
    
    # Track income and expenses to calculate retained earnings
    total_income_balance = 0.0  # Sum of INCOME account balances (negative in GnuCash)
    total_expense_balance = 0.0  # Sum of EXPENSE account balances (positive in GnuCash)
    
    for guid, account in filtered_accounts.items():
        balance = balances.get(guid, 0.0)
        
        # Skip zero-balance accounts (optional - could include them)
        if abs(balance) < config.numeric_tolerance:
            continue
        
        classification = classify_account_type(account)
        
        # Track income and expenses for Retained Earnings calculation
        if classification == "INCOME":
            total_income_balance += balance  # Negative in GnuCash
            continue  # Don't add to Balance Sheet directly
        elif classification == "EXPENSE":
            total_expense_balance += balance  # Positive in GnuCash
            continue  # Don't add to Balance Sheet directly
        
        # CRITICAL: GnuCash stores LIABILITY and EQUITY accounts with negative balances
        # (credits are negative). For Balance Sheet display, we need to show them as
        # positive values. Negate the balance for these account types.
        display_balance = balance
        if classification in ("LIABILITY", "EQUITY"):
            display_balance = -balance
        
        line = BalanceSheetLine(
            account_guid=guid,
            account_name=account.full_name,
            account_type=account.type,
            balance=display_balance,
            level=account.full_name.count(':')  # Indentation based on depth
        )
        
        if classification == "ASSET":
            balance_sheet.assets.append(line)
        elif classification == "LIABILITY":
            balance_sheet.liabilities.append(line)
        elif classification == "EQUITY":
            balance_sheet.equity.append(line)
    
    # Calculate and add Retained Earnings (Net Income) to Equity
    # In GnuCash: Income is negative, Expenses are positive
    # Net Income = -Income - Expenses = -(Income + Expenses)
    # For display: show as positive value in Equity section
    retained_earnings = -(total_income_balance + total_expense_balance)
    
    if abs(retained_earnings) >= config.numeric_tolerance:
        retained_earnings_line = BalanceSheetLine(
            account_guid="RETAINED_EARNINGS",  # Synthetic account
            account_name="Retained Earnings (Net Income)",
            account_type="EQUITY",
            balance=retained_earnings,
            level=0
        )
        balance_sheet.equity.append(retained_earnings_line)
        logger.info(f"Added Retained Earnings: {retained_earnings:,.2f}")
    
    # Sort each section by account name
    balance_sheet.assets.sort(key=lambda x: x.account_name)
    balance_sheet.liabilities.sort(key=lambda x: x.account_name)
    balance_sheet.equity.sort(key=lambda x: x.account_name)
    
    logger.info(f"Classified: {len(balance_sheet.assets)} assets, "
                f"{len(balance_sheet.liabilities)} liabilities, "
                f"{len(balance_sheet.equity)} equity accounts")
    
    # STEP 5: Verify accounting equation
    logger.info("Step 5: Verifying accounting equation (Assets = Liabilities + Equity)")
    is_balanced, delta = balance_sheet.check_balance(config.numeric_tolerance)
    
    if not is_balanced:
        error_msg = (
            f"ACCOUNTING EQUATION VIOLATION: Balance Sheet does not balance!\n"
            f"Assets: {balance_sheet.total_assets:,.2f}\n"
            f"Liabilities: {balance_sheet.total_liabilities:,.2f}\n"
            f"Equity: {balance_sheet.total_equity:,.2f}\n"
            f"Imbalance (A - L - E): {delta:,.2f}\n"
            f"This indicates a serious data integrity issue."
        )
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    logger.info("[OK] Accounting equation verified (within tolerance)")
    logger.info(f"Total Assets: {balance_sheet.total_assets:,.2f}")
    logger.info(f"Total Liabilities: {balance_sheet.total_liabilities:,.2f}")
    logger.info(f"Total Equity: {balance_sheet.total_equity:,.2f}")
    
    return balance_sheet


def format_as_text(balance_sheet: BalanceSheet) -> str:
    """
    Format a Balance Sheet as human-readable text.
    
    Args:
        balance_sheet: BalanceSheet to format.
        
    Returns:
        Formatted text string.
    """
    output = StringIO()
    
    # Header
    output.write("=" * 80 + "\n")
    output.write(f"BALANCE SHEET\n")
    output.write(f"{balance_sheet.entity_label}\n")
    output.write(f"As of {balance_sheet.as_of_date.strftime('%B %d, %Y')}\n")
    output.write(f"Currency: {balance_sheet.currency}\n")
    output.write("=" * 80 + "\n\n")
    
    # Assets section
    output.write("ASSETS\n")
    output.write("-" * 80 + "\n")
    for line in balance_sheet.assets:
        indent = "  " * line.level
        output.write(f"{indent}{line.account_name:<60} {line.balance:>15,.2f}\n")
    output.write("-" * 80 + "\n")
    output.write(f"{'TOTAL ASSETS':<60} {balance_sheet.total_assets:>15,.2f}\n")
    output.write("\n")
    
    # Liabilities section
    output.write("LIABILITIES\n")
    output.write("-" * 80 + "\n")
    for line in balance_sheet.liabilities:
        indent = "  " * line.level
        output.write(f"{indent}{line.account_name:<60} {line.balance:>15,.2f}\n")
    output.write("-" * 80 + "\n")
    output.write(f"{'TOTAL LIABILITIES':<60} {balance_sheet.total_liabilities:>15,.2f}\n")
    output.write("\n")
    
    # Equity section
    output.write("EQUITY\n")
    output.write("-" * 80 + "\n")
    for line in balance_sheet.equity:
        indent = "  " * line.level
        output.write(f"{indent}{line.account_name:<60} {line.balance:>15,.2f}\n")
    output.write("-" * 80 + "\n")
    output.write(f"{'TOTAL EQUITY':<60} {balance_sheet.total_equity:>15,.2f}\n")
    output.write("\n")
    
    # Summary
    output.write("=" * 80 + "\n")
    output.write(f"{'TOTAL LIABILITIES AND EQUITY':<60} {balance_sheet.total_liabilities_and_equity:>15,.2f}\n")
    output.write("=" * 80 + "\n")
    
    # Verification
    is_balanced, delta = balance_sheet.check_balance()
    if is_balanced:
        output.write(f"\n[OK] ACCOUNTING EQUATION VERIFIED: Assets = Liabilities + Equity\n")
    else:
        output.write(f"\n[X] WARNING: Imbalance of {delta:,.2f}\n")
    
    return output.getvalue()


def format_as_csv(balance_sheet: BalanceSheet) -> str:
    """
    Format a Balance Sheet as CSV.
    
    Args:
        balance_sheet: BalanceSheet to format.
        
    Returns:
        CSV string.
    """
    output = StringIO()
    writer = csv.writer(output)
    
    # Header rows
    writer.writerow(["Balance Sheet"])
    writer.writerow([balance_sheet.entity_label])
    writer.writerow([f"As of {balance_sheet.as_of_date.strftime('%Y-%m-%d')}"])
    writer.writerow([])  # Blank row
    
    # Column headers
    writer.writerow(["Section", "Account", "Account Type", "Balance"])
    
    # Assets
    for line in balance_sheet.assets:
        writer.writerow(["ASSETS", line.account_name, line.account_type, f"{line.balance:.2f}"])
    writer.writerow(["ASSETS", "TOTAL ASSETS", "", f"{balance_sheet.total_assets:.2f}"])
    writer.writerow([])  # Blank row
    
    # Liabilities
    for line in balance_sheet.liabilities:
        writer.writerow(["LIABILITIES", line.account_name, line.account_type, f"{line.balance:.2f}"])
    writer.writerow(["LIABILITIES", "TOTAL LIABILITIES", "", f"{balance_sheet.total_liabilities:.2f}"])
    writer.writerow([])  # Blank row
    
    # Equity
    for line in balance_sheet.equity:
        writer.writerow(["EQUITY", line.account_name, line.account_type, f"{line.balance:.2f}"])
    writer.writerow(["EQUITY", "TOTAL EQUITY", "", f"{balance_sheet.total_equity:.2f}"])
    writer.writerow([])  # Blank row
    
    # Summary
    writer.writerow(["SUMMARY", "Total Liabilities and Equity", "", f"{balance_sheet.total_liabilities_and_equity:.2f}"])
    
    return output.getvalue()


def format_as_json(balance_sheet: BalanceSheet) -> str:
    """
    Format a Balance Sheet as JSON.
    
    Args:
        balance_sheet: BalanceSheet to format.
        
    Returns:
        JSON string.
    """
    def line_to_dict(line: BalanceSheetLine) -> dict:
        return {
            "account_guid": line.account_guid,
            "account_name": line.account_name,
            "account_type": line.account_type,
            "balance": round(line.balance, 2),
            "level": line.level
        }
    
    is_balanced, delta = balance_sheet.check_balance()
    
    data = {
        "balance_sheet": {
            "entity": balance_sheet.entity_label,
            "entity_key": balance_sheet.entity_key,
            "as_of_date": balance_sheet.as_of_date.strftime("%Y-%m-%d"),
            "currency": balance_sheet.currency,
            "assets": {
                "line_items": [line_to_dict(line) for line in balance_sheet.assets],
                "total": round(balance_sheet.total_assets, 2)
            },
            "liabilities": {
                "line_items": [line_to_dict(line) for line in balance_sheet.liabilities],
                "total": round(balance_sheet.total_liabilities, 2)
            },
            "equity": {
                "line_items": [line_to_dict(line) for line in balance_sheet.equity],
                "total": round(balance_sheet.total_equity, 2)
            },
            "summary": {
                "total_assets": round(balance_sheet.total_assets, 2),
                "total_liabilities": round(balance_sheet.total_liabilities, 2),
                "total_equity": round(balance_sheet.total_equity, 2),
                "total_liabilities_and_equity": round(balance_sheet.total_liabilities_and_equity, 2),
                "accounting_equation_balanced": is_balanced,
                "imbalance": round(delta, 2) if not is_balanced else 0.0
            }
        }
    }
    
    return json.dumps(data, indent=2)


@dataclass
class BalanceCheckResult:
    """
    Structured result from a single entity balance check.

    Attributes:
        entity_key: Entity key, or None for consolidated.
        entity_label: Human-readable entity name.
        balanced: True if the accounting equation holds.
        total_assets: Total asset balance.
        total_liabilities: Total liability balance.
        total_equity: Total equity balance.
        imbalance: Imbalance amount (A - L - E).
        error: Error message if the check failed for a non-imbalance reason.
    """

    entity_key: Optional[str]
    entity_label: str
    balanced: bool
    total_assets: float = 0.0
    total_liabilities: float = 0.0
    total_equity: float = 0.0
    imbalance: float = 0.0
    error: Optional[str] = None


def check_entity_balance(
    book,
    entity_map: EntityMap,
    as_of_date_str: str,
    entity_key: Optional[str],
    config: GCGAAPConfig,
) -> BalanceCheckResult:
    """
    Run a balance sheet for one entity and return a structured result.

    Calls generate_balance_sheet and catches ValueError so callers don't
    have to parse the error message string.

    Args:
        book: Open GnuCashBook context.
        entity_map: Loaded EntityMap.
        as_of_date_str: Date string in YYYY-MM-DD format.
        entity_key: Entity key, or None for consolidated.
        config: GCGAAPConfig instance.

    Returns:
        BalanceCheckResult with balance data or error information.
    """
    if entity_key is None:
        label = "Consolidated (All Entities)"
    else:
        label = entity_map.entities[entity_key].label if entity_key in entity_map.entities else entity_key

    try:
        bs = generate_balance_sheet(
            book=book,
            entity_map=entity_map,
            as_of_date_str=as_of_date_str,
            entity_key=entity_key,
            config=config,
        )
        return BalanceCheckResult(
            entity_key=entity_key,
            entity_label=label,
            balanced=True,
            total_assets=bs.total_assets,
            total_liabilities=bs.total_liabilities,
            total_equity=bs.total_equity,
            imbalance=0.0,
        )
    except ValueError as e:
        error_str = str(e)
        if "Imbalance (A - L - E):" in error_str:
            assets = liabilities = equity = imbalance = 0.0
            for line in error_str.split("\n"):
                if line.startswith("Assets:"):
                    assets = float(line.split(":")[1].strip().replace(",", ""))
                elif line.startswith("Liabilities:"):
                    liabilities = float(line.split(":")[1].strip().replace(",", ""))
                elif line.startswith("Equity:"):
                    equity = float(line.split(":")[1].strip().replace(",", ""))
                elif line.startswith("Imbalance"):
                    imbalance = float(line.split(":")[1].strip().replace(",", ""))
            return BalanceCheckResult(
                entity_key=entity_key,
                entity_label=label,
                balanced=False,
                total_assets=assets,
                total_liabilities=liabilities,
                total_equity=equity,
                imbalance=imbalance,
            )
        return BalanceCheckResult(
            entity_key=entity_key,
            entity_label=label,
            balanced=False,
            error=error_str,
        )
