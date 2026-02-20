"""
Trial Balance report generation.

Generates a GAAP-style Trial Balance as of a specific date, listing all accounts
with their debit and credit amounts. Total debits must equal total credits for a
set of books in balance.
"""

import csv
import json
import logging
from dataclasses import dataclass, field
from datetime import date
from io import StringIO
from typing import Optional

from ..config import GCGAAPConfig
from ..entity_map import EntityMap
from ..gnucash_access import GnuCashBook, parse_date
from ..validate import validate_for_reporting
from .balance_sheet import classify_account_type

logger = logging.getLogger(__name__)

# Account types whose natural (normal) balance is a debit.
DEBIT_NORMAL_TYPES = {"ASSET", "EXPENSE"}

# Account types whose natural (normal) balance is a credit.
CREDIT_NORMAL_TYPES = {"LIABILITY", "EQUITY", "INCOME"}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class TrialBalanceLine:
    """
    A single account line in a Trial Balance.

    Attributes:
        account_guid: Account GUID.
        account_name: Full account name path.
        account_type: GnuCash account type.
        classification: High-level classification (ASSET, LIABILITY, etc.).
        debit: Amount in the debit column (0.0 if none).
        credit: Amount in the credit column (0.0 if none).
        level: Indentation level for display (colon depth in full_name).
    """

    account_guid: str
    account_name: str
    account_type: str
    classification: str
    debit: float
    credit: float
    level: int = 0


@dataclass
class TrialBalance:
    """
    GAAP-style Trial Balance representation.

    Attributes:
        as_of_date: Balance date.
        entity_key: Entity key (None for consolidated).
        entity_label: Human-readable entity name.
        lines: All account lines sorted by account name.
        currency: Currency symbol.
    """

    as_of_date: date
    entity_key: Optional[str]
    entity_label: str
    lines: list[TrialBalanceLine] = field(default_factory=list)
    currency: str = "USD"

    @property
    def total_debits(self) -> float:
        """Sum of all debit amounts."""
        return sum(line.debit for line in self.lines)

    @property
    def total_credits(self) -> float:
        """Sum of all credit amounts."""
        return sum(line.credit for line in self.lines)

    def is_balanced(self, tolerance: float = 0.01) -> bool:
        """
        Check whether total debits equal total credits.

        Args:
            tolerance: Maximum acceptable difference.

        Returns:
            True if abs(total_debits - total_credits) <= tolerance.
        """
        return abs(self.total_debits - self.total_credits) <= tolerance

    def imbalance(self) -> float:
        """
        Return the imbalance amount (debits minus credits).

        Returns:
            Difference; 0.0 for a balanced trial balance.
        """
        return self.total_debits - self.total_credits


# ---------------------------------------------------------------------------
# Debit / credit assignment
# ---------------------------------------------------------------------------


def _assign_debit_credit(balance: float, classification: str) -> tuple[float, float]:
    """
    Assign a GnuCash account balance to the correct debit or credit column.

    GnuCash sign conventions:
        ASSET / EXPENSE:     positive balance = debit (normal side)
        LIABILITY / EQUITY / INCOME: negative balance = credit (normal side)

    An account on the wrong side of zero has an abnormal (contra) balance and
    is placed in the opposite column.

    Args:
        balance: Raw GnuCash account balance.
        classification: One of ASSET, LIABILITY, EQUITY, INCOME, EXPENSE, OTHER.

    Returns:
        Tuple of (debit, credit); exactly one will be non-zero.
    """
    if classification in DEBIT_NORMAL_TYPES:
        if balance >= 0.0:
            return balance, 0.0
        return 0.0, -balance
    else:
        # Credit-normal: GnuCash stores as negative for normal credit balance.
        if balance <= 0.0:
            return 0.0, -balance
        return balance, 0.0


# ---------------------------------------------------------------------------
# Core generation function
# ---------------------------------------------------------------------------


def generate_trial_balance(
    book: GnuCashBook,
    entity_map: EntityMap,
    as_of_date_str: str,
    entity_key: Optional[str] = None,
    config: Optional[GCGAAPConfig] = None,
) -> TrialBalance:
    """
    Generate a Trial Balance as of a specific date.

    Lists all accounts with non-zero balances in debit/credit format.
    Verifies that total debits equal total credits.

    Args:
        book: Opened GnuCashBook.
        entity_map: EntityMap for account resolution.
        as_of_date_str: Date string in YYYY-MM-DD format.
        entity_key: Optional entity key for entity-specific report.
                   If None, generates consolidated report.
        config: Optional configuration; uses default if not provided.

    Returns:
        TrialBalance instance.

    Raises:
        RuntimeError: If strict validation fails.
        ValueError: If date string is not in YYYY-MM-DD format.
    """
    if config is None:
        from ..config import default_config
        config = default_config

    as_of_date = parse_date(as_of_date_str)

    logger.info(f"Generating Trial Balance as of {as_of_date}")
    if entity_key:
        logger.info(f"Entity: {entity_key}")

    # STEP 1: Strict validation.
    logger.info("Step 1: Running strict validation")
    validate_for_reporting(book, entity_map, config)
    logger.info("[OK] Strict validation passed")

    # STEP 2: Get all accounts and filter by entity.
    logger.info("Step 2: Collecting accounts and balances")
    all_accounts = {acc.guid: acc for acc in book.iter_accounts()}
    balances = book.get_account_balances(as_of_date)

    # STEP 3: Build trial balance lines.
    lines: list[TrialBalanceLine] = []

    for guid, account in all_accounts.items():
        resolved_entity = entity_map.resolve_entity_for_account(guid, account.full_name)

        if entity_key and resolved_entity != entity_key:
            continue

        balance = balances.get(guid, 0.0)

        # Skip accounts with no activity.
        if abs(balance) < config.numeric_tolerance:
            continue

        classification = classify_account_type(account)
        debit, credit = _assign_debit_credit(balance, classification)

        lines.append(TrialBalanceLine(
            account_guid=guid,
            account_name=account.full_name,
            account_type=account.type,
            classification=classification,
            debit=debit,
            credit=credit,
            level=account.full_name.count(":"),
        ))

    # Sort by account name for consistent display.
    lines.sort(key=lambda ln: ln.account_name)

    # Resolve entity metadata.
    if entity_key and entity_key in entity_map.entities:
        entity_label = entity_map.entities[entity_key].label
    else:
        entity_label = "Consolidated"

    trial_balance = TrialBalance(
        as_of_date=as_of_date,
        entity_key=entity_key,
        entity_label=entity_label,
        lines=lines,
    )

    logger.info(
        f"Trial Balance: {len(lines)} accounts | "
        f"Debits: {trial_balance.total_debits:,.2f} | "
        f"Credits: {trial_balance.total_credits:,.2f}"
    )

    is_bal = trial_balance.is_balanced(config.numeric_tolerance)
    if is_bal:
        logger.info("[OK] Trial Balance is balanced (Debits = Credits)")
    else:
        logger.warning(
            f"[!] Trial Balance imbalance: {trial_balance.imbalance():,.2f}"
        )

    return trial_balance


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------


def format_as_text(trial_balance: TrialBalance) -> str:
    """
    Format a Trial Balance as human-readable text.

    Args:
        trial_balance: TrialBalance to format.

    Returns:
        Formatted text string.
    """
    out = StringIO()
    sep = "=" * 100
    thin = "-" * 100

    out.write(sep + "\n")
    out.write("TRIAL BALANCE\n")
    out.write(f"{trial_balance.entity_label}\n")
    out.write(f"As of {trial_balance.as_of_date.strftime('%B %d, %Y')}\n")
    out.write(f"Currency: {trial_balance.currency}\n")
    out.write(sep + "\n\n")

    # Column headers
    out.write(f"{'Account':<65} {'Type':<12} {'Debit':>15} {'Credit':>15}\n")
    out.write(thin + "\n")

    for line in trial_balance.lines:
        indent = "  " * line.level
        name = f"{indent}{line.account_name}"
        debit_str = f"{line.debit:>15,.2f}" if line.debit else ""
        credit_str = f"{line.credit:>15,.2f}" if line.credit else ""
        out.write(f"{name:<65} {line.classification:<12} {debit_str:>15} {credit_str:>15}\n")

    out.write(thin + "\n")
    out.write(
        f"{'TOTALS':<65} {'':<12} "
        f"{trial_balance.total_debits:>15,.2f} "
        f"{trial_balance.total_credits:>15,.2f}\n"
    )
    out.write(sep + "\n")

    if trial_balance.is_balanced():
        out.write("\n[OK] TRIAL BALANCE IS BALANCED (Debits = Credits)\n")
    else:
        out.write(f"\n[X] IMBALANCE: {trial_balance.imbalance():,.2f}\n")

    return out.getvalue()


def format_as_csv(trial_balance: TrialBalance) -> str:
    """
    Format a Trial Balance as CSV.

    Args:
        trial_balance: TrialBalance to format.

    Returns:
        CSV string.
    """
    out = StringIO()
    writer = csv.writer(out)

    writer.writerow(["Trial Balance"])
    writer.writerow([trial_balance.entity_label])
    writer.writerow([f"As of {trial_balance.as_of_date.strftime('%Y-%m-%d')}"])
    writer.writerow([])
    writer.writerow(["Account", "Account Type", "Classification", "Level", "Debit", "Credit"])

    for line in trial_balance.lines:
        writer.writerow([
            line.account_name,
            line.account_type,
            line.classification,
            line.level,
            f"{line.debit:.2f}" if line.debit else "",
            f"{line.credit:.2f}" if line.credit else "",
        ])

    writer.writerow([])
    writer.writerow([
        "TOTALS", "", "", "",
        f"{trial_balance.total_debits:.2f}",
        f"{trial_balance.total_credits:.2f}",
    ])

    return out.getvalue()


def format_as_json(trial_balance: TrialBalance) -> str:
    """
    Format a Trial Balance as JSON.

    Args:
        trial_balance: TrialBalance to format.

    Returns:
        JSON string.
    """
    def line_to_dict(line: TrialBalanceLine) -> dict:
        return {
            "account_guid": line.account_guid,
            "account_name": line.account_name,
            "account_type": line.account_type,
            "classification": line.classification,
            "debit": round(line.debit, 2),
            "credit": round(line.credit, 2),
            "level": line.level,
        }

    data = {
        "trial_balance": {
            "entity": trial_balance.entity_label,
            "entity_key": trial_balance.entity_key,
            "as_of_date": trial_balance.as_of_date.strftime("%Y-%m-%d"),
            "currency": trial_balance.currency,
            "accounts": [line_to_dict(l) for l in trial_balance.lines],
            "summary": {
                "total_debits": round(trial_balance.total_debits, 2),
                "total_credits": round(trial_balance.total_credits, 2),
                "is_balanced": trial_balance.is_balanced(),
                "imbalance": round(trial_balance.imbalance(), 2),
            },
        }
    }

    return json.dumps(data, indent=2)
