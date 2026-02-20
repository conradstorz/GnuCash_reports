"""
Command-line interface for GCGAAP.

Registers four command groups:
    entity   — entity mapping and inference
    report   — financial report generation
    xact     — transaction analysis and balancing
    db       — database validation, repair, and snapshots
"""

import logging

import click

from . import __version__
from .config import setup_logging
from .commands.entity import entity_group
from .commands.report import report_group
from .commands.xact import xact_group
from .commands.db import db_group

logger = logging.getLogger(__name__)


@click.group()
@click.version_option(version=__version__, prog_name="gcgaap")
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose (DEBUG level) logging.",
)
@click.pass_context
def main(ctx, verbose):
    """
    GCGAAP - GnuCash GAAP Validation and Reporting.

    A command-line tool for validating GnuCash books and generating
    GAAP-style financial reports with strict accounting equation enforcement.
    """
    setup_logging(verbose)
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    logger.debug(f"GCGAAP version {__version__}")


main.add_command(entity_group)
main.add_command(report_group)
main.add_command(xact_group)
main.add_command(db_group)


if __name__ == "__main__":
    main()
