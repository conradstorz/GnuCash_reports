"""
Shared Click option decorators for gcgaap command groups.

Each decorator factory wraps a single Click option so it can be reused
across multiple commands without repeating the option definition.
"""

from pathlib import Path

import click


def book_file_option(func):
    """--file/-f: required path to a GnuCash book file."""
    return click.option(
        "--file",
        "-f",
        "book_file",
        type=click.Path(exists=True, path_type=Path),
        required=True,
        help="Path to the GnuCash book file (.gnucash).",
    )(func)


def entity_map_option(default: str = "entity_account_map.json"):
    """--entity-map/-e: path to the entity mapping JSON file."""
    def decorator(func):
        return click.option(
            "--entity-map",
            "-e",
            "entity_map_file",
            type=click.Path(path_type=Path),
            default=default,
            help=f"Path to the entity mapping JSON file (default: {default}).",
        )(func)
    return decorator


def as_of_option(required: bool = False):
    """--as-of: balance sheet / analysis date in YYYY-MM-DD format."""
    def decorator(func):
        return click.option(
            "--as-of",
            type=str,
            required=required,
            default=None,
            help="Date in YYYY-MM-DD format.",
        )(func)
    return decorator


def format_option(choices: tuple = ("text", "json", "csv")):
    """--format: output format selector."""
    def decorator(func):
        return click.option(
            "--format",
            type=click.Choice(list(choices), case_sensitive=False),
            default=choices[0],
            help=f"Output format (default: {choices[0]}).",
        )(func)
    return decorator


def entity_filter_option(func):
    """--entity: optional entity key to filter results."""
    return click.option(
        "--entity",
        type=str,
        default=None,
        help="Entity key to filter results.",
    )(func)


def tolerance_option(func):
    """--tolerance/-t: numeric tolerance for balance checks."""
    return click.option(
        "--tolerance",
        "-t",
        type=float,
        default=0.01,
        help="Numeric tolerance for balance checks (default: 0.01).",
    )(func)


def output_file_option(required: bool = False, default=None):
    """--output/-o: output file path."""
    def decorator(func):
        return click.option(
            "--output",
            "-o",
            "output_file",
            type=click.Path(path_type=Path),
            required=required,
            default=default,
            help="Output file path.",
        )(func)
    return decorator
