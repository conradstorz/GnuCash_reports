"""
Command-line interface for GCGAAP.

Provides CLI commands for validation, entity management, and reporting.
"""

import json
import logging
import sys
import warnings
from pathlib import Path

import click

from . import __version__
from .config import GCGAAPConfig, setup_logging
from .entity_map import EntityMap
from .gnucash_access import GnuCashBook, parse_date
from .validate import validate_book, scan_unmapped_accounts, check_cross_entity_balancing_accounts
from .entity_inference import EntityInferenceEngine
from .violations import generate_violations_report, format_violations_report
from .cross_entity import analyze_cross_entity_transactions
from .reports.balance_sheet import (
    generate_balance_sheet,
    format_as_text,
    format_as_csv,
    format_as_json
)
from .snapshot import (
    DatabaseSnapshot,
    compare_snapshots,
    format_comparison_text
)
from .repair import (
    diagnose_empty_reconcile_dates,
    repair_empty_reconcile_dates,
    RepairResult
)
from .balance_xacts import (
    create_backup,
    find_equity_accounts,
    identify_fixable_transactions,
    group_transactions,
    balance_transaction_groups
)

logger = logging.getLogger(__name__)


@click.group()
@click.version_option(version=__version__, prog_name="gcgaap")
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose (DEBUG level) logging."
)
@click.pass_context
def main(ctx, verbose):
    """
    GCGAAP - GnuCash GAAP Validation and Reporting.
    
    A command-line tool for validating GnuCash books and generating
    GAAP-style financial reports with strict accounting equation enforcement.
    """
    # Set up logging
    setup_logging(verbose)
    
    # Store verbose flag in context for subcommands
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    
    logger.debug(f"GCGAAP version {__version__}")


@main.command()
@click.option(
    "--file",
    "-f",
    "book_file",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to the GnuCash book file (.gnucash)."
)
@click.option(
    "--entity-map",
    "-e",
    "entity_map_file",
    type=click.Path(path_type=Path),
    default="entity_account_map.json",
    help="Path to the entity mapping JSON file (default: entity_account_map.json)."
)
def entity_scan(book_file, entity_map_file):
    """
    Scan for accounts that have no entity mapping.
    
    Lists all accounts in the GnuCash book that are not currently
    mapped to any entity in the entity_account_map.json file.
    
    Also checks for cross-entity balancing equity accounts and reports
    on their presence or absence for each entity.
    
    This is useful for identifying accounts that need to be added
    to the entity mapping configuration.
    """
    logger.info("=== GCGAAP Entity Scan ===")
    
    try:
        # Load entity map
        entity_map = EntityMap.load(entity_map_file)
        
        # Open book and scan
        with GnuCashBook(book_file) as book:
            unmapped = scan_unmapped_accounts(book, entity_map)
            balancing_status = check_cross_entity_balancing_accounts(book, entity_map)
        
        # Display unmapped accounts
        if not unmapped:
            click.echo("[OK] All accounts are mapped to entities.")
        else:
            click.echo(f"\nFound {len(unmapped)} unmapped account(s):\n")
            click.echo(f"{'GUID':<40} {'Type':<15} {'Currency':<10} {'Full Name'}")
            click.echo("-" * 120)
            
            for account in unmapped:
                click.echo(
                    f"{account.guid:<40} "
                    f"{account.type:<15} "
                    f"{account.commodity_symbol:<10} "
                    f"{account.full_name}"
                )
            
            click.echo(f"\n{len(unmapped)} account(s) need entity mapping.")
            click.echo(f"Edit {entity_map_file} to add mappings for these accounts.")
        
        # Display cross-entity balancing account status
        click.echo("\n" + "=" * 80)
        click.echo("CROSS-ENTITY BALANCING ACCOUNT STATUS")
        click.echo("=" * 80)
        click.echo()
        
        entities_with_balancing = []
        entities_without_balancing = []
        
        for entity_key, status in sorted(balancing_status.items(), key=lambda x: x[1].entity_label):
            if status.has_balancing_account:
                entities_with_balancing.append(status)
            else:
                entities_without_balancing.append(status)
        
        if entities_with_balancing:
            click.echo("✓ Entities WITH cross-entity balancing accounts:")
            click.echo()
            for status in entities_with_balancing:
                click.echo(f"  ✓ {status.entity_label} ({status.entity_key})")
                for account_name in status.balancing_accounts:
                    click.echo(f"      - {account_name}")
            click.echo()
        
        if entities_without_balancing:
            click.echo("⚠ Entities WITHOUT cross-entity balancing accounts:")
            click.echo()
            for status in entities_without_balancing:
                click.echo(f"  ⚠ {status.entity_label} ({status.entity_key})")
            click.echo()
            click.echo("Consider creating cross-entity balancing equity accounts for these entities")
            click.echo("if they participate in cross-entity transactions (e.g., shared credit cards).")
            click.echo()
            click.echo("Recommended account names:")
            click.echo("  - Equity:Cross-Entity Balancing")
            click.echo("  - Equity:Inter-Entity")
            click.echo()
        
        # Summary
        click.echo("=" * 80)
        click.echo(f"Summary: {len(entities_with_balancing)} entities with balancing accounts, "
                   f"{len(entities_without_balancing)} without")
        click.echo("=" * 80)
        
        # Exit with success (this is informational, not an error)
        sys.exit(0)
        
    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error during entity scan: {e}", exc_info=True)
        sys.exit(1)


@main.command()
@click.option(
    "--file",
    "-f",
    "book_file",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to the GnuCash book file (.gnucash)."
)
@click.option(
    "--entity-map",
    "-e",
    "entity_map_file",
    type=click.Path(path_type=Path),
    default="entity_account_map.json",
    help="Path to read/write entity mapping JSON file (default: entity_account_map.json)."
)
@click.option(
    "--output",
    "-o",
    "output_file",
    type=click.Path(path_type=Path),
    default=None,
    help="Output file for suggested entity map (default: print to console)."
)
@click.option(
    "--merge/--no-merge",
    default=False,
    help="Merge suggestions with existing entity-map file."
)
def entity_infer(book_file, entity_map_file, output_file, merge):
    """
    Smart entity inference using AI pattern analysis.
    
    Analyzes account names in the GnuCash book to intelligently
    suggest entity groupings and generate entity mapping configuration.
    
    This uses pattern matching and heuristics to identify:
    - Business entities (by detecting company names, LLC/Inc/Corp)
    - Personal/individual entities
    - Common account grouping patterns
    
    The output can be saved to a new file or merged with an existing
    entity-map.json file.
    """
    logger.info("=== GCGAAP Smart Entity Inference ===")
    
    try:
        # Open book and run inference
        engine = EntityInferenceEngine()
        
        with GnuCashBook(book_file) as book:
            result = engine.analyze_book(book)
        
        # Display analysis notes
        click.echo("\n=== Analysis Summary ===\n")
        for note in result.analysis_notes:
            click.echo(f"  {note}")
        
        # Display suggestions
        if not result.suggestions:
            click.echo("\n⚠ No entity patterns detected. Your book may need manual mapping.")
            sys.exit(0)
        
        click.echo(f"\n=== Suggested Entities ({len(result.suggestions)}) ===\n")
        
        for i, suggestion in enumerate(result.suggestions, 1):
            confidence_bar = "█" * int(suggestion.confidence * 10)
            click.echo(f"{i}. {suggestion.label}")
            click.echo(f"   Key: {suggestion.key}")
            click.echo(f"   Type: {suggestion.type}")
            click.echo(f"   Confidence: [{confidence_bar:<10}] {suggestion.confidence:.1%}")
            click.echo(f"   Accounts: {suggestion.account_count}")
            click.echo(f"   Sample accounts:")
            for sample in suggestion.sample_accounts[:3]:
                click.echo(f"     - {sample}")
            click.echo(f"   Suggested patterns:")
            for pattern in suggestion.suggested_patterns[:3]:
                click.echo(f"     - {pattern}")
            if len(suggestion.suggested_patterns) > 3:
                click.echo(f"     ... and {len(suggestion.suggested_patterns) - 3} more")
            click.echo()
        
        # Display unmapped accounts
        if result.unmapped_accounts:
            click.echo(f"=== Unmapped Accounts ({len(result.unmapped_accounts)}) ===\n")
            click.echo("These accounts don't match suggested patterns and may need manual mapping:\n")
            for account in result.unmapped_accounts[:10]:
                click.echo(f"  - {account.full_name}")
            if len(result.unmapped_accounts) > 10:
                click.echo(f"  ... and {len(result.unmapped_accounts) - 10} more")
            click.echo()
        
        # Generate entity map structure
        suggested_map = _build_entity_map_from_suggestions(result.suggestions)
        
        # Merge with existing if requested
        if merge and entity_map_file.exists():
            click.echo(f"Merging with existing entity map from {entity_map_file}")
            existing_map = EntityMap.load(entity_map_file)
            suggested_map = _merge_entity_maps(existing_map, suggested_map)
        
        # Output or save
        if output_file:
            suggested_map.save(output_file)
            click.echo(f"\n[OK] Suggested entity map saved to: {output_file}")
        else:
            # Print JSON to console
            import json
            click.echo("\n=== Suggested Entity Map JSON ===\n")
            
            map_dict = {
                "version": suggested_map.version,
                "entities": {
                    key: {
                        "label": entity.label,
                        "type": entity.type
                    }
                    for key, entity in suggested_map.entities.items()
                },
                "accounts": suggested_map.account_entities,
                "patterns": suggested_map.patterns
            }
            
            click.echo(json.dumps(map_dict, indent=2))
            click.echo()
            click.echo("To regenerate entity mapping:")
            click.echo(f"  gcgaap entity-remap -f {book_file}")
        
        sys.exit(0)
        
    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error during entity inference: {e}", exc_info=True)
        sys.exit(1)


def _build_entity_map_from_suggestions(suggestions: list) -> EntityMap:
    """
    Build an EntityMap from inference suggestions.
    
    Args:
        suggestions: List of EntitySuggestion objects.
        
    Returns:
        EntityMap with suggested entities and patterns.
    """
    from .entity_map import EntityDefinition
    
    entity_map = EntityMap()
    
    for suggestion in suggestions:
        # Add entity definition
        entity_map.entities[suggestion.key] = EntityDefinition(
            key=suggestion.key,
            label=suggestion.label,
            type=suggestion.type
        )
        
        # Add patterns
        if suggestion.suggested_patterns:
            entity_map.patterns[suggestion.key] = suggestion.suggested_patterns
    
    # Recompile patterns
    entity_map._compile_patterns()
    
    return entity_map


def _merge_entity_maps(existing: EntityMap, suggested: EntityMap) -> EntityMap:
    """
    Merge suggested entity map with existing one.
    
    Args:
        existing: Existing EntityMap.
        suggested: Suggested EntityMap.
        
    Returns:
        Merged EntityMap (keeps existing, adds new suggestions).
    """
    merged = EntityMap(
        version=existing.version,
        entities=dict(existing.entities),
        account_entities=dict(existing.account_entities),
        patterns=dict(existing.patterns)
    )
    
    # Add new entities (don't overwrite existing)
    for key, entity in suggested.entities.items():
        if key not in merged.entities:
            merged.entities[key] = entity
            logger.info(f"Added new entity: {key}")
    
    # Add new patterns (merge lists for existing entities)
    for key, patterns in suggested.patterns.items():
        if key in merged.patterns:
            # Merge pattern lists, avoiding duplicates
            existing_patterns = set(merged.patterns[key])
            new_patterns = [p for p in patterns if p not in existing_patterns]
            if new_patterns:
                merged.patterns[key].extend(new_patterns)
                logger.info(f"Added {len(new_patterns)} new pattern(s) for entity: {key}")
        else:
            merged.patterns[key] = patterns
            logger.info(f"Added patterns for new entity: {key}")
    
    # Recompile patterns
    merged._compile_patterns()
    
    return merged


@main.command(name="entity-remap")
@click.option(
    "--file",
    "-f",
    "book_file",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to the GnuCash book file (.gnucash)."
)
@click.option(
    "--output",
    "-o",
    "output_file",
    type=click.Path(path_type=Path),
    default="entity_account_map.json",
    help="Output JSON file path (default: entity_account_map.json)"
)
@click.pass_context
def entity_remap(ctx, book_file, output_file):
    """
    Regenerate entity account mapping from GnuCash database.
    
    Scans all accounts in the GnuCash book and maps them to entities
    based on naming patterns. Uses parent-child inheritance for entity
    assignment.
    
    This is the canonical way to generate the entity_account_map.json
    file that gcgaap uses for all entity-based operations.
    """
    verbose = ctx.obj.get("verbose", False)
    
    logger.info("=== GCGAAP Entity Remapping ===")
    
    try:
        # Import the mapper functions from tools
        import sys
        from pathlib import Path
        tools_path = Path(__file__).parent / "tools"
        sys.path.insert(0, str(tools_path))
        
        from entity_account_mapper import (
            build_entity_patterns,
            build_account_tree,
            assign_entities_with_inheritance,
            generate_entity_report,
            generate_summary,
            ENTITIES
        )
        from piecash import open_book
        
        if verbose:
            click.echo(f"Opening GnuCash database: {book_file}")
        
        # Open the GnuCash book
        book = open_book(str(book_file), readonly=True, do_backup=False)
        
        try:
            # Build entity patterns
            if verbose:
                click.echo("Building entity patterns...")
            entity_patterns = build_entity_patterns()
            
            # Build account tree
            if verbose:
                click.echo("Building account tree...")
            accounts_dict, root_accounts = build_account_tree(book)
            
            if verbose:
                click.echo(f"Found {len(accounts_dict)} accounts")
            
            # Assign entities with inheritance
            if verbose:
                click.echo("Assigning entities to accounts...")
            assign_entities_with_inheritance(accounts_dict, root_accounts, entity_patterns)
            
            # Generate report
            if verbose:
                click.echo("Generating report...")
            report = generate_entity_report(accounts_dict)
            summary = generate_summary(report)
            
            # Create final output structure
            output = {
                "summary": summary,
                "entities": report,
            }
            
            # Write to JSON file
            output_path = Path(output_file)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(output, f, indent=2, ensure_ascii=False)
            
            click.echo(f"Entity mapping written to: {output_path}")
            click.echo()
            click.echo("Summary:")
            for entity_key, count in summary["entity_counts"].items():
                label = summary["entity_labels"][entity_key]
                click.echo(f"  {label:20s}: {count:4d} accounts")
            click.echo(f"  {'-' * 26}")
            click.echo(f"  {'Total':20s}: {summary['total_accounts']:4d} accounts")
            
        finally:
            book.close()
        
        sys.exit(0)
        
    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error during entity remapping: {e}", exc_info=True)
        sys.exit(1)


@main.command()
@click.option(
    "--file",
    "-f",
    "book_file",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to the GnuCash book file (.gnucash)."
)
@click.option(
    "--entity-map",
    "-e",
    "entity_map_file",
    type=click.Path(path_type=Path),
    default="entity_account_map.json",
    help="Path to the entity mapping JSON file (default: entity_account_map.json)."
)
@click.option(
    "--tolerance",
    "-t",
    type=float,
    default=0.01,
    help="Numeric tolerance for balance checks (default: 0.01)."
)
@click.option(
    "--strict",
    is_flag=True,
    help="Strict mode: Require 100%% entity mapping (for pre-report validation)."
)
@click.option(
    "--format",
    type=click.Choice(["text", "json", "csv"], case_sensitive=False),
    default="text",
    help="Output format (default: text)."
)
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    help="Suppress log messages, show only formatted output."
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
    # Suppress SQLAlchemy warnings
    import warnings
    warnings.filterwarnings('ignore', category=Warning)
    
    # Suppress all logging in quiet mode
    if quiet:
        import logging
        logging.getLogger().setLevel(logging.CRITICAL)
        logging.getLogger('gcgaap').setLevel(logging.CRITICAL)
        logging.getLogger('piecash').setLevel(logging.CRITICAL)
    
    if not quiet:
        if strict:
            logger.info("=== GCGAAP Validation (STRICT MODE) ===")
        else:
            logger.info("=== GCGAAP Validation ===")
    
    try:
        # Create configuration
        config = GCGAAPConfig(numeric_tolerance=tolerance)
        
        # Load entity map
        entity_map = EntityMap.load(entity_map_file)
        
        # Open book and validate
        with GnuCashBook(book_file) as book:
            result = validate_book(book, entity_map, config, strict_mode=strict, quiet=quiet)
        
        # Format and display output
        if format.lower() == "json":
            output = result.format_as_json()
        elif format.lower() == "csv":
            output = result.format_as_csv()
        else:  # text
            output = result.format_as_text(strict_mode=strict)
        
        click.echo(output)
        
        # Exit with appropriate code
        if result.has_errors:
            sys.exit(1)
        else:
            sys.exit(0)
        
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


@main.command()
@click.option(
    "--file",
    "-f",
    "book_file",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to the GnuCash book file (.gnucash)."
)
@click.option(
    "--output",
    "-o",
    "output_file",
    type=click.Path(path_type=Path),
    required=True,
    help="Path to save the snapshot JSON file."
)
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
        # Open book and capture snapshot
        with GnuCashBook(book_file) as book:
            db_snapshot = DatabaseSnapshot.capture(book)
        
        # Save snapshot
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


@main.command()
@click.option(
    "--before",
    "-b",
    "before_file",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to the 'before' snapshot JSON file."
)
@click.option(
    "--after",
    "-a",
    "after_file",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to the 'after' snapshot JSON file."
)
@click.option(
    "--output",
    "-o",
    "output_file",
    type=click.Path(path_type=Path),
    default=None,
    help="Path to save comparison results (JSON). If omitted, prints to console."
)
@click.option(
    "--format",
    type=click.Choice(["text", "json"], case_sensitive=False),
    default="text",
    help="Output format (default: text)."
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
    1. gcgaap snapshot -f book.gnucash -o before.json
    2. (fix transaction in GnuCash or run external utility)
    3. gcgaap snapshot -f book.gnucash -o after.json
    4. gcgaap diff-snapshots -b before.json -a after.json
    """
    logger.info("=== GCGAAP Snapshot Comparison ===")
    
    try:
        # Load snapshots
        logger.info(f"Loading before snapshot from {before_file}")
        before = DatabaseSnapshot.load(before_file)
        
        logger.info(f"Loading after snapshot from {after_file}")
        after = DatabaseSnapshot.load(after_file)
        
        # Compare
        changes = compare_snapshots(before, after)
        
        # Format output
        if format.lower() == "json":
            import json
            output = json.dumps(changes, indent=2)
        else:
            output = format_comparison_text(changes)
        
        # Save or print
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(output)
            click.echo(f"Comparison saved to: {output_file}")
        else:
            click.echo(output)
        
        # Exit code based on findings
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


@main.command()
@click.option(
    "--file",
    "-f",
    "book_file",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to the GnuCash book file (.gnucash)."
)
@click.option(
    "--entity-map",
    "-e",
    "entity_map_file",
    type=click.Path(path_type=Path),
    default="entity_account_map.json",
    help="Path to the entity mapping JSON file (default: entity_account_map.json)."
)
@click.option(
    "--as-of",
    type=str,
    default=None,
    help="Balance calculation date in YYYY-MM-DD format (default: today)."
)
@click.option(
    "--tolerance",
    "-t",
    type=float,
    default=0.01,
    help="Numeric tolerance for balance checks (default: 0.01)."
)
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
    
    The violations report shows:
    \b
    - Summary of all violations by category
    - Entity balance summary (which entities don't balance)
    - Detailed violation information
    - Actionable recommendations for fixing issues
    
    Use this command to identify and prioritize data quality fixes before
    generating financial reports.
    """
    logger.info("=== GCGAAP Violations Report ===")
    
    try:
        # Create configuration
        config = GCGAAPConfig(numeric_tolerance=tolerance)
        
        # Load entity map
        entity_map = EntityMap.load(entity_map_file)
        
        # Parse as_of_date
        if as_of:
            as_of_date = parse_date(as_of)
        else:
            from datetime import date as date_class
            as_of_date = date_class.today()
        
        click.echo(f"Analyzing book as of {as_of_date}")
        click.echo()
        
        # Open book and generate violations report
        with GnuCashBook(book_file) as book:
            report = generate_violations_report(
                book=book,
                entity_map=entity_map,
                as_of_date=as_of_date,
                config=config
            )
        
        # Format and display the report
        formatted_report = format_violations_report(report)
        click.echo(formatted_report)
        
        # Exit with appropriate code
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


@main.command(name="cross-entity")
@click.option(
    "--file",
    "-f",
    "book_file",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to the GnuCash book file (.gnucash)."
)
@click.option(
    "--entity-map",
    "-e",
    "entity_map_file",
    type=click.Path(path_type=Path),
    default="entity_account_map.json",
    help="Path to the entity mapping JSON file (default: entity_account_map.json)."
)
@click.option(
    "--as-of",
    type=str,
    default=None,
    help="Analysis date in YYYY-MM-DD format (default: all transactions)."
)
@click.option(
    "--entity",
    type=str,
    default=None,
    help="Filter to show only cross-entity transactions involving this specific entity."
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show detailed transaction information for each cross-entity transaction."
)
@click.option(
    "--limit",
    "-l",
    type=int,
    default=None,
    help="Limit number of detailed transactions shown (default: show all)."
)
@click.option(
    "--simple",
    "-s",
    is_flag=True,
    help="Show unbalanced transactions in simple format: one line per split with account, date, amount."
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
    gcgaap cross-entity -f book.gnucash
    
    # Show first 10 transactions in detail
    gcgaap cross-entity -f book.gnucash --verbose --limit 10
    
    # Show all transactions in detail
    gcgaap cross-entity -f book.gnucash -v
    
    # Show simple one-line format
    gcgaap cross-entity -f book.gnucash --simple
    """
    logger.info("=== GCGAAP Cross-Entity Transaction Analysis ===")
    
    try:
        # Load entity map
        entity_map = EntityMap.load(entity_map_file)
        
        # Validate entity key if specified
        if entity and entity not in entity_map.entities:
            click.echo(f"Error: Entity '{entity}' not found in entity map.")
            click.echo(f"Available entities: {', '.join(entity_map.entities.keys())}")
            sys.exit(1)
        
        # Parse as_of_date
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
        
        # Open book and analyze
        with GnuCashBook(book_file) as book:
            analysis = analyze_cross_entity_transactions(
                book=book,
                entity_map=entity_map,
                as_of_date=as_of_date
            )
        
        # Filter by entity if specified
        if entity:
            analysis = analysis.filter_by_entity(entity)
        
        # Display summary
        summary = analysis.format_summary()
        click.echo(summary)
        click.echo()
        
        # Display transactions in requested format
        if simple:
            # Simple one-line format
            simple_list = analysis.format_simple_list()
            click.echo(simple_list)
            click.echo()
        elif verbose:
            # Detailed multi-line format
            details = analysis.format_transaction_details(limit=limit)
            click.echo(details)
            click.echo()
        
        # Display recommendations (skip if simple format)
        if not simple:
            recommendations = analysis.format_recommendations()
            click.echo(recommendations)
        
        # Exit with appropriate code
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


@main.command(name="balance-xacts")
@click.option(
    "--file",
    "-f",
    "book_file",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to the GnuCash book file (.gnucash)."
)
@click.option(
    "--entity-map",
    "-e",
    "entity_map_file",
    type=click.Path(path_type=Path),
    default="entity_account_map.json",
    help="Path to the entity mapping JSON file (default: entity_account_map.json)."
)
@click.option(
    "--entity",
    type=str,
    default=None,
    help="Filter to transactions involving this entity."
)
@click.option(
    "--date-from",
    type=str,
    default=None,
    help="Start date filter (YYYY-MM-DD)."
)
@click.option(
    "--date-to",
    type=str,
    default=None,
    help="End date filter (YYYY-MM-DD)."
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Preview changes without modifying the database."
)
def balance_xacts(book_file, entity_map_file, entity, date_from, date_to, dry_run):
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
        
        # Load entity map
        entity_map = EntityMap.load(entity_map_file)
        
        # Validate entity filter if specified
        if entity and entity not in entity_map.entities:
            click.echo(f"Error: Entity '{entity}' not found in entity map.")
            click.echo(f"Available entities: {', '.join(entity_map.entities.keys())}")
            sys.exit(1)
        
        if entity:
            logger.info(f"Filtering to entity: {entity}")
        
        # Step 1: Analyze cross-entity transactions
        click.echo("\n" + "=" * 80)
        click.echo("STEP 1: Analyzing cross-entity transactions...")
        click.echo("=" * 80)
        
        with GnuCashBook(book_file) as book:
            analysis = analyze_cross_entity_transactions(book, entity_map)
        
        # Step 2: Identify fixable transactions
        click.echo("\n" + "=" * 80)
        click.echo("STEP 2: Identifying fixable 2-split transactions...")
        click.echo("=" * 80)
        
        fixable = identify_fixable_transactions(
            analysis,
            date_from=parsed_date_from,
            date_to=parsed_date_to,
            entity_filter=entity
        )
        
        if not fixable:
            click.echo("\nNo fixable transactions found!")
            click.echo("(Looking for 2-split cross-entity transactions with imbalances)")
            sys.exit(0)
        
        click.echo(f"\nFound {len(fixable)} fixable transaction(s)")
        
        # Step 3: Check for required equity accounts
        click.echo("\n" + "=" * 80)
        click.echo("STEP 3: Checking for inter-entity equity accounts...")
        click.echo("=" * 80)
        
        import piecash
        
        # Open book to check equity accounts
        book_obj = piecash.open_book(str(book_file), readonly=True, do_backup=False)
        equity_accounts_map = find_equity_accounts(book_obj, entity_map)
        book_obj.close()
        
        # Check which entities are involved in fixable transactions
        involved_entities = set()
        for txn in fixable:
            involved_entities.update(txn.entities_involved)
        
        # Verify all involved entities have equity accounts
        missing_accounts = []
        for entity_key in involved_entities:
            if entity_key not in equity_accounts_map:
                missing_accounts.append(f"  - {entity_key}: No equity accounts found")
            elif not equity_accounts_map[entity_key].has_both_accounts():
                equity = equity_accounts_map[entity_key]
                if not equity.money_in_account:
                    missing_accounts.append(f"  - {entity_key}: Missing 'Money In' account")
                if not equity.money_out_account:
                    missing_accounts.append(f"  - {entity_key}: Missing 'Money Out' account")
        
        if missing_accounts:
            click.echo("\n[ERROR] Missing required equity accounts:")
            for msg in missing_accounts:
                click.echo(msg)
            click.echo("\nRequired account pattern for each entity:")
            click.echo("  Equity:<EntityName>:Money In (<OtherEntity>)")
            click.echo("  Equity:<EntityName>:Money Out (<OtherEntity>)")
            click.echo("\nCreate these accounts in GnuCash and map them to entities.")
            sys.exit(1)
        
        click.echo(f"\n[OK] All {len(involved_entities)} involved entities have required equity accounts")
        
        # Step 4: Group transactions
        click.echo("\n" + "=" * 80)
        click.echo("STEP 4: Grouping similar transactions...")
        click.echo("=" * 80)
        
        groups = group_transactions(fixable)
        
        click.echo(f"\nCreated {len(groups)} group(s) for approval")
        
        # Step 5: Create backup (unless dry-run)
        if not dry_run:
            click.echo("\n" + "=" * 80)
            click.echo("STEP 5: Creating backup...")
            click.echo("=" * 80)
            
            backup_path = create_backup(book_file)
            click.echo(f"\n[OK] Backup created: {backup_path}")
        else:
            click.echo("\n[DRY RUN] Skipping backup creation")
        
        # Step 6: Process groups with user approval
        click.echo("\n" + "=" * 80)
        if dry_run:
            click.echo("STEP 6: Processing groups (DRY RUN - no changes will be made)...")
        else:
            click.echo("STEP 6: Processing groups (you will approve each group)...")
        click.echo("=" * 80)
        
        fixed_count, failed_count = balance_transaction_groups(
            book_file,
            groups,
            equity_accounts_map,
            dry_run=dry_run
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
                click.echo(f"✗ Failed to balance: {failed_count} transaction(s)")
            
            if fixed_count > 0:
                click.echo("\nChanges have been saved to the GnuCash database.")
                click.echo(f"Backup available at: {backup_path}")
                click.echo("\nRecommendation: Run 'gcgaap cross-entity' to verify balances.")
        
        sys.exit(0 if failed_count == 0 else 1)
        
    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        click.echo(f"\nError: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error balancing transactions: {e}", exc_info=True)
        click.echo(f"\nError: {e}")
        sys.exit(1)


@main.command(name="repair-dates")
@click.option(
    "--file",
    "-f",
    "book_file",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to the GnuCash book file (.gnucash)."
)
@click.option(
    "--diagnose-only",
    is_flag=True,
    help="Only diagnose issues without making changes."
)
@click.option(
    "--no-backup",
    is_flag=True,
    help="Skip backup creation (not recommended)."
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
        # Diagnose the issue
        logger.info(f"Analyzing database: {book_file}")
        count, descriptions = diagnose_empty_reconcile_dates(book_file)
        
        if count == 0:
            click.echo("\n✓ No empty reconcile_date fields found.")
            click.echo("Your database is clean - no repairs needed!")
            sys.exit(0)
        
        # Show diagnosis
        click.echo(f"\n⚠️  Found {count} split(s) with empty reconcile_date field")
        click.echo(f"\nAffected transactions ({len(descriptions)}):")
        for desc in descriptions[:10]:  # Show first 10
            click.echo(f"  - {desc}")
        if len(descriptions) > 10:
            click.echo(f"  ... and {len(descriptions) - 10} more")
        
        click.echo(f"\nThis prevents piecash from reading these transactions.")
        click.echo("Error message: \"Couldn't parse datetime string: ''\"\n")
        
        # If diagnose-only, stop here
        if diagnose_only:
            click.echo("Diagnosis complete. Run without --diagnose-only to repair.")
            sys.exit(0)
        
        # Confirm repair
        if not no_backup:
            click.echo("A backup will be created before making changes.")
        else:
            click.echo("⚠️  WARNING: No backup will be created (--no-backup flag)")
        
        click.echo("\nProceeding with repair...")
        
        # Perform repair
        result = repair_empty_reconcile_dates(
            book_file,
            create_backup_first=not no_backup
        )
        
        # Report results
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


@main.command(name="balance-check")
@click.option(
    "--file",
    "-f",
    "book_file",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to the GnuCash book file (.gnucash)."
)
@click.option(
    "--entity-map",
    "-e",
    "entity_map_file",
    type=click.Path(path_type=Path),
    default="entity_account_map.json",
    help="Path to the entity mapping JSON file (default: entity_account_map.json)."
)
@click.option(
    "--as-of",
    type=str,
    required=True,
    help="Balance sheet date in YYYY-MM-DD format."
)
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
        # Create configuration
        config = GCGAAPConfig()
        
        # Load entity map
        entity_map = EntityMap.load(entity_map_file)
        
        # Store results
        results = []
        
        # Open book
        with GnuCashBook(book_file) as book:
            # Check consolidated first
            click.echo("\n" + "=" * 80)
            click.echo(f"BALANCE CHECK REPORT - As of {as_of}")
            click.echo("=" * 80)
            click.echo("\nChecking consolidated (all entities)...")
            
            try:
                bs = generate_balance_sheet(
                    book=book,
                    entity_map=entity_map,
                    as_of_date_str=as_of,
                    entity_key=None,
                    config=config
                )
                results.append({
                    "entity": "CONSOLIDATED",
                    "label": "Consolidated (All Entities)",
                    "balanced": True,
                    "assets": bs.total_assets,
                    "liabilities": bs.total_liabilities,
                    "equity": bs.total_equity,
                    "imbalance": 0.0
                })
            except ValueError as e:
                # Extract imbalance from error message
                error_str = str(e)
                if "Imbalance (A - L - E):" in error_str:
                    lines = error_str.split('\n')
                    assets = liabilities = equity = imbalance = 0.0
                    for line in lines:
                        if line.startswith("Assets:"):
                            assets = float(line.split(":")[1].strip().replace(",", ""))
                        elif line.startswith("Liabilities:"):
                            liabilities = float(line.split(":")[1].strip().replace(",", ""))
                        elif line.startswith("Equity:"):
                            equity = float(line.split(":")[1].strip().replace(",", ""))
                        elif line.startswith("Imbalance"):
                            imbalance = float(line.split(":")[1].strip().replace(",", ""))
                    results.append({
                        "entity": "CONSOLIDATED",
                        "label": "Consolidated (All Entities)",
                        "balanced": False,
                        "assets": assets,
                        "liabilities": liabilities,
                        "equity": equity,
                        "imbalance": imbalance
                    })
                else:
                    results.append({
                        "entity": "CONSOLIDATED",
                        "label": "Consolidated (All Entities)",
                        "balanced": False,
                        "assets": 0.0,
                        "liabilities": 0.0,
                        "equity": 0.0,
                        "imbalance": 0.0,
                        "error": str(e)
                    })
            
            # Check each entity
            for entity_key, entity_config in entity_map.entities.items():
                if entity_key == "unassigned":
                    continue  # Skip unassigned structural accounts
                
                entity_label = entity_config.label
                click.echo(f"Checking {entity_label}...")
                
                try:
                    bs = generate_balance_sheet(
                        book=book,
                        entity_map=entity_map,
                        as_of_date_str=as_of,
                        entity_key=entity_key,
                        config=config
                    )
                    results.append({
                        "entity": entity_key,
                        "label": entity_label,
                        "balanced": True,
                        "assets": bs.total_assets,
                        "liabilities": bs.total_liabilities,
                        "equity": bs.total_equity,
                        "imbalance": 0.0
                    })
                except ValueError as e:
                    # Extract imbalance from error message
                    error_str = str(e)
                    if "Imbalance (A - L - E):" in error_str:
                        lines = error_str.split('\n')
                        assets = liabilities = equity = imbalance = 0.0
                        for line in lines:
                            if line.startswith("Assets:"):
                                assets = float(line.split(":")[1].strip().replace(",", ""))
                            elif line.startswith("Liabilities:"):
                                liabilities = float(line.split(":")[1].strip().replace(",", ""))
                            elif line.startswith("Equity:"):
                                equity = float(line.split(":")[1].strip().replace(",", ""))
                            elif line.startswith("Imbalance"):
                                imbalance = float(line.split(":")[1].strip().replace(",", ""))
                        results.append({
                            "entity": entity_key,
                            "label": entity_label,
                            "balanced": False,
                            "assets": assets,
                            "liabilities": liabilities,
                            "equity": equity,
                            "imbalance": imbalance
                        })
                    else:
                        results.append({
                            "entity": entity_key,
                            "label": entity_label,
                            "balanced": False,
                            "assets": 0.0,
                            "liabilities": 0.0,
                            "equity": 0.0,
                            "imbalance": 0.0,
                            "error": str(e)
                        })
        
        # Display summary
        click.echo("\n" + "=" * 80)
        click.echo("SUMMARY")
        click.echo("=" * 80)
        
        balanced_count = sum(1 for r in results if r["balanced"])
        imbalanced_count = len(results) - balanced_count
        
        # Show balanced entities
        if balanced_count > 0:
            click.echo(f"\n✓ BALANCED ({balanced_count}):")
            click.echo("-" * 80)
            for result in results:
                if result["balanced"]:
                    click.echo(f"  ✓ {result['label']:40s} "
                             f"A: ${result['assets']:>15,.2f}  "
                             f"L: ${result['liabilities']:>15,.2f}  "
                             f"E: ${result['equity']:>15,.2f}")
        
        # Show imbalanced entities
        if imbalanced_count > 0:
            click.echo(f"\n✗ IMBALANCED ({imbalanced_count}):")
            click.echo("-" * 80)
            for result in results:
                if not result["balanced"]:
                    if "error" in result:
                        click.echo(f"  ✗ {result['label']:40s} ERROR: {result['error']}")
                    else:
                        click.echo(f"  ✗ {result['label']:40s} "
                                 f"A: ${result['assets']:>15,.2f}  "
                                 f"L: ${result['liabilities']:>15,.2f}  "
                                 f"E: ${result['equity']:>15,.2f}  "
                                 f"Imbalance: ${result['imbalance']:>15,.2f}")
        
        click.echo("\n" + "=" * 80)
        
        if imbalanced_count == 0:
            click.echo("✓ ALL ENTITIES BALANCED - Books are in good order!")
            sys.exit(0)
        else:
            click.echo(f"✗ {imbalanced_count} entity/entities have accounting equation violations")
            click.echo("  Review and fix imbalanced entities before generating reports.")
            sys.exit(1)
        
    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error during balance check: {e}", exc_info=True)
        click.echo(f"\n✗ Balance check failed: {e}")
        sys.exit(1)


@main.command()
@click.option(
    "--file",
    "-f",
    "book_file",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to the GnuCash book file (.gnucash)."
)
@click.option(
    "--entity-map",
    "-e",
    "entity_map_file",
    type=click.Path(path_type=Path),
    default="entity_account_map.json",
    help="Path to the entity mapping JSON file (default: entity_account_map.json)."
)
@click.option(
    "--as-of",
    type=str,
    required=True,
    help="Balance sheet date in YYYY-MM-DD format."
)
@click.option(
    "--entity",
    type=str,
    default=None,
    help="Entity key for entity-specific report (omit for consolidated)."
)
@click.option(
    "--format",
    type=click.Choice(["text", "csv", "json"], case_sensitive=False),
    default="text",
    help="Output format (default: text)."
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
        # Create configuration
        config = GCGAAPConfig()
        
        # Load entity map
        entity_map = EntityMap.load(entity_map_file)
        
        # Validate entity key if specified
        if entity and entity not in entity_map.entities:
            click.echo(f"Error: Entity '{entity}' not found in entity map.")
            click.echo(f"Available entities: {', '.join(entity_map.entities.keys())}")
            sys.exit(1)
        
        # Open book and generate report
        with GnuCashBook(book_file) as book:
            # Generate balance sheet (includes automatic strict validation)
            balance_sheet_obj = generate_balance_sheet(
                book=book,
                entity_map=entity_map,
                as_of_date_str=as_of,
                entity_key=entity,
                config=config
            )
        
        # Format output based on requested format
        if format.lower() == "csv":
            output = format_as_csv(balance_sheet_obj)
        elif format.lower() == "json":
            output = format_as_json(balance_sheet_obj)
        else:  # text (default)
            output = format_as_text(balance_sheet_obj)
        
        # Display the report
        click.echo()
        click.echo(output)
        
        # Success
        sys.exit(0)
        
    except ValueError as e:
        # Accounting equation violation or data integrity issue
        logger.error(f"Report generation failed: {e}")
        click.echo(f"\n[ERROR] {e}")
        sys.exit(1)
    except RuntimeError as e:
        # Strict validation failure
        logger.error(f"Validation failed: {e}")
        click.echo(f"\n[FAIL] VALIDATION FAILED: {e}")
        click.echo("\nFix validation errors before generating reports.")
        click.echo("Use 'gcgaap validate --strict' to see detailed validation results.")
        sys.exit(1)
    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error generating balance sheet: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
