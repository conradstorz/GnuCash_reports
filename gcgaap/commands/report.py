"""
Report command group for gcgaap.

Commands: balance-sheet, balance-check
"""

import logging
import sys

import click

from ..config import GCGAAPConfig
from ..entity_map import EntityMap
from ..gnucash_access import GnuCashBook
from ..reports.balance_sheet import (
    generate_balance_sheet,
    format_as_text,
    format_as_csv,
    format_as_json,
    check_entity_balance,
)
from ..reports.income_statement import (
    generate_income_statement,
    format_as_text as is_format_text,
    format_as_csv as is_format_csv,
    format_as_json as is_format_json,
)
from ..reports.trial_balance import (
    generate_trial_balance,
    format_as_text as tb_format_text,
    format_as_csv as tb_format_csv,
    format_as_json as tb_format_json,
)
from ._options import (
    book_file_option,
    entity_map_option,
    as_of_option,
    from_date_option,
    to_date_option,
    format_option,
    entity_filter_option,
)

logger = logging.getLogger(__name__)


@click.group(name="report")
def report_group():
    """Financial report generation commands."""


@report_group.command(name="balance-sheet")
@book_file_option
@entity_map_option()
@as_of_option(required=True)
@click.option(
    "--entity",
    type=str,
    default=None,
    help="Entity key for entity-specific report (omit for consolidated).",
)
@click.option(
    "--format",
    type=click.Choice(["text", "csv", "json"], case_sensitive=False),
    default="text",
    help="Output format (default: text).",
)
def balance_sheet(book_file, entity_map_file, as_of, entity, format):
    """
    Generate a GAAP-compliant Balance Sheet report.

    Produces a Balance Sheet as of a specified date, either for a specific
    entity or consolidated across all entities.

    IMPORTANT: This command automatically runs strict validation to ensure:
    - 100% of accounts are mapped to entities
    - All transactions are balanced
    - Accounting equation holds (Assets = Liabilities + Equity)

    The report will fail if:
    - Any accounts are unmapped
    - The accounting equation doesn't balance
    - Strict validation fails for any reason
    """
    logger.info("=== GCGAAP Balance Sheet Report ===")

    try:
        config = GCGAAPConfig()
        entity_map = EntityMap.load(entity_map_file)

        if entity and entity not in entity_map.entities:
            click.echo(f"Error: Entity '{entity}' not found in entity map.")
            click.echo(f"Available entities: {', '.join(entity_map.entities.keys())}")
            sys.exit(1)

        with GnuCashBook(book_file) as book:
            balance_sheet_obj = generate_balance_sheet(
                book=book,
                entity_map=entity_map,
                as_of_date_str=as_of,
                entity_key=entity,
                config=config,
            )

        if format.lower() == "csv":
            output = format_as_csv(balance_sheet_obj)
        elif format.lower() == "json":
            output = format_as_json(balance_sheet_obj)
        else:
            output = format_as_text(balance_sheet_obj)

        click.echo()
        click.echo(output)
        sys.exit(0)

    except ValueError as e:
        logger.error(f"Report generation failed: {e}")
        click.echo(f"\n[ERROR] {e}")
        sys.exit(1)
    except RuntimeError as e:
        logger.error(f"Validation failed: {e}")
        click.echo(f"\n[FAIL] VALIDATION FAILED: {e}")
        click.echo("\nFix validation errors before generating reports.")
        click.echo("Use 'gcgaap db validate --strict' to see detailed validation results.")
        sys.exit(1)
    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error generating balance sheet: {e}", exc_info=True)
        sys.exit(1)


@report_group.command(name="balance-check")
@book_file_option
@entity_map_option()
@as_of_option(required=True)
def balance_check(book_file, entity_map_file, as_of):
    """
    Quick balance check for all entities and consolidated.

    Generates a summary report showing which entities have balanced
    accounting equations and which have imbalances. This is useful
    for quickly identifying data integrity issues across all entities.

    Shows:
    - Consolidated (all entities) balance status
    - Individual entity balance status
    - Imbalance amounts for entities that don't balance
    """
    logger.info("=== GCGAAP Balance Check (All Entities) ===")

    try:
        config = GCGAAPConfig()
        entity_map = EntityMap.load(entity_map_file)

        with GnuCashBook(book_file) as book:
            click.echo("\n" + "=" * 80)
            click.echo(f"BALANCE CHECK REPORT - As of {as_of}")
            click.echo("=" * 80)

            # Consolidated
            click.echo("\nChecking consolidated (all entities)...")
            results = [check_entity_balance(book, entity_map, as_of, None, config)]

            # Per entity
            for entity_key, entity_config in entity_map.entities.items():
                if entity_key == "unassigned":
                    continue
                click.echo(f"Checking {entity_config.label}...")
                results.append(
                    check_entity_balance(book, entity_map, as_of, entity_key, config)
                )

        # Display summary
        click.echo("\n" + "=" * 80)
        click.echo("SUMMARY")
        click.echo("=" * 80)

        balanced_count = sum(1 for r in results if r.balanced)
        imbalanced_count = len(results) - balanced_count

        if balanced_count > 0:
            click.echo(f"\n[OK] BALANCED ({balanced_count}):")
            click.echo("-" * 80)
            for result in results:
                if result.balanced:
                    click.echo(
                        f"  [OK] {result.entity_label:40s} "
                        f"A: ${result.total_assets:>15,.2f}  "
                        f"L: ${result.total_liabilities:>15,.2f}  "
                        f"E: ${result.total_equity:>15,.2f}"
                    )

        if imbalanced_count > 0:
            click.echo(f"\n[X] IMBALANCED ({imbalanced_count}):")
            click.echo("-" * 80)
            for result in results:
                if not result.balanced:
                    if result.error:
                        click.echo(f"  [X] {result.entity_label:40s} ERROR: {result.error}")
                    else:
                        click.echo(
                            f"  [X] {result.entity_label:40s} "
                            f"A: ${result.total_assets:>15,.2f}  "
                            f"L: ${result.total_liabilities:>15,.2f}  "
                            f"E: ${result.total_equity:>15,.2f}  "
                            f"Imbalance: ${result.imbalance:>15,.2f}"
                        )

        click.echo("\n" + "=" * 80)

        if imbalanced_count == 0:
            click.echo("[OK] ALL ENTITIES BALANCED - Books are in good order!")
            sys.exit(0)
        else:
            click.echo(f"[X] {imbalanced_count} entity/entities have accounting equation violations")
            click.echo("  Review and fix imbalanced entities before generating reports.")
            sys.exit(1)

    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error during balance check: {e}", exc_info=True)
        click.echo(f"\n[X] Balance check failed: {e}")
        sys.exit(1)


@report_group.command(name="income-statement")
@book_file_option
@entity_map_option()
@from_date_option(required=True)
@to_date_option(required=True)
@entity_filter_option
@format_option(("text", "csv", "json"))
def income_statement(book_file, entity_map_file, from_date, to_date, entity, format):
    """
    Generate a GAAP-compliant Income Statement for a date range.

    Shows revenues and expenses for the specified period with hierarchical
    account groupings and subtotals, ending with net income (or net loss).

    The report title adapts to entity type:
      - Business entities:  Income Statement
      - Individual entities: Statement of Income and Expenses

    Use --entity to generate a report for one entity, or omit for consolidated.
    """
    logger.info("=== GCGAAP Income Statement Report ===")

    try:
        config = GCGAAPConfig()
        entity_map = EntityMap.load(entity_map_file)

        if entity and entity not in entity_map.entities:
            click.echo(f"Error: Entity '{entity}' not found in entity map.")
            click.echo(f"Available entities: {', '.join(entity_map.entities.keys())}")
            sys.exit(1)

        with GnuCashBook(book_file) as book:
            report = generate_income_statement(
                book=book,
                entity_map=entity_map,
                from_date_str=from_date,
                to_date_str=to_date,
                entity_key=entity,
                config=config,
            )

        if format.lower() == "csv":
            output = is_format_csv(report)
        elif format.lower() == "json":
            output = is_format_json(report)
        else:
            output = is_format_text(report)

        click.echo()
        click.echo(output)
        sys.exit(0)

    except ValueError as e:
        logger.error(f"Report generation failed: {e}")
        click.echo(f"\n[ERROR] {e}")
        sys.exit(1)
    except RuntimeError as e:
        logger.error(f"Validation failed: {e}")
        click.echo(f"\n[FAIL] VALIDATION FAILED: {e}")
        click.echo("\nFix validation errors before generating reports.")
        click.echo("Use 'gcgaap db validate --strict' to see detailed validation results.")
        sys.exit(1)
    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error generating income statement: {e}", exc_info=True)
        sys.exit(1)


@report_group.command(name="trial-balance")
@book_file_option
@entity_map_option()
@as_of_option(required=True)
@entity_filter_option
@format_option(("text", "csv", "json"))
def trial_balance(book_file, entity_map_file, as_of, entity, format):
    """
    Generate a Trial Balance as of a specific date.

    Lists all accounts with non-zero balances in debit and credit columns.
    Total debits must equal total credits for a set of books in balance.
    Useful as a sanity check before generating other GAAP reports.

    Use --entity to generate a report for one entity, or omit for consolidated.
    """
    logger.info("=== GCGAAP Trial Balance Report ===")

    try:
        config = GCGAAPConfig()
        entity_map = EntityMap.load(entity_map_file)

        if entity and entity not in entity_map.entities:
            click.echo(f"Error: Entity '{entity}' not found in entity map.")
            click.echo(f"Available entities: {', '.join(entity_map.entities.keys())}")
            sys.exit(1)

        with GnuCashBook(book_file) as book:
            report = generate_trial_balance(
                book=book,
                entity_map=entity_map,
                as_of_date_str=as_of,
                entity_key=entity,
                config=config,
            )

        if format.lower() == "csv":
            output = tb_format_csv(report)
        elif format.lower() == "json":
            output = tb_format_json(report)
        else:
            output = tb_format_text(report)

        click.echo()
        click.echo(output)
        sys.exit(0 if report.is_balanced() else 1)

    except ValueError as e:
        logger.error(f"Report generation failed: {e}")
        click.echo(f"\n[ERROR] {e}")
        sys.exit(1)
    except RuntimeError as e:
        logger.error(f"Validation failed: {e}")
        click.echo(f"\n[FAIL] VALIDATION FAILED: {e}")
        click.echo("\nFix validation errors before generating reports.")
        click.echo("Use 'gcgaap db validate --strict' to see detailed validation results.")
        sys.exit(1)
    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error generating trial balance: {e}", exc_info=True)
        sys.exit(1)
