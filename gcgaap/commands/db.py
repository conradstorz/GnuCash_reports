"""
Database command group for gcgaap.

Commands: validate, violations, repair-dates, snapshot, diff-snapshots
"""

import json
import logging
import sys
import warnings
from datetime import date as date_class
from pathlib import Path

import click

from ..config import GCGAAPConfig
from ..entity_map import EntityMap
from ..gnucash_access import GnuCashBook, parse_date
from ..validate import validate_book
from ..violations import generate_violations_report, format_violations_report
from ..repair import diagnose_empty_reconcile_dates, repair_empty_reconcile_dates
from ..snapshot import DatabaseSnapshot, compare_snapshots, format_comparison_text
from ._options import (
    book_file_option,
    entity_map_option,
    as_of_option,
    tolerance_option,
    output_file_option,
)

logger = logging.getLogger(__name__)


@click.group(name="db")
def db_group():
    """Database validation, repair, and snapshot commands."""


@db_group.command()
@book_file_option
@entity_map_option()
@tolerance_option
@click.option(
    "--strict",
    is_flag=True,
    help="Strict mode: require 100%% entity mapping.",
)
@click.option(
    "--format",
    type=click.Choice(["text", "json", "csv"], case_sensitive=False),
    default="text",
    help="Output format (default: text).",
)
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    help="Suppress log messages, show only formatted output.",
)
def validate(book_file, entity_map_file, tolerance, strict, format, quiet):
    """
    Validate the integrity of a GnuCash book.

    Performs validation checks including:
    - Transaction-level double-entry balancing
    - Imbalance/Orphan account detection
    - Entity mapping coverage
    - Data integrity issues

    Use --strict mode before generating reports to ensure ALL accounts
    are mapped to entities (unmapped accounts become errors instead of warnings).

    Use --format json or --format csv for machine-readable output.
    Use --quiet to suppress log messages.

    Returns exit code 0 if validation passes (no errors),
    non-zero if errors are found.
    """
    warnings.filterwarnings("ignore", category=Warning)

    if quiet:
        logging.getLogger().setLevel(logging.CRITICAL)
        logging.getLogger("gcgaap").setLevel(logging.CRITICAL)
        logging.getLogger("piecash").setLevel(logging.CRITICAL)

    if not quiet:
        if strict:
            logger.info("=== GCGAAP Validation (STRICT MODE) ===")
        else:
            logger.info("=== GCGAAP Validation ===")

    try:
        config = GCGAAPConfig(numeric_tolerance=tolerance)
        entity_map = EntityMap.load(entity_map_file)

        with GnuCashBook(book_file) as book:
            result = validate_book(book, entity_map, config, strict_mode=strict, quiet=quiet)

        if format.lower() == "json":
            output = result.format_as_json()
        elif format.lower() == "csv":
            output = result.format_as_csv()
        else:
            output = result.format_as_text(strict_mode=strict)

        click.echo(output)

        sys.exit(1 if result.has_errors else 0)

    except FileNotFoundError as e:
        if not quiet:
            logger.error(f"File not found: {e}")
        click.echo(f"ERROR: File not found: {e}")
        sys.exit(1)
    except Exception as e:
        if not quiet:
            logger.error(f"Error during validation: {e}", exc_info=True)
        click.echo(f"ERROR: {e}")
        sys.exit(1)


@db_group.command()
@book_file_option
@entity_map_option()
@as_of_option(required=False)
@tolerance_option
def violations(book_file, entity_map_file, as_of, tolerance):
    """
    Generate a comprehensive data quality violations report.

    This command performs extensive validation and reports ALL data quality
    issues including:

    \b
    - Imbalanced transactions (critical)
    - Unmapped accounts (errors)
    - Entity-level accounting equation violations (errors)
    - Imbalance/Orphan accounts with non-zero balances (warnings)

    Use this command to identify and prioritize data quality fixes before
    generating financial reports.
    """
    logger.info("=== GCGAAP Violations Report ===")

    try:
        config = GCGAAPConfig(numeric_tolerance=tolerance)
        entity_map = EntityMap.load(entity_map_file)

        if as_of:
            as_of_date = parse_date(as_of)
        else:
            as_of_date = date_class.today()

        click.echo(f"Analyzing book as of {as_of_date}")
        click.echo()

        with GnuCashBook(book_file) as book:
            report = generate_violations_report(
                book=book,
                entity_map=entity_map,
                as_of_date=as_of_date,
                config=config,
            )

        formatted_report = format_violations_report(report)
        click.echo(formatted_report)

        if report.has_critical:
            click.echo("\n[CRITICAL] Critical violations found - data integrity compromised!")
            sys.exit(2)
        elif report.has_errors:
            click.echo("\n[FAIL] Errors found - reports cannot be generated until resolved.")
            sys.exit(1)
        elif report.warning_count > 0:
            click.echo(f"\n[OK] No critical errors, but {report.warning_count} warning(s) found.")
            sys.exit(0)
        else:
            click.echo("\n[OK] No violations found - data quality is excellent!")
            sys.exit(0)

    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        sys.exit(1)
    except ValueError as e:
        logger.error(f"Invalid input: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error generating violations report: {e}", exc_info=True)
        sys.exit(1)


@db_group.command(name="repair-dates")
@book_file_option
@click.option(
    "--diagnose-only",
    is_flag=True,
    help="Only diagnose issues without making changes.",
)
@click.option(
    "--no-backup",
    is_flag=True,
    help="Skip backup creation (not recommended).",
)
def repair_dates(book_file, diagnose_only, no_backup):
    """
    Repair empty reconcile_date fields in GnuCash database.

    This command fixes a common data integrity issue where split records
    have empty strings ('') in the reconcile_date field instead of NULL.
    This causes piecash to fail with: "Couldn't parse datetime string: ''"

    The repair sets these empty strings to NULL, which piecash handles correctly.

    \b
    By default, this command:
    - Creates a timestamped backup before making changes
    - Repairs all empty reconcile_date fields
    - Verifies the repair was successful

    Use --diagnose-only to check for issues without making changes.
    """
    logger.info("=== GCGAAP Database Repair: Empty Reconcile Dates ===")

    try:
        logger.info(f"Analyzing database: {book_file}")
        count, descriptions = diagnose_empty_reconcile_dates(book_file)

        if count == 0:
            click.echo("\n✓ No empty reconcile_date fields found.")
            click.echo("Your database is clean - no repairs needed!")
            sys.exit(0)

        click.echo(f"\n⚠️  Found {count} split(s) with empty reconcile_date field")
        click.echo(f"\nAffected transactions ({len(descriptions)}):")
        for desc in descriptions[:10]:
            click.echo(f"  - {desc}")
        if len(descriptions) > 10:
            click.echo(f"  ... and {len(descriptions) - 10} more")

        click.echo(f"\nThis prevents piecash from reading these transactions.")
        click.echo("Error message: \"Couldn't parse datetime string: ''\"\n")

        if diagnose_only:
            click.echo("Diagnosis complete. Run without --diagnose-only to repair.")
            sys.exit(0)

        if not no_backup:
            click.echo("A backup will be created before making changes.")
        else:
            click.echo("⚠️  WARNING: No backup will be created (--no-backup flag)")

        click.echo("\nProceeding with repair...")

        result = repair_empty_reconcile_dates(
            book_file,
            create_backup_first=not no_backup,
        )

        click.echo()
        if result.success:
            click.echo(f"✓ {result.message}")
            if result.backup_path:
                click.echo(f"✓ Backup saved to: {result.backup_path}")
            click.echo(f"\nRepaired {result.items_fixed} split(s) successfully!")
            click.echo("\nYou can now run validation and reports without errors.")
            click.echo("If everything works, you can delete the backup file.")
            sys.exit(0)
        else:
            click.echo(f"⚠️  {result.message}")
            if result.backup_path:
                click.echo(f"Backup saved to: {result.backup_path}")
            click.echo("\nPartial repair completed. Some issues may remain.")
            sys.exit(1)

    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error during repair: {e}", exc_info=True)
        click.echo(f"\n❌ Repair failed: {e}")
        sys.exit(1)


@db_group.command()
@book_file_option
@output_file_option(required=True)
def snapshot(book_file, output_file):
    """
    Capture a complete snapshot of the GnuCash database.

    This creates a JSON snapshot file containing all accounts and transactions
    with their current state, including any errors. Useful for:

    \b
    - Debugging data integrity issues
    - Tracking changes before/after fixes
    - Identifying what external utilities might be corrupting

    Use 'diff-snapshots' command to compare two snapshots and see what changed.
    """
    logger.info("=== GCGAAP Database Snapshot ===")

    try:
        with GnuCashBook(book_file) as book:
            db_snapshot = DatabaseSnapshot.capture(book)

        db_snapshot.save(output_file)

        click.echo(f"\nSnapshot captured successfully!")
        click.echo(f"Timestamp: {db_snapshot.timestamp}")
        click.echo(f"Accounts: {db_snapshot.metadata['account_count']}")
        click.echo(f"Transactions: {db_snapshot.metadata['transaction_count']}")
        click.echo(f"Errors: {db_snapshot.metadata['error_count']}")
        click.echo(f"\nSaved to: {output_file}")

        sys.exit(0)

    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error creating snapshot: {e}", exc_info=True)
        sys.exit(1)


@db_group.command(name="diff-snapshots")
@click.option(
    "--before",
    "-b",
    "before_file",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to the 'before' snapshot JSON file.",
)
@click.option(
    "--after",
    "-a",
    "after_file",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to the 'after' snapshot JSON file.",
)
@output_file_option(required=False)
@click.option(
    "--format",
    type=click.Choice(["text", "json"], case_sensitive=False),
    default="text",
    help="Output format (default: text).",
)
def diff_snapshots(before_file, after_file, output_file, format):
    """
    Compare two database snapshots to see what changed.

    This is extremely useful for debugging what fixing a transaction actually
    changed, or identifying what an external utility is doing to the database.

    \b
    Highlights:
    - Transactions that were fixed (had errors before, not after)
    - Transactions that were broken (OK before, errors after)
    - All modifications with before/after details

    Example workflow:
    \b
    1. gcgaap db snapshot -f book.gnucash -o before.json
    2. (fix transaction in GnuCash or run external utility)
    3. gcgaap db snapshot -f book.gnucash -o after.json
    4. gcgaap db diff-snapshots -b before.json -a after.json
    """
    logger.info("=== GCGAAP Snapshot Comparison ===")

    try:
        logger.info(f"Loading before snapshot from {before_file}")
        before = DatabaseSnapshot.load(before_file)

        logger.info(f"Loading after snapshot from {after_file}")
        after = DatabaseSnapshot.load(after_file)

        changes = compare_snapshots(before, after)

        if format.lower() == "json":
            output = json.dumps(changes, indent=2)
        else:
            output = format_comparison_text(changes)

        if output_file:
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(output)
            click.echo(f"Comparison saved to: {output_file}")
        else:
            click.echo(output)

        summary = changes["summary"]
        if summary["transactions_fixed"] > 0:
            click.echo(f"\n✓ {summary['transactions_fixed']} transaction(s) were successfully fixed!")

        if summary["transactions_broken"] > 0:
            click.echo(f"\n✗ WARNING: {summary['transactions_broken']} transaction(s) were damaged!")
            sys.exit(1)

        sys.exit(0)

    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error comparing snapshots: {e}", exc_info=True)
        sys.exit(1)
