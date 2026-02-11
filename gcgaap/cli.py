"""
Command-line interface for GCGAAP.

Provides CLI commands for validation, entity management, and reporting.
"""

import logging
import sys
from pathlib import Path

import click

from . import __version__
from .config import GCGAAPConfig, setup_logging
from .entity_map import EntityMap
from .gnucash_access import GnuCashBook, parse_date
from .validate import validate_book, scan_unmapped_accounts
from .entity_inference import EntityInferenceEngine
from .violations import generate_violations_report, format_violations_report
from .reports.balance_sheet import (
    generate_balance_sheet,
    format_as_text,
    format_as_csv,
    format_as_json
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
    default="entity-map.json",
    help="Path to the entity mapping JSON file (default: entity-map.json)."
)
def entity_scan(book_file, entity_map_file):
    """
    Scan for accounts that have no entity mapping.
    
    Lists all accounts in the GnuCash book that are not currently
    mapped to any entity in the entity-map.json file.
    
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
        
        # Display results
        if not unmapped:
            click.echo("[OK] All accounts are mapped to entities.")
            sys.exit(0)
        
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
    default="entity-map.json",
    help="Path to read/write entity mapping JSON file (default: entity-map.json)."
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
            click.echo("To save this configuration:")
            click.echo(f"  gcgaap entity-infer -f {book_file} -o entity-map.json")
        
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
    default="entity-map.json",
    help="Path to the entity mapping JSON file (default: entity-map.json)."
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
    "--entity-map",
    "-e",
    "entity_map_file",
    type=click.Path(path_type=Path),
    default="entity-map.json",
    help="Path to the entity mapping JSON file (default: entity-map.json)."
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
    default="entity-map.json",
    help="Path to the entity mapping JSON file (default: entity-map.json)."
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
