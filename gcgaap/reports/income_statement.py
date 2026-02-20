"""
Income Statement report generation.

Generates GAAP-style Income Statements (or Statements of Income and Expenses for
individuals) showing revenues and expenses for a date range with hierarchical
account groupings and subtotals.
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
from ..gnucash_access import GnuCashBook, parse_date
from ..validate import validate_for_reporting
from .balance_sheet import classify_account_type

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class IncomeStatementLine:
    """
    A single line in the Income Statement.

    Attributes:
        account_guid: Account GUID (may have synthetic suffix like "_header" or "_total").
        account_name: Display name (last path segment, or "Total X" for totals).
        account_type: GnuCash account type.
        balance: Monetary balance (0.0 for header rows).
        level: Display indentation level (0 = top-level within section).
        is_header: True for parent account name rows that show no balance.
        is_total: True for subtotal / section-total rows.
    """

    account_guid: str
    account_name: str
    account_type: str
    balance: float
    level: int
    is_header: bool = False
    is_total: bool = False


@dataclass
class IncomeStatement:
    """
    GAAP-style Income Statement representation.

    Attributes:
        from_date: Start of reporting period.
        to_date: End of reporting period.
        entity_key: Entity key (None for consolidated).
        entity_label: Human-readable entity name.
        entity_type: "individual", "business", or "structural".
        revenue_lines: Hierarchical list of revenue line items.
        expense_lines: Hierarchical list of expense line items.
        total_revenue: Sum of all revenue for the period.
        total_expenses: Sum of all expenses for the period.
        currency: Currency symbol (e.g., "USD").
    """

    from_date: date
    to_date: date
    entity_key: Optional[str]
    entity_label: str
    entity_type: str
    revenue_lines: list[IncomeStatementLine] = field(default_factory=list)
    expense_lines: list[IncomeStatementLine] = field(default_factory=list)
    total_revenue: float = 0.0
    total_expenses: float = 0.0
    currency: str = "USD"

    @property
    def net_income(self) -> float:
        """Revenue minus expenses."""
        return self.total_revenue - self.total_expenses

    @property
    def report_title(self) -> str:
        """Title adapted to entity type."""
        if self.entity_type == "individual":
            return "STATEMENT OF INCOME AND EXPENSES"
        return "INCOME STATEMENT"

    @property
    def net_income_label(self) -> str:
        """Net income label adapted to entity type."""
        if self.entity_type == "individual":
            return "Net Income (Surplus)" if self.net_income >= 0 else "Net Loss (Deficit)"
        return "Net Income" if self.net_income >= 0 else "Net Loss"


# ---------------------------------------------------------------------------
# Account tree helpers
# ---------------------------------------------------------------------------


def _build_children_map(accounts: dict[str, "GCAccount"]) -> dict[str, list[str]]:
    """
    Build a parent-GUID → [child-GUIDs] mapping from the given account set.

    Only includes parent relationships where both parent and child are in the
    provided account dict (i.e., no cross-section links).

    Args:
        accounts: Dict of guid → GCAccount to consider.

    Returns:
        Dict mapping each parent GUID to a sorted list of child GUIDs.
    """
    children: dict[str, list[str]] = defaultdict(list)
    for guid, account in accounts.items():
        if account.parent_guid and account.parent_guid in accounts:
            children[account.parent_guid].append(guid)
    return dict(children)


def _find_roots(accounts: dict[str, "GCAccount"]) -> list[str]:
    """
    Find accounts whose parent is not present in the given account set.

    These are the top-level nodes when building a display tree.

    Args:
        accounts: Dict of guid → GCAccount to consider.

    Returns:
        List of GUIDs sorted by full_name.
    """
    roots = [
        guid
        for guid, account in accounts.items()
        if account.parent_guid is None or account.parent_guid not in accounts
    ]
    return sorted(roots, key=lambda g: accounts[g].full_name)


def _walk_account_tree(
    guid: str,
    accounts: dict[str, "GCAccount"],
    children_map: dict[str, list[str]],
    balances: dict[str, float],
    sign_factor: float,
    tolerance: float,
    level: int,
) -> tuple[list[IncomeStatementLine], float]:
    """
    Recursively build Income Statement lines for one account subtree.

    For leaf accounts: returns a single ACCOUNT line with its balance.
    For parent accounts: returns a GROUP_HEADER line, all children's lines,
    and a GROUP_TOTAL line with the accumulated subtotal.

    Sign convention:
        sign_factor = -1.0 for INCOME (GnuCash stores credits as negative).
        sign_factor = +1.0 for EXPENSE (GnuCash stores debits as positive).

    Args:
        guid: Root of the subtree to walk.
        accounts: All accounts in this section (INCOME or EXPENSE) for the entity.
        children_map: Pre-built parent → [child] mapping.
        balances: Period account balances from get_period_account_balances().
        sign_factor: Multiplier to convert GnuCash sign to display-positive sign.
        tolerance: Numeric tolerance; lines below this threshold are omitted.
        level: Current display indentation level.

    Returns:
        Tuple of (lines, subtotal) where subtotal is the net contribution of
        this subtree (used by the caller to accumulate its own subtotal without
        double-counting).
    """
    account = accounts[guid]
    child_guids = sorted(
        children_map.get(guid, []),
        key=lambda g: accounts[g].full_name,
    )
    display_name = account.full_name.split(":")[-1]

    if not child_guids:
        # Leaf account: show its balance directly.
        balance = balances.get(guid, 0.0) * sign_factor
        if abs(balance) < tolerance:
            return [], 0.0
        line = IncomeStatementLine(
            account_guid=guid,
            account_name=display_name,
            account_type=account.type,
            balance=balance,
            level=level,
        )
        return [line], balance

    # Parent account: recurse into children first.
    child_lines: list[IncomeStatementLine] = []
    child_total: float = 0.0

    for child_guid in child_guids:
        lines, subtotal = _walk_account_tree(
            child_guid, accounts, children_map, balances, sign_factor, tolerance, level + 1
        )
        child_lines.extend(lines)
        child_total += subtotal

    # Some parent accounts also carry their own transactions (non-placeholder).
    own_balance = balances.get(guid, 0.0) * sign_factor
    if abs(own_balance) >= tolerance and not account.is_placeholder:
        own_line = IncomeStatementLine(
            account_guid=guid + "_own",
            account_name=display_name + " (direct)",
            account_type=account.type,
            balance=own_balance,
            level=level + 1,
        )
        child_lines.insert(0, own_line)
        child_total += own_balance

    if not child_lines:
        return [], 0.0

    header = IncomeStatementLine(
        account_guid=guid + "_header",
        account_name=display_name,
        account_type=account.type,
        balance=0.0,
        level=level,
        is_header=True,
    )
    total_line = IncomeStatementLine(
        account_guid=guid + "_total",
        account_name=f"Total {display_name}",
        account_type=account.type,
        balance=child_total,
        level=level,
        is_total=True,
    )

    return [header] + child_lines + [total_line], child_total


# ---------------------------------------------------------------------------
# Core generation function
# ---------------------------------------------------------------------------


def generate_income_statement(
    book: GnuCashBook,
    entity_map: EntityMap,
    from_date_str: str,
    to_date_str: str,
    entity_key: Optional[str] = None,
    config: Optional[GCGAAPConfig] = None,
) -> IncomeStatement:
    """
    Generate a GAAP-compliant Income Statement for a date range.

    Computes revenue and expense activity for transactions posted between
    from_date and to_date (inclusive), filtered to the specified entity
    (or consolidated across all entities if entity_key is None).

    Args:
        book: Opened GnuCashBook.
        entity_map: EntityMap for account resolution.
        from_date_str: Period start date in YYYY-MM-DD format.
        to_date_str: Period end date in YYYY-MM-DD format.
        entity_key: Optional entity key for entity-specific report.
                   If None, generates consolidated report.
        config: Optional configuration; uses default if not provided.

    Returns:
        IncomeStatement instance.

    Raises:
        RuntimeError: If strict validation fails (unmapped accounts exist).
        ValueError: If date strings are not in YYYY-MM-DD format.
    """
    if config is None:
        from ..config import default_config
        config = default_config

    from_date = parse_date(from_date_str)
    to_date = parse_date(to_date_str)

    if from_date > to_date:
        raise ValueError(
            f"from_date ({from_date_str}) must be on or before to_date ({to_date_str})."
        )

    logger.info(f"Generating Income Statement for period {from_date} to {to_date}")
    if entity_key:
        logger.info(f"Entity: {entity_key}")
    else:
        logger.info("Type: Consolidated (all entities)")

    # STEP 1: Strict validation (required for GAAP compliance).
    logger.info("Step 1: Running strict validation")
    validate_for_reporting(book, entity_map, config)
    logger.info("[OK] Strict validation passed")

    # STEP 2: Collect all accounts, filter by entity.
    logger.info("Step 2: Collecting and filtering accounts")
    all_accounts = {acc.guid: acc for acc in book.iter_accounts()}

    income_accounts: dict[str, "GCAccount"] = {}
    expense_accounts: dict[str, "GCAccount"] = {}

    for guid, account in all_accounts.items():
        resolved_entity = entity_map.resolve_entity_for_account(guid, account.full_name)

        if entity_key and resolved_entity != entity_key:
            continue

        classification = classify_account_type(account)
        if classification == "INCOME":
            income_accounts[guid] = account
        elif classification == "EXPENSE":
            expense_accounts[guid] = account

    logger.info(
        f"Filtered to {len(income_accounts)} income accounts, "
        f"{len(expense_accounts)} expense accounts"
    )

    # STEP 3: Calculate period balances for INCOME and EXPENSE accounts only.
    logger.info("Step 3: Calculating period balances")
    all_period_guids = list(income_accounts.keys()) + list(expense_accounts.keys())
    period_balances = book.get_period_account_balances(
        from_date=from_date,
        to_date=to_date,
        account_guids=all_period_guids if all_period_guids else None,
    )

    # STEP 4: Build hierarchical lines for each section.
    logger.info("Step 4: Building hierarchical account tree")

    # Revenue section (INCOME accounts; negate GnuCash sign for display).
    income_children = _build_children_map(income_accounts)
    income_roots = _find_roots(income_accounts)

    revenue_lines: list[IncomeStatementLine] = []
    total_revenue = 0.0
    for root_guid in income_roots:
        lines, subtotal = _walk_account_tree(
            guid=root_guid,
            accounts=income_accounts,
            children_map=income_children,
            balances=period_balances,
            sign_factor=-1.0,  # GnuCash income is credit (negative)
            tolerance=config.numeric_tolerance,
            level=0,
        )
        revenue_lines.extend(lines)
        total_revenue += subtotal

    # Expense section (EXPENSE accounts; GnuCash sign is already positive).
    expense_children = _build_children_map(expense_accounts)
    expense_roots = _find_roots(expense_accounts)

    expense_lines: list[IncomeStatementLine] = []
    total_expenses = 0.0
    for root_guid in expense_roots:
        lines, subtotal = _walk_account_tree(
            guid=root_guid,
            accounts=expense_accounts,
            children_map=expense_children,
            balances=period_balances,
            sign_factor=1.0,  # GnuCash expense is debit (positive)
            tolerance=config.numeric_tolerance,
            level=0,
        )
        expense_lines.extend(lines)
        total_expenses += subtotal

    # Resolve entity metadata.
    if entity_key and entity_key in entity_map.entities:
        entity_def = entity_map.entities[entity_key]
        entity_label = entity_def.label
        entity_type = entity_def.type
    else:
        entity_label = "Consolidated"
        entity_type = "business"  # Use business-style labels for consolidated

    logger.info(
        f"Revenue: {total_revenue:,.2f} | Expenses: {total_expenses:,.2f} | "
        f"Net: {total_revenue - total_expenses:,.2f}"
    )

    return IncomeStatement(
        from_date=from_date,
        to_date=to_date,
        entity_key=entity_key,
        entity_label=entity_label,
        entity_type=entity_type,
        revenue_lines=revenue_lines,
        expense_lines=expense_lines,
        total_revenue=total_revenue,
        total_expenses=total_expenses,
    )


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------


def _format_line(line: IncomeStatementLine, col_width: int = 60, num_width: int = 15) -> str:
    """
    Render one Income Statement line as a fixed-width text string.

    Header rows show the account name with no balance. Total rows show
    the balance right-justified. Regular account rows show name and balance.

    Args:
        line: The line to format.
        col_width: Width of the account name column.
        num_width: Width of the numeric column.

    Returns:
        Formatted string (no trailing newline).
    """
    indent = "  " * line.level
    name = f"{indent}{line.account_name}"

    if line.is_header:
        return name
    if line.is_total:
        return f"{name:<{col_width}} {line.balance:>{num_width},.2f}"
    return f"{name:<{col_width}} {line.balance:>{num_width},.2f}"


def format_as_text(income_statement: IncomeStatement) -> str:
    """
    Format an Income Statement as human-readable text.

    Args:
        income_statement: IncomeStatement to format.

    Returns:
        Formatted text string.
    """
    out = StringIO()
    sep = "=" * 80
    thin = "-" * 80

    # Header
    out.write(sep + "\n")
    out.write(f"{income_statement.report_title}\n")
    out.write(f"{income_statement.entity_label}\n")
    out.write(
        f"For the period {income_statement.from_date.strftime('%B %d, %Y')} "
        f"to {income_statement.to_date.strftime('%B %d, %Y')}\n"
    )
    out.write(f"Currency: {income_statement.currency}\n")
    out.write(sep + "\n\n")

    # Revenue section
    out.write("REVENUE\n")
    out.write(thin + "\n")
    for line in income_statement.revenue_lines:
        out.write(_format_line(line) + "\n")
    out.write(thin + "\n")
    out.write(f"{'TOTAL REVENUE':<60} {income_statement.total_revenue:>15,.2f}\n")
    out.write("\n")

    # Expenses section
    out.write("EXPENSES\n")
    out.write(thin + "\n")
    for line in income_statement.expense_lines:
        out.write(_format_line(line) + "\n")
    out.write(thin + "\n")
    out.write(f"{'TOTAL EXPENSES':<60} {income_statement.total_expenses:>15,.2f}\n")
    out.write("\n")

    # Net income summary
    out.write(sep + "\n")
    net = income_statement.net_income
    label = income_statement.net_income_label
    out.write(f"{label:<60} {net:>15,.2f}\n")
    out.write(sep + "\n")

    return out.getvalue()


def format_as_csv(income_statement: IncomeStatement) -> str:
    """
    Format an Income Statement as CSV.

    Args:
        income_statement: IncomeStatement to format.

    Returns:
        CSV string.
    """
    out = StringIO()
    writer = csv.writer(out)

    writer.writerow([income_statement.report_title])
    writer.writerow([income_statement.entity_label])
    writer.writerow([
        f"{income_statement.from_date.strftime('%Y-%m-%d')} to "
        f"{income_statement.to_date.strftime('%Y-%m-%d')}"
    ])
    writer.writerow([])
    writer.writerow(["Section", "Account", "Account Type", "Level", "Row Kind", "Balance"])

    def write_lines(section_name: str, lines: list[IncomeStatementLine]) -> None:
        for line in lines:
            kind = "header" if line.is_header else ("total" if line.is_total else "account")
            writer.writerow([
                section_name,
                line.account_name,
                line.account_type,
                line.level,
                kind,
                "" if line.is_header else f"{line.balance:.2f}",
            ])

    write_lines("REVENUE", income_statement.revenue_lines)
    writer.writerow(["REVENUE", "TOTAL REVENUE", "", "", "section_total",
                     f"{income_statement.total_revenue:.2f}"])
    writer.writerow([])

    write_lines("EXPENSES", income_statement.expense_lines)
    writer.writerow(["EXPENSES", "TOTAL EXPENSES", "", "", "section_total",
                     f"{income_statement.total_expenses:.2f}"])
    writer.writerow([])

    writer.writerow(["SUMMARY", income_statement.net_income_label, "", "", "net_income",
                     f"{income_statement.net_income:.2f}"])

    return out.getvalue()


def format_as_json(income_statement: IncomeStatement) -> str:
    """
    Format an Income Statement as JSON.

    Args:
        income_statement: IncomeStatement to format.

    Returns:
        JSON string.
    """
    def line_to_dict(line: IncomeStatementLine) -> dict:
        return {
            "account_guid": line.account_guid,
            "account_name": line.account_name,
            "account_type": line.account_type,
            "balance": round(line.balance, 2),
            "level": line.level,
            "is_header": line.is_header,
            "is_total": line.is_total,
        }

    data = {
        "income_statement": {
            "title": income_statement.report_title,
            "entity": income_statement.entity_label,
            "entity_key": income_statement.entity_key,
            "entity_type": income_statement.entity_type,
            "from_date": income_statement.from_date.strftime("%Y-%m-%d"),
            "to_date": income_statement.to_date.strftime("%Y-%m-%d"),
            "currency": income_statement.currency,
            "revenue": {
                "line_items": [line_to_dict(l) for l in income_statement.revenue_lines],
                "total": round(income_statement.total_revenue, 2),
            },
            "expenses": {
                "line_items": [line_to_dict(l) for l in income_statement.expense_lines],
                "total": round(income_statement.total_expenses, 2),
            },
            "summary": {
                "total_revenue": round(income_statement.total_revenue, 2),
                "total_expenses": round(income_statement.total_expenses, 2),
                "net_income": round(income_statement.net_income, 2),
                "net_income_label": income_statement.net_income_label,
            },
        }
    }

    return json.dumps(data, indent=2)
