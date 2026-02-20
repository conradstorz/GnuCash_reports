"""
Transaction command group for gcgaap.

Commands: cross-entity, balance
"""

import logging
import sys

import click

from ..entity_map import EntityMap
from ..gnucash_access import GnuCashBook, parse_date
from ..cross_entity import analyze_cross_entity_transactions
from ..balance_xacts import run_balance_xacts_workflow
from ._options import book_file_option, entity_map_option, as_of_option

logger = logging.getLogger(__name__)


@click.group(name="xact")
def xact_group():
    """Transaction analysis and balancing commands."""


@xact_group.command(name="cross-entity")
@book_file_option
@entity_map_option()
@as_of_option(required=False)
@click.option(
    "--entity",
    type=str,
    default=None,
    help="Filter to show only cross-entity transactions involving this specific entity.",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show detailed transaction information for each cross-entity transaction.",
)
@click.option(
    "--limit",
    "-l",
    type=int,
    default=None,
    help="Limit number of detailed transactions shown (default: show all).",
)
@click.option(
    "--simple",
    "-s",
    is_flag=True,
    help="Show unbalanced transactions in simple format: one line per split with account, date, amount.",
)
def cross_entity(book_file, entity_map_file, as_of, entity, verbose, limit, simple):
    """
    Analyze cross-entity transactions and identify imbalances.

    This command identifies transactions where splits belong to different
    entities, which commonly occurs when:

    \b
    - Shared credit cards are used for multiple businesses/personal expenses
    - One entity pays expenses on behalf of another
    - Inter-entity transfers occur

    The report shows:
    \b
    - All cross-entity transactions (count)
    - Net imbalance for each entity
    - Inter-entity balances (who owes whom)
    - Specific recommendations for creating balancing entries
    - With --verbose: detailed transaction list with dates, descriptions, and splits
    - With --simple: simple one-line format with account name, date, and amount

    Use this command when your entity balance sheets don't balance due to
    shared accounts or cross-entity payments.

    Examples:
    \b
    # Basic summary
    gcgaap xact cross-entity -f book.gnucash

    # Show first 10 transactions in detail
    gcgaap xact cross-entity -f book.gnucash --verbose --limit 10

    # Show all transactions in detail
    gcgaap xact cross-entity -f book.gnucash -v

    # Show simple one-line format
    gcgaap xact cross-entity -f book.gnucash --simple
    """
    logger.info("=== GCGAAP Cross-Entity Transaction Analysis ===")

    try:
        entity_map = EntityMap.load(entity_map_file)

        if entity and entity not in entity_map.entities:
            click.echo(f"Error: Entity '{entity}' not found in entity map.")
            click.echo(f"Available entities: {', '.join(entity_map.entities.keys())}")
            sys.exit(1)

        as_of_date = None
        if as_of:
            as_of_date = parse_date(as_of)
            click.echo(f"Analyzing transactions as of {as_of_date}")
        else:
            click.echo("Analyzing all transactions")

        if entity:
            entity_label = entity_map.entities[entity].label
            click.echo(f"Filtering to show only transactions involving: {entity_label} ({entity})")

        click.echo()

        with GnuCashBook(book_file) as book:
            analysis = analyze_cross_entity_transactions(
                book=book,
                entity_map=entity_map,
                as_of_date=as_of_date,
            )

        if entity:
            analysis = analysis.filter_by_entity(entity)

        click.echo(analysis.format_summary())
        click.echo()

        if simple:
            click.echo(analysis.format_simple_list())
            click.echo()
        elif verbose:
            click.echo(analysis.format_transaction_details(limit=limit))
            click.echo()

        if not simple:
            click.echo(analysis.format_recommendations())

        if analysis.get_entities_with_imbalances():
            click.echo("\n[ACTION NEEDED] Cross-entity imbalances detected.")
            click.echo("Review recommendations above and create balancing entries.")
            sys.exit(1)
        else:
            click.echo("\n[OK] All cross-entity transactions are balanced.")
            sys.exit(0)

    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        sys.exit(1)
    except ValueError as e:
        logger.error(f"Invalid input: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error analyzing cross-entity transactions: {e}", exc_info=True)
        sys.exit(1)


@xact_group.command(name="balance")
@book_file_option
@entity_map_option()
@click.option(
    "--entity",
    type=str,
    default=None,
    help="Filter to transactions involving this entity.",
)
@click.option(
    "--date-from",
    type=str,
    default=None,
    help="Start date filter (YYYY-MM-DD).",
)
@click.option(
    "--date-to",
    type=str,
    default=None,
    help="End date filter (YYYY-MM-DD).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Preview changes without modifying the database.",
)
def balance(book_file, entity_map_file, entity, date_from, date_to, dry_run):
    """
    Balance 2-split cross-entity transactions by adding equity account splits.

    This command identifies cross-entity transactions with exactly 2 splits
    that span 2 different entities, and automatically adds two balancing
    splits using inter-entity equity accounts (Money In/Out).

    \b
    Process:
    1. Identifies 2-split cross-entity transactions that need balancing
    2. Groups transactions by entity pair and expense account (max 9 per group)
    3. Presents each group for user approval
    4. Adds balancing splits with cross-referenced memos
    5. Saves changes after each approved group

    \b
    Requirements:
    - Each entity must have "Money In (entity)" and "Money Out (entity)" equity accounts
    - These accounts must be properly mapped to entities in entity_account_map.json
    - Transactions must have exactly 2 splits, each in a different entity

    \b
    A backup is automatically created before any changes are made.
    """
    logger.info("=== GCGAAP Balance Cross-Entity Transactions ===")

    try:
        # Parse date filters
        parsed_date_from = None
        parsed_date_to = None

        if date_from:
            parsed_date_from = parse_date(date_from)
            if not parsed_date_from:
                click.echo(f"Error: Invalid date format for --date-from: {date_from}")
                click.echo("Expected format: YYYY-MM-DD")
                sys.exit(1)
            logger.info(f"Filtering transactions from: {parsed_date_from}")

        if date_to:
            parsed_date_to = parse_date(date_to)
            if not parsed_date_to:
                click.echo(f"Error: Invalid date format for --date-to: {date_to}")
                click.echo("Expected format: YYYY-MM-DD")
                sys.exit(1)
            logger.info(f"Filtering transactions to: {parsed_date_to}")

        entity_map = EntityMap.load(entity_map_file)

        if entity and entity not in entity_map.entities:
            click.echo(f"Error: Entity '{entity}' not found in entity map.")
            click.echo(f"Available entities: {', '.join(entity_map.entities.keys())}")
            sys.exit(1)

        if entity:
            logger.info(f"Filtering to entity: {entity}")

        fixed_count, failed_count, backup_path = run_balance_xacts_workflow(
            book_file=book_file,
            entity_map=entity_map,
            entity_filter=entity,
            date_from=parsed_date_from,
            date_to=parsed_date_to,
            dry_run=dry_run,
        )

        # Summary
        click.echo("\n" + "=" * 80)
        click.echo("SUMMARY")
        click.echo("=" * 80)

        if dry_run:
            click.echo(f"\n[DRY RUN] Would have processed {fixed_count} transaction(s)")
            click.echo("\nRun without --dry-run to actually make changes.")
        else:
            click.echo(f"\n[OK] Successfully balanced: {fixed_count} transaction(s)")
            if failed_count > 0:
                click.echo(f"[X] Failed to balance: {failed_count} transaction(s)")

            if fixed_count > 0:
                click.echo("\nChanges have been saved to the GnuCash database.")
                click.echo(f"Backup available at: {backup_path}")
                click.echo("\nRecommendation: Run 'gcgaap xact cross-entity' to verify balances.")

        sys.exit(0 if failed_count == 0 else 1)

    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        click.echo(f"\nError: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error balancing transactions: {e}", exc_info=True)
        click.echo(f"\nError: {e}")
        sys.exit(1)
