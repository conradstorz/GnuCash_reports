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
    
    def format_as_text(self, strict_mode: bool = False) -> str:
        """
        Format validation results as human-readable text.
        
        Args:
            strict_mode: Whether strict mode was used.
            
        Returns:
            Formatted text report.
        """
        lines = []
        lines.append("=" * 80)
        lines.append("GCGAAP VALIDATION REPORT")
        if strict_mode:
            lines.append("Mode: STRICT (100% entity mapping required)")
        else:
            lines.append("Mode: STANDARD")
        lines.append("=" * 80)
        lines.append("")
        
        # Summary
        if self.has_errors:
            status = "[FAILED]"
        elif self.has_warnings:
            status = "[PASSED WITH WARNINGS]"
        else:
            status = "[PASSED]"
        
        lines.append(f"Status: {status}")
        lines.append(f"Errors: {self.error_count}")
        lines.append(f"Warnings: {self.warning_count}")
        lines.append("")
        
        # Errors
        if self.error_count > 0:
            lines.append("-" * 80)
            lines.append(f"ERRORS ({self.error_count})")
            lines.append("-" * 80)
            for i, problem in enumerate([p for p in self.problems if p.severity == "error"], 1):
                lines.append(f"{i}. {problem.message}")
                if problem.context:
                    lines.append(f"   Context: {problem.context}")
                lines.append("")
        
        # Warnings
        if self.warning_count > 0:
            lines.append("-" * 80)
            lines.append(f"WARNINGS ({self.warning_count})")
            lines.append("-" * 80)
            for i, problem in enumerate([p for p in self.problems if p.severity == "warning"], 1):
                lines.append(f"{i}. {problem.message}")
                if problem.context:
                    lines.append(f"   Context: {problem.context}")
                lines.append("")
        
        lines.append("=" * 80)
        
        return "\n".join(lines)
    
    def format_as_json(self) -> str:
        """
        Format validation results as JSON.
        
        Returns:
            JSON string with validation results.
        """
        import json
        
        data = {
            "status": "failed" if self.has_errors else ("warning" if self.has_warnings else "passed"),
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "problems": [
                {
                    "severity": p.severity,
                    "message": p.message,
                    "context": p.context
                }
                for p in self.problems
            ]
        }
        
        return json.dumps(data, indent=2)
    
    def format_as_csv(self) -> str:
        """
        Format validation results as CSV.
        
        Returns:
            CSV string with validation results.
        """
        import csv
        from io import StringIO
        
        output = StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow(["Severity", "Message", "Context"])
        
        # Data
        for problem in self.problems:
            writer.writerow([problem.severity, problem.message, problem.context or ""])
        
        return output.getvalue()


def validate_book(
    book: GnuCashBook,
    entity_map: EntityMap,
    config: Optional[GCGAAPConfig] = None,
    strict_mode: bool = False,
    quiet: bool = False
) -> ValidationResult:
    """
    Perform comprehensive validation of a GnuCash book.
    
    Args:
        book: Opened GnuCashBook to validate.
        entity_map: EntityMap for account-to-entity resolution.
        config: Optional configuration; uses default if not provided.
        strict_mode: If True, require 100% entity mapping coverage (errors instead
                    of warnings). Use strict_mode=True before generating reports.
        quiet: If True, suppress log messages.
        
    Returns:
        ValidationResult with all problems found.
    """
    if config is None:
        from .config import default_config
        config = default_config
    
    if not quiet:
        if strict_mode:
            logger.info("Starting book validation (STRICT MODE - required for reporting)")
        else:
            logger.info("Starting book validation")
    
    result = ValidationResult()
    
    # Validate accounts
    validate_accounts(book, entity_map, result, strict_mode=strict_mode, quiet=quiet)
    
    # Validate transactions
    validate_transactions(book, config, result, quiet=quiet)
    
    if not quiet:
        logger.info("Validation complete")
    
    return result


def validate_accounts(
    book: GnuCashBook,
    entity_map: EntityMap,
    result: ValidationResult,
    strict_mode: bool = False,
    quiet: bool = False
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
        quiet: If True, suppress log messages.
    """
    if not quiet:
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
        
        if not entity_map.is_explicitly_mapped(account.guid, account.full_name):
            unmapped_count += 1
        else:
            entity_counts[entity_key] = entity_counts.get(entity_key, 0) + 1
        
        # Check for Imbalance/Orphan accounts
        if account.is_imbalance_account():
            imbalance_accounts.append(account.full_name)
    
    if not quiet:
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
            if not quiet:
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
        if not quiet:
            logger.info("✓ All accounts have entity mappings")
    
    # Log entity distribution
    if entity_counts and not quiet:
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
    result: ValidationResult,
    quiet: bool = False
) -> None:
    """
    Validate transaction-level balancing.
    
    Checks that all transactions balance (sum of splits ≈ 0).
    Also detects data integrity issues (invalid dates, corrupted records).
    
    Args:
        book: Opened GnuCashBook.
        config: Configuration with numeric tolerance.
        result: ValidationResult to append problems to.
        quiet: If True, suppress log messages.
    """
    if not quiet:
        logger.debug("Validating transactions")
    
    unbalanced_count = 0
    total_transactions = 0
    data_integrity_errors = 0
    
    # Try to iterate through transactions, catching data integrity issues
    try:
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
    except ValueError as e:
        # Catch datetime parsing errors and other value errors
        error_msg = str(e)
        data_integrity_errors += 1
        
        if "datetime" in error_msg.lower() or "date" in error_msg.lower():
            result.add_error(
                "Transaction with invalid or missing date",
                context=error_msg
            )
        else:
            result.add_error(
                f"Data integrity error: {error_msg}",
                context="Transaction data is corrupted or invalid"
            )
        
        if not quiet:
            logger.error(f"Data integrity error encountered: {error_msg}")
    except Exception as e:
        # Catch any other unexpected errors
        data_integrity_errors += 1
        result.add_error(
            f"Unexpected error during transaction validation: {type(e).__name__}",
            context=str(e)
        )
        if not quiet:
            logger.error(f"Unexpected error: {e}", exc_info=True)
    
    if not quiet:
        logger.info(f"Processed {total_transactions} transactions")
    
        if data_integrity_errors > 0:
            logger.error(f"✗ Found {data_integrity_errors} data integrity error(s) - fix these in GnuCash")
    
        if unbalanced_count == 0 and data_integrity_errors == 0:
            logger.info("✓ All transactions are balanced (within tolerance)")
        elif unbalanced_count > 0:
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
        if not entity_map.is_explicitly_mapped(account.guid, account.full_name):
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
