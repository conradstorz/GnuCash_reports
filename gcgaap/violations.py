"""
Violations reporting engine for GCGAAP.

Provides detailed analysis of data quality issues including:
- Imbalanced/orphan transactions
- Entity-level balance violations
- Account mapping issues
- Per-entity accounting equation validation
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional

from .config import GCGAAPConfig
from .entity_map import EntityMap
from .gnucash_access import GnuCashBook, GCAccount, GCTransaction, parse_date

logger = logging.getLogger(__name__)


@dataclass
class ViolationDetail:
    """
    Detailed information about a specific violation.
    
    Attributes:
        category: Violation category (e.g., "IMBALANCED_TRANSACTION", "ENTITY_BALANCE").
        severity: "critical", "error", or "warning".
        message: Human-readable description.
        item_id: Associated item identifier (e.g., transaction GUID, account GUID).
        item_name: Associated item name (e.g., transaction description, account name).
        details: Additional contextual information.
    """
    
    category: str
    severity: str  # "critical", "error", or "warning"
    message: str
    item_id: Optional[str] = None
    item_name: Optional[str] = None
    details: dict = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate severity value."""
        if self.severity not in ("critical", "error", "warning"):
            raise ValueError(
                f"Invalid severity: {self.severity}. "
                f"Must be 'critical', 'error', or 'warning'."
            )


@dataclass
class EntityBalanceInfo:
    """
    Balance information for a single entity.
    
    Attributes:
        entity_key: Entity identifier.
        entity_label: Human-readable entity name.
        total_assets: Total asset value.
        total_liabilities: Total liability value.
        total_equity: Total equity value.
        imbalance: Accounting equation imbalance (Assets - Liabilities - Equity).
        account_count: Number of accounts mapped to this entity.
    """
    
    entity_key: str
    entity_label: str
    total_assets: Decimal
    total_liabilities: Decimal
    total_equity: Decimal
    imbalance: Decimal
    account_count: int
    
    def is_balanced(self, tolerance: float = 0.01) -> bool:
        """Check if entity's accounting equation balances."""
        return abs(float(self.imbalance)) <= tolerance


@dataclass
class ViolationsReport:
    """
    Comprehensive violations report.
    
    Attributes:
        violations: List of all violations found.
        entity_balances: Balance information for each entity.
        total_accounts: Total number of accounts analyzed.
        total_transactions: Total number of transactions analyzed.
        unmapped_accounts: List of accounts without entity mapping.
    """
    
    violations: list[ViolationDetail] = field(default_factory=list)
    entity_balances: dict[str, EntityBalanceInfo] = field(default_factory=dict)
    total_accounts: int = 0
    total_transactions: int = 0
    unmapped_accounts: list[GCAccount] = field(default_factory=list)
    
    @property
    def critical_count(self) -> int:
        """Count of critical violations."""
        return sum(1 for v in self.violations if v.severity == "critical")
    
    @property
    def error_count(self) -> int:
        """Count of error violations."""
        return sum(1 for v in self.violations if v.severity == "error")
    
    @property
    def warning_count(self) -> int:
        """Count of warning violations."""
        return sum(1 for v in self.violations if v.severity == "warning")
    
    @property
    def has_critical(self) -> bool:
        """Check if any critical violations exist."""
        return self.critical_count > 0
    
    @property
    def has_errors(self) -> bool:
        """Check if any errors exist."""
        return self.error_count > 0
    
    def add_violation(
        self,
        category: str,
        severity: str,
        message: str,
        item_id: Optional[str] = None,
        item_name: Optional[str] = None,
        **details
    ) -> None:
        """
        Add a violation to the report.
        
        Args:
            category: Violation category.
            severity: Severity level.
            message: Violation message.
            item_id: Optional item identifier.
            item_name: Optional item name.
            **details: Additional detail fields.
        """
        self.violations.append(
            ViolationDetail(
                category=category,
                severity=severity,
                message=message,
                item_id=item_id,
                item_name=item_name,
                details=details
            )
        )


def generate_violations_report(
    book: GnuCashBook,
    entity_map: EntityMap,
    as_of_date: Optional[date] = None,
    config: Optional[GCGAAPConfig] = None
) -> ViolationsReport:
    """
    Generate a comprehensive violations report.
    
    Args:
        book: Opened GnuCashBook to analyze.
        entity_map: EntityMap for account-to-entity resolution.
        as_of_date: Date for balance calculations. If None, uses current date.
        config: Optional configuration; uses default if not provided.
        
    Returns:
        ViolationsReport with all violations and entity balance info.
    """
    if config is None:
        from .config import default_config
        config = default_config
    
    if as_of_date is None:
        from datetime import date as date_class
        as_of_date = date_class.today()
    
    logger.info(f"Generating comprehensive violations report as of {as_of_date}")
    
    report = ViolationsReport()
    
    # Check 1: Validate transactions (imbalanced, orphans)
    _check_transactions(book, config, report)
    
    # Check 2: Validate account mappings
    _check_account_mappings(book, entity_map, report)
    
    # Check 3: Validate entity-level balances
    _check_entity_balances(book, entity_map, as_of_date, config, report)
    
    # Check 4: Check for imbalance/orphan accounts with non-zero balances
    _check_imbalance_accounts(book, as_of_date, config, report)
    
    logger.info(
        f"Violations report complete: {report.critical_count} critical, "
        f"{report.error_count} errors, {report.warning_count} warnings"
    )
    
    return report


def _check_transactions(
    book: GnuCashBook,
    config: GCGAAPConfig,
    report: ViolationsReport
) -> None:
    """
    Check all transactions for balance violations.
    
    Args:
        book: Opened GnuCashBook.
        config: Configuration with tolerance.
        report: ViolationsReport to append to.
    """
    logger.debug("Checking transactions for violations")
    
    for transaction in book.iter_transactions():
        report.total_transactions += 1
        
        if not transaction.is_balanced(config.numeric_tolerance):
            total = transaction.total_value()
            
            report.add_violation(
                category="IMBALANCED_TRANSACTION",
                severity="critical",
                message=f"Transaction does not balance (imbalance: {total:.4f})",
                item_id=transaction.guid,
                item_name=transaction.description,
                post_date=transaction.post_date,
                imbalance_amount=total,
                split_count=len(transaction.splits)
            )
    
    logger.info(f"Checked {report.total_transactions} transactions")


def _check_account_mappings(
    book: GnuCashBook,
    entity_map: EntityMap,
    report: ViolationsReport
) -> None:
    """
    Check all accounts for entity mapping violations.
    
    Args:
        book: Opened GnuCashBook.
        entity_map: EntityMap for resolution.
        report: ViolationsReport to append to.
    """
    logger.debug("Checking account mappings")
    
    for account in book.iter_accounts():
        report.total_accounts += 1
        
        entity_key = entity_map.resolve_entity_for_account(
            account.guid,
            account.full_name
        )
        
        if entity_key is None:
            report.unmapped_accounts.append(account)
            
            report.add_violation(
                category="UNMAPPED_ACCOUNT",
                severity="error",
                message=f"Account has no entity mapping",
                item_id=account.guid,
                item_name=account.full_name,
                account_type=account.type,
                commodity=account.commodity_symbol
            )
    
    logger.info(f"Checked {report.total_accounts} accounts")


def _check_entity_balances(
    book: GnuCashBook,
    entity_map: EntityMap,
    as_of_date: date,
    config: GCGAAPConfig,
    report: ViolationsReport
) -> None:
    """
    Check accounting equation balance for each entity.
    
    Args:
        book: Opened GnuCashBook.
        entity_map: EntityMap for account resolution.
        as_of_date: Date for balance calculations.
        config: Configuration with tolerance.
        report: ViolationsReport to append to.
    """
    logger.debug("Checking entity-level balances")
    
    # Initialize balance tracking by entity
    entity_balances = defaultdict(lambda: {
        'assets': Decimal('0'),
        'liabilities': Decimal('0'),
        'equity': Decimal('0'),
        'account_count': 0
    })
    
    # Collect all accounts and their balances by entity
    for account in book.iter_accounts():
        entity_key = entity_map.resolve_entity_for_account(
            account.guid,
            account.full_name
        )
        
        # Skip unmapped accounts (already reported above)
        if entity_key is None:
            continue
        
        # Get account balance
        balance = Decimal(str(book.get_account_balance(account.guid, as_of_date)))
        
        # Add to appropriate category
        account_type = account.type.upper()
        
        if account_type in ('ASSET', 'BANK', 'CASH', 'STOCK', 'MUTUAL', 'RECEIVABLE'):
            entity_balances[entity_key]['assets'] += balance
        elif account_type in ('LIABILITY', 'CREDIT', 'PAYABLE'):
            entity_balances[entity_key]['liabilities'] += balance
        elif account_type in ('EQUITY', 'INCOME', 'EXPENSE'):
            entity_balances[entity_key]['equity'] += balance
        else:
            # Unknown account type - report as warning
            report.add_violation(
                category="UNKNOWN_ACCOUNT_TYPE",
                severity="warning",
                message=f"Account has unknown type: {account_type}",
                item_id=account.guid,
                item_name=account.full_name,
                account_type=account_type,
                entity_key=entity_key
            )
        
        entity_balances[entity_key]['account_count'] += 1
    
    # Create EntityBalanceInfo for each entity and check balance
    for entity_key, balances in entity_balances.items():
        entity_def = entity_map.entities.get(entity_key)
        entity_label = entity_def.label if entity_def else entity_key
        
        # Calculate imbalance (Assets should equal Liabilities + Equity)
        # Note: In accounting, liabilities and equity are typically negative in the system
        # so we use: Assets + Liabilities + Equity = 0
        imbalance = balances['assets'] + balances['liabilities'] + balances['equity']
        
        entity_info = EntityBalanceInfo(
            entity_key=entity_key,
            entity_label=entity_label,
            total_assets=balances['assets'],
            total_liabilities=balances['liabilities'],
            total_equity=balances['equity'],
            imbalance=imbalance,
            account_count=balances['account_count']
        )
        
        report.entity_balances[entity_key] = entity_info
        
        # Check if entity balances
        if not entity_info.is_balanced(config.numeric_tolerance):
            # Determine likely causes
            causes = []
            
            if len(report.unmapped_accounts) > 0:
                causes.append(f"{len(report.unmapped_accounts)} unmapped account(s)")
            
            # Check for imbalanced transactions affecting this entity
            imbalanced_txn_count = sum(
                1 for v in report.violations 
                if v.category == "IMBALANCED_TRANSACTION"
            )
            if imbalanced_txn_count > 0:
                causes.append(f"{imbalanced_txn_count} imbalanced transaction(s)")
            
            causes_str = "; likely due to: " + ", ".join(causes) if causes else ""
            
            report.add_violation(
                category="ENTITY_IMBALANCE",
                severity="error",
                message=(
                    f"Entity accounting equation does not balance "
                    f"(imbalance: {float(imbalance):.2f}){causes_str}"
                ),
                item_id=entity_key,
                item_name=entity_label,
                total_assets=float(balances['assets']),
                total_liabilities=float(balances['liabilities']),
                total_equity=float(balances['equity']),
                imbalance=float(imbalance),
                account_count=balances['account_count']
            )
    
    logger.info(f"Checked {len(entity_balances)} entities")


def _check_imbalance_accounts(
    book: GnuCashBook,
    as_of_date: date,
    config: GCGAAPConfig,
    report: ViolationsReport
) -> None:
    """
    Check for Imbalance/Orphan accounts with non-zero balances.
    
    Args:
        book: Opened GnuCashBook.
        as_of_date: Date for balance calculations.
        config: Configuration with tolerance.
        report: ViolationsReport to append to.
    """
    logger.debug("Checking for imbalance/orphan accounts")
    
    for account in book.iter_accounts():
        if account.is_imbalance_account():
            balance = book.get_account_balance(account.guid, as_of_date)
            
            if abs(balance) > config.numeric_tolerance:
                report.add_violation(
                    category="IMBALANCE_ACCOUNT_NONZERO",
                    severity="warning",
                    message=(
                        f"Imbalance/Orphan account has non-zero balance "
                        f"({balance:.2f})"
                    ),
                    item_id=account.guid,
                    item_name=account.full_name,
                    balance=balance,
                    account_type=account.type
                )


def format_violations_report(report: ViolationsReport) -> str:
    """
    Format violations report as human-readable text.
    
    Args:
        report: ViolationsReport to format.
        
    Returns:
        Formatted text report.
    """
    lines = []
    
    lines.append("=" * 80)
    lines.append("GCGAAP DATA QUALITY VIOLATIONS REPORT")
    lines.append("=" * 80)
    lines.append("")
    
    # Summary
    lines.append("SUMMARY")
    lines.append("-" * 80)
    lines.append(f"Total Accounts Analyzed:     {report.total_accounts}")
    lines.append(f"Total Transactions Analyzed: {report.total_transactions}")
    lines.append(f"Entities Analyzed:           {len(report.entity_balances)}")
    lines.append("")
    lines.append(f"Critical Violations:         {report.critical_count}")
    lines.append(f"Errors:                      {report.error_count}")
    lines.append(f"Warnings:                    {report.warning_count}")
    lines.append("")
    
    # Entity Balance Summary
    if report.entity_balances:
        lines.append("ENTITY BALANCE SUMMARY")
        lines.append("-" * 80)
        lines.append(
            f"{'Entity':<30} {'Accounts':>8} {'Assets':>15} {'Liab':>15} "
            f"{'Equity':>15} {'Balance':>10}"
        )
        lines.append("-" * 80)
        
        for entity_key, info in sorted(report.entity_balances.items()):
            status = "✓ OK" if info.is_balanced() else "✗ FAIL"
            lines.append(
                f"{info.entity_label[:30]:<30} "
                f"{info.account_count:>8} "
                f"{float(info.total_assets):>15,.2f} "
                f"{float(info.total_liabilities):>15,.2f} "
                f"{float(info.total_equity):>15,.2f} "
                f"{status:>10}"
            )
        
        lines.append("")
    
    # Violations by Category
    if report.violations:
        lines.append("VIOLATIONS BY CATEGORY")
        lines.append("-" * 80)
        
        # Group by category
        by_category = defaultdict(list)
        for violation in report.violations:
            by_category[violation.category].append(violation)
        
        for category, violations in sorted(by_category.items()):
            lines.append("")
            lines.append(f"{category} ({len(violations)} violation(s))")
            lines.append("-" * 80)
            
            for i, v in enumerate(violations[:10], 1):  # Limit to first 10 per category
                severity_marker = {
                    "critical": "[CRITICAL]",
                    "error": "[ERROR]   ",
                    "warning": "[WARNING] "
                }.get(v.severity, "[UNKNOWN] ")
                
                lines.append(f"{i}. {severity_marker} {v.message}")
                
                if v.item_name:
                    lines.append(f"   Item: {v.item_name}")
                
                if v.item_id:
                    lines.append(f"   ID: {v.item_id}")
                
                if v.details:
                    for key, value in sorted(v.details.items()):
                        if key not in ('item_id', 'item_name'):
                            lines.append(f"   {key}: {value}")
                
                lines.append("")
            
            if len(violations) > 10:
                lines.append(f"   ... and {len(violations) - 10} more {category} violations")
                lines.append("")
    else:
        lines.append("NO VIOLATIONS FOUND")
        lines.append("-" * 80)
        lines.append("✓ All validation checks passed!")
        lines.append("")
    
    # Recommendations
    if report.violations:
        lines.append("RECOMMENDATIONS")
        lines.append("-" * 80)
        
        if report.critical_count > 0:
            lines.append("1. FIX CRITICAL VIOLATIONS FIRST:")
            lines.append("   - Imbalanced transactions indicate data integrity issues")
            lines.append("   - These MUST be corrected in GnuCash before proceeding")
            lines.append("")
        
        if len(report.unmapped_accounts) > 0:
            lines.append("2. MAP ALL ACCOUNTS TO ENTITIES:")
            lines.append(f"   - {len(report.unmapped_accounts)} account(s) need entity mapping")
            lines.append("   - Run: gcgaap entity-scan to see unmapped accounts")
            lines.append("   - Run: gcgaap entity-infer to generate suggested mappings")
            lines.append("")
        
        if any(v.category == "ENTITY_IMBALANCE" for v in report.violations):
            lines.append("3. RESOLVE ENTITY-LEVEL IMBALANCES:")
            lines.append("   - Review entity balance summary above")
            lines.append("   - Entity imbalances often result from:")
            lines.append("     • Unmapped accounts")
            lines.append("     • Imbalanced transactions")
            lines.append("     • Incorrect entity assignments")
            lines.append("")
    
    lines.append("=" * 80)
    
    return "\n".join(lines)
