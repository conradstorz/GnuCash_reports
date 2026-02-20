"""
Entity command group for gcgaap.

Commands: scan, infer, remap
"""

import json
import logging
import sys
from pathlib import Path

import click

from ..entity_map import EntityMap
from ..gnucash_access import GnuCashBook
from ..validate import scan_unmapped_accounts, check_cross_entity_balancing_accounts
from ..entity_inference import EntityInferenceEngine, build_entity_map_from_suggestions, merge_entity_maps
from ._options import book_file_option, entity_map_option, output_file_option

logger = logging.getLogger(__name__)


@click.group(name="entity")
def entity_group():
    """Entity mapping and inference commands."""


@entity_group.command(name="scan")
@book_file_option
@entity_map_option()
def scan(book_file, entity_map_file):
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
        entity_map = EntityMap.load(entity_map_file)

        with GnuCashBook(book_file) as book:
            unmapped = scan_unmapped_accounts(book, entity_map)
            balancing_status = check_cross_entity_balancing_accounts(book, entity_map)

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

        click.echo("=" * 80)
        click.echo(
            f"Summary: {len(entities_with_balancing)} entities with balancing accounts, "
            f"{len(entities_without_balancing)} without"
        )
        click.echo("=" * 80)

        sys.exit(0)

    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error during entity scan: {e}", exc_info=True)
        sys.exit(1)


@entity_group.command(name="infer")
@book_file_option
@entity_map_option()
@output_file_option(required=False)
@click.option(
    "--merge/--no-merge",
    default=False,
    help="Merge suggestions with existing entity-map file.",
)
def infer(book_file, entity_map_file, output_file, merge):
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
        engine = EntityInferenceEngine()

        with GnuCashBook(book_file) as book:
            result = engine.analyze_book(book)

        click.echo("\n=== Analysis Summary ===\n")
        for note in result.analysis_notes:
            click.echo(f"  {note}")

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

        if result.unmapped_accounts:
            click.echo(f"=== Unmapped Accounts ({len(result.unmapped_accounts)}) ===\n")
            click.echo("These accounts don't match suggested patterns and may need manual mapping:\n")
            for account in result.unmapped_accounts[:10]:
                click.echo(f"  - {account.full_name}")
            if len(result.unmapped_accounts) > 10:
                click.echo(f"  ... and {len(result.unmapped_accounts) - 10} more")
            click.echo()

        suggested_map = build_entity_map_from_suggestions(result.suggestions)

        if merge and entity_map_file.exists():
            click.echo(f"Merging with existing entity map from {entity_map_file}")
            existing_map = EntityMap.load(entity_map_file)
            suggested_map = merge_entity_maps(existing_map, suggested_map)

        if output_file:
            suggested_map.save(output_file)
            click.echo(f"\n[OK] Suggested entity map saved to: {output_file}")
        else:
            click.echo("\n=== Suggested Entity Map JSON ===\n")

            map_dict = {
                "version": suggested_map.version,
                "entities": {
                    key: {"label": entity.label, "type": entity.type}
                    for key, entity in suggested_map.entities.items()
                },
                "accounts": suggested_map.account_entities,
                "patterns": suggested_map.patterns,
            }

            click.echo(json.dumps(map_dict, indent=2))
            click.echo()
            click.echo("To regenerate entity mapping:")
            click.echo(f"  gcgaap entity remap -f {book_file}")

        sys.exit(0)

    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error during entity inference: {e}", exc_info=True)
        sys.exit(1)


@entity_group.command(name="remap")
@book_file_option
@output_file_option(required=False, default="entity_account_map.json")
@click.pass_context
def remap(ctx, book_file, output_file):
    """
    Regenerate entity account mapping from GnuCash database.

    Scans all accounts in the GnuCash book and maps them to entities
    based on naming patterns. Uses parent-child inheritance for entity
    assignment.

    This is the canonical way to generate the entity_account_map.json
    file that gcgaap uses for all entity-based operations.
    """
    verbose = ctx.obj.get("verbose", False) if ctx.obj else False

    logger.info("=== GCGAAP Entity Remapping ===")

    try:
        import sys as _sys
        tools_path = Path(__file__).parent.parent / "tools"
        _sys.path.insert(0, str(tools_path))

        from entity_account_mapper import (
            build_entity_patterns,
            build_account_tree,
            assign_entities_with_inheritance,
            generate_entity_report,
            generate_summary,
            ENTITIES,
        )
        from piecash import open_book

        if verbose:
            click.echo(f"Opening GnuCash database: {book_file}")

        book = open_book(str(book_file), readonly=True, do_backup=False)

        try:
            if verbose:
                click.echo("Building entity patterns...")
            entity_patterns = build_entity_patterns()

            if verbose:
                click.echo("Building account tree...")
            accounts_dict, root_accounts = build_account_tree(book)

            if verbose:
                click.echo(f"Found {len(accounts_dict)} accounts")

            if verbose:
                click.echo("Assigning entities to accounts...")
            assign_entities_with_inheritance(accounts_dict, root_accounts, entity_patterns)

            if verbose:
                click.echo("Generating report...")
            report = generate_entity_report(accounts_dict)
            summary = generate_summary(report)

            output = {
                "summary": summary,
                "entities": report,
            }

            output_path = Path(output_file)
            with open(output_path, "w", encoding="utf-8") as f:
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
