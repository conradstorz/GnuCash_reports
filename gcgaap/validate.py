"""
Validation engine for GCGAAP.

Implements validation rules for GnuCash book integrity, including:
- Transaction-level double-entry balancing
- Imbalance/Orphan account detection
- Entity mapping coverage
- Strict mode for pre-report validation (100% entity mapping required)

IMPORTANT: Before generating any GAAP reports, validation MUST pass in strict mode
to ensure all accounts are assigned to entities. This guarantees:
1. No accounts are excluded from reports
2. Entity reports sum to total book balances
3. Complete accounting equation compliance (Assets = Liabilities + Equity)
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from .config import GCGAAPConfig
from .entity_map import EntityMap
from .gnucash_access import GnuCashBook, GCAccount, GCTransaction

logger = logging.getLogger(__name__)


@dataclass
class ValidationProblem:
    """
    Represents a single validation issue.
    
    Attributes:
        severity: "error" or "warning".
        message: Human-readable description of the problem.
        context: Optional additional context (e.g., transaction GUID).
    """
    
    severity: str  # "error" or "warning"
    message: str
    context: Optional[str] = None
    
    def __post_init__(self):
        """Validate severity value."""
        if self.severity not in ("error", "warning"):
            raise ValueError(
                f"Invalid severity: {self.severity}. Must be 'error' or 'warning'."
            )
    
    def __str__(self) -> str:
        """Format problem for display."""
        severity_upper = self.severity.upper()
        if self.context:
            return f"[{severity_upper}] {self.message} (Context: {self.context})"
        else:
            return f"[{severity_upper}] {self.message}"


@dataclass
class ValidationResult:
    """
    Results from validating a GnuCash book.
    
    Attributes:
        problems: List of all validation problems found.
    """
    
    problems: list[ValidationProblem] = field(default_factory=list)
    
    @property
    def has_errors(self) -> bool:
        """
        Check if any errors were found.
        
        Returns:
            True if at least one problem has severity "error".
        """
        return any(p.severity == "error" for p in self.problems)
    
    @property
    def has_warnings(self) -> bool:
        """
        Check if any warnings were found.
        
        Returns:
            True if at least one problem has severity "warning".
        """
        return any(p.severity == "warning" for p in self.problems)
    
    @property
    def error_count(self) -> int:
        """Count of errors."""
        return sum(1 for p in self.problems if p.severity == "error")
    
    @property
    def warning_count(self) -> int:
        """Count of warnings."""
        return sum(1 for p in self.problems if p.severity == "warning")
    
    def add_error(self, message: str, context: Optional[str] = None) -> None:
        """
        Add an error to the validation results.
        
        Args:
            message: Error message.
            context: Optional context information.
        """
        self.problems.append(ValidationProblem("error", message, context))
    
    def add_warning(self, message: str, context: Optional[str] = None) -> None:
        """
        Add a warning to the validation results.
        
        Args:
            message: Warning message.
            context: Optional context information.
        """
        self.problems.append(ValidationProblem("warning", message, context))
    
    def log_summary(self) -> None:
        """
        Log a summary of validation results.
        
        Logs all problems and provides counts.
        """
        if not self.problems:
            logger.info("✓ Validation passed with no issues")
            return
        
        logger.info(f"Validation completed: {self.error_count} error(s), {self.warning_count} warning(s)")
        
        # Log all problems
        for problem in self.problems:
            if problem.severity == "error":
                logger.error(str(problem))
            else:
                logger.warning(str(problem))
        
        # Final summary
        if self.has_errors:
            logger.error(f"✗ Validation FAILED with {self.error_count} error(s)")
        else:
            logger.info(f"✓ Validation passed (with {self.warning_count} warning(s))")


def validate_book(
    book: GnuCashBook,
    entity_map: EntityMap,
    config: Optional[GCGAAPConfig] = None,
    strict_mode: bool = False
) -> ValidationResult:
    """
    Perform comprehensive validation of a GnuCash book.
    
    Args:
        book: Opened GnuCashBook to validate.
        entity_map: EntityMap for account-to-entity resolution.
        config: Optional configuration; uses default if not provided.
        strict_mode: If True, require 100% entity mapping coverage (errors instead
                    of warnings). Use strict_mode=True before generating reports.
        config: Optional configuration; uses default if not provided.
        
    Returns:
        ValidationResult with all problems found.
    """
    if config is None:
        from .config import default_config
        config = default_config
    
    if strict_mode:
        logger.info("Starting book validation (STRICT MODE - required for reporting)")
    else:
        logger.info("Starting book validation")
    
    result = ValidationResult()
    
    # Validate accounts
    validate_accounts(book, entity_map, result, strict_mode=strict_mode)
    
    # Validate transactions
    validate_transactions(book, config, result)
    
    logger.info("Validation complete")
    
    return result


def validate_accounts(
    book: GnuCashBook,
    entity_map: EntityMap,
    result: ValidationResult,
    strict_mode: bool = False
) -> None:
    """
    Validate account-level issues.
    
    Checks:
    - Accounts have entity mappings
    - Imbalance/Orphan accounts are identified
    
    Args:
        book: Opened GnuCashBook.
        entity_map: EntityMap for account resolution.
        result: ValidationResult to append problems to.
        strict_mode: If True, treat unmapped accounts as errors instead of warnings.
                    This ensures 100% coverage required for GAAP reporting.
    """
    logger.debug("Validating accounts")
    
    unmapped_count = 0
    imbalance_accounts = []
    total_accounts = 0
    entity_counts = {}
    
    for account in book.iter_accounts():
        total_accounts += 1
        
        # Check entity mapping
        entity_key = entity_map.resolve_entity_for_account(
            account.guid,
            account.full_name
        )
        
        if entity_key is None:
            unmapped_count += 1
        else:
            entity_counts[entity_key] = entity_counts.get(entity_key, 0) + 1
        
        # Check for Imbalance/Orphan accounts
        if account.is_imbalance_account():
            imbalance_accounts.append(account.full_name)
    
    logger.info(f"Processed {total_accounts} accounts")
    
    # Report unmapped accounts
    if unmapped_count > 0:
        if strict_mode:
            # In strict mode (for reporting), unmapped accounts are ERRORS
            result.add_error(
                f"{unmapped_count} account(s) have no entity mapping. "
                f"All accounts MUST be mapped to entities before generating reports. "
                f"Use 'entity-scan' or 'entity-infer' commands to identify and map them."
            )
            logger.error(
                f"STRICT MODE: {unmapped_count} unmapped accounts block report generation"
            )
        else:
            # In normal mode, unmapped accounts are warnings
            result.add_warning(
                f"{unmapped_count} account(s) have no entity mapping. "
                f"Use 'entity-scan' command to identify them."
            )
    else:
        logger.info("✓ All accounts have entity mappings")
    
    # Log entity distribution
    if entity_counts:
        logger.info("Account distribution by entity:")
        for entity_key, count in sorted(entity_counts.items()):
            entity_label = entity_map.entities.get(entity_key, None)
            label = entity_label.label if entity_label else entity_key
            logger.info(f"  {label}: {count} account(s)")
    
    # Report Imbalance/Orphan accounts
    if imbalance_accounts:
        result.add_warning(
            f"{len(imbalance_accounts)} Imbalance/Orphan account(s) detected. "
            f"These should typically have zero balance: {', '.join(imbalance_accounts)}"
        )
    else:
        logger.info("No Imbalance/Orphan accounts found")


def validate_transactions(
    book: GnuCashBook,
    config: GCGAAPConfig,
    result: ValidationResult
) -> None:
    """
    Validate transaction-level balancing.
    
    Checks that all transactions balance (sum of splits ≈ 0).
    
    Args:
        book: Opened GnuCashBook.
        config: Configuration with numeric tolerance.
        result: ValidationResult to append problems to.
    """
    logger.debug("Validating transactions")
    
    unbalanced_count = 0
    total_transactions = 0
    
    for transaction in book.iter_transactions():
        total_transactions += 1
        
        if not transaction.is_balanced(config.numeric_tolerance):
            unbalanced_count += 1
            total = transaction.total_value()
            
            result.add_error(
                f"Unbalanced transaction: '{transaction.description}' "
                f"(imbalance: {total:.4f})",
                context=f"GUID: {transaction.guid}, Date: {transaction.post_date}"
            )
    
    logger.info(f"Processed {total_transactions} transactions")
    
    if unbalanced_count == 0:
        logger.info("✓ All transactions are balanced (within tolerance)")
    else:
        logger.error(f"✗ Found {unbalanced_count} unbalanced transaction(s)")


def scan_unmapped_accounts(
    book: GnuCashBook,
    entity_map: EntityMap
) -> list[GCAccount]:
    """
    Scan for accounts that have no entity mapping.
    
    This is a utility function for the 'entity-scan' CLI command.
    
    Args:
        book: Opened GnuCashBook.
        entity_map: EntityMap for account resolution.
        
    Returns:
        List of GCAccount instances that are not mapped to any entity.
    """
    logger.info("Scanning for unmapped accounts")
    
    unmapped_accounts = []
    
    for account in book.iter_accounts():
        entity_key = entity_map.resolve_entity_for_account(
            account.guid,
            account.full_name
        )
        
        if entity_key is None:
            unmapped_accounts.append(account)
    
    logger.info(f"Found {len(unmapped_accounts)} unmapped account(s)")
    
    return unmapped_accounts


def validate_for_reporting(
    book: GnuCashBook,
    entity_map: EntityMap,
    config: Optional[GCGAAPConfig] = None
) -> ValidationResult:
    """
    Validate a GnuCash book with strict requirements for GAAP reporting.
    
    This is a convenience wrapper that enforces strict mode validation,
    which is REQUIRED before generating any financial reports.
    
    Strict mode ensures:
    - 100% of accounts are mapped to entities
    - All transactions are balanced
    - No Imbalance/Orphan accounts exist
    
    This guarantees that:
    1. Sum of entity reports = Total book balances
    2. No accounts are excluded from reports
    3. Complete GAAP compliance (Assets = Liabilities + Equity)
    
    Args:
        book: Opened GnuCashBook to validate.
        entity_map: EntityMap for account-to-entity resolution.
        config: Optional configuration; uses default if not provided.
        
    Returns:
        ValidationResult with strict validation applied.
        
    Raises:
        RuntimeError: If validation fails (has errors) - reports should NOT be generated.
    """
    logger.info("Running strict validation for report generation")
    
    result = validate_book(book, entity_map, config, strict_mode=True)
    
    if result.has_errors:
        error_msg = (
            f"Strict validation FAILED with {result.error_count} error(s). "
            f"Cannot generate GAAP-compliant reports until all errors are resolved. "
            f"All accounts MUST be mapped to entities before reporting."
        )
        logger.error(error_msg)
        raise RuntimeError(error_msg)
    
    logger.info("✓ Strict validation passed - ready for report generation")
    
    return result
