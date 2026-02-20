"""CLI smoke tests using Click's CliRunner."""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from gcgaap.cli import main
from gcgaap.validate import ValidationResult


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ---------------------------------------------------------------------------
# Main group
# ---------------------------------------------------------------------------


class TestMainGroup:
    def test_version_option(self, runner):
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.2.0" in result.output

    def test_help_shows_all_subgroups(self, runner):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "entity" in result.output
        assert "report" in result.output
        assert "xact" in result.output
        assert "db" in result.output

    def test_help_shows_description(self, runner):
        result = runner.invoke(main, ["--help"])
        assert "GCGAAP" in result.output

    def test_no_args_shows_help(self, runner):
        """Invoked with no arguments, Click shows help and exits 0."""
        result = runner.invoke(main, [])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# entity subgroup
# ---------------------------------------------------------------------------


class TestEntityGroup:
    def test_entity_help_shows_commands(self, runner):
        result = runner.invoke(main, ["entity", "--help"])
        assert result.exit_code == 0
        assert "scan" in result.output
        assert "infer" in result.output
        assert "remap" in result.output

    def test_entity_scan_help(self, runner):
        result = runner.invoke(main, ["entity", "scan", "--help"])
        assert result.exit_code == 0

    def test_entity_infer_help(self, runner):
        result = runner.invoke(main, ["entity", "infer", "--help"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# report subgroup
# ---------------------------------------------------------------------------


class TestReportGroup:
    def test_report_help_shows_commands(self, runner):
        result = runner.invoke(main, ["report", "--help"])
        assert result.exit_code == 0
        assert "balance-sheet" in result.output
        assert "balance-check" in result.output

    def test_report_balance_sheet_help(self, runner):
        result = runner.invoke(main, ["report", "balance-sheet", "--help"])
        assert result.exit_code == 0

    def test_report_balance_check_help(self, runner):
        result = runner.invoke(main, ["report", "balance-check", "--help"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# xact subgroup
# ---------------------------------------------------------------------------


class TestXactGroup:
    def test_xact_help_shows_commands(self, runner):
        result = runner.invoke(main, ["xact", "--help"])
        assert result.exit_code == 0
        assert "cross-entity" in result.output
        assert "balance" in result.output

    def test_xact_cross_entity_help(self, runner):
        result = runner.invoke(main, ["xact", "cross-entity", "--help"])
        assert result.exit_code == 0

    def test_xact_balance_help(self, runner):
        result = runner.invoke(main, ["xact", "balance", "--help"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# db subgroup
# ---------------------------------------------------------------------------


class TestDbGroup:
    def test_db_help_shows_all_commands(self, runner):
        result = runner.invoke(main, ["db", "--help"])
        assert result.exit_code == 0
        assert "validate" in result.output
        assert "violations" in result.output
        assert "repair-dates" in result.output
        assert "snapshot" in result.output
        assert "diff-snapshots" in result.output

    def test_db_validate_missing_file_exits_nonzero(self, runner):
        """db validate fails (exit 2) when --file points to a nonexistent file."""
        result = runner.invoke(main, ["db", "validate", "--file", "/nonexistent/book.gnucash"])
        assert result.exit_code != 0

    def test_db_validate_requires_file_flag(self, runner):
        """db validate with no --file flag exits with a non-zero code."""
        result = runner.invoke(main, ["db", "validate"])
        assert result.exit_code != 0

    def test_db_validate_clean_book_exits_zero(self, runner, tmp_path):
        """
        db validate exits 0 when validation finds no errors.

        Mocks GnuCashBook, EntityMap.load, and validate_book so no real
        GnuCash file is needed.
        """
        from tests.helpers import MockBook, make_account

        book_file = tmp_path / "test.gnucash"
        book_file.touch()

        mock_book_instance = MockBook(
            accounts=[make_account("acc-001", "Assets:Checking", "BANK")],
            transactions=[],
        )
        clean_result = ValidationResult()

        with patch("gcgaap.commands.db.GnuCashBook", return_value=mock_book_instance):
            with patch("gcgaap.commands.db.EntityMap") as mock_em_class:
                mock_em_class.load.return_value = MagicMock(entities={})
                with patch("gcgaap.commands.db.validate_book", return_value=clean_result):
                    result = runner.invoke(
                        main,
                        ["db", "validate", "--file", str(book_file), "--quiet"],
                    )

        assert result.exit_code == 0

    def test_db_validate_errors_exits_nonzero(self, runner, tmp_path):
        """db validate exits non-zero when validation finds errors."""
        from tests.helpers import MockBook, make_account

        book_file = tmp_path / "test.gnucash"
        book_file.touch()

        mock_book_instance = MockBook(accounts=[], transactions=[])
        error_result = ValidationResult()
        error_result.add_error("Something is broken")

        with patch("gcgaap.commands.db.GnuCashBook", return_value=mock_book_instance):
            with patch("gcgaap.commands.db.EntityMap") as mock_em_class:
                mock_em_class.load.return_value = MagicMock(entities={})
                with patch("gcgaap.commands.db.validate_book", return_value=error_result):
                    result = runner.invoke(
                        main,
                        ["db", "validate", "--file", str(book_file), "--quiet"],
                    )

        assert result.exit_code != 0

    def test_db_validate_json_format(self, runner, tmp_path):
        """db validate --format json outputs valid JSON."""
        import json as json_mod

        from tests.helpers import MockBook

        book_file = tmp_path / "test.gnucash"
        book_file.touch()

        mock_book_instance = MockBook(accounts=[], transactions=[])
        clean_result = ValidationResult()

        with patch("gcgaap.commands.db.GnuCashBook", return_value=mock_book_instance):
            with patch("gcgaap.commands.db.EntityMap") as mock_em_class:
                mock_em_class.load.return_value = MagicMock(entities={})
                with patch("gcgaap.commands.db.validate_book", return_value=clean_result):
                    result = runner.invoke(
                        main,
                        [
                            "db", "validate",
                            "--file", str(book_file),
                            "--format", "json",
                            "--quiet",
                        ],
                    )

        assert result.exit_code == 0
        # Output should contain JSON
        data = json_mod.loads(result.output)
        assert "status" in data

    def test_db_repair_dates_help(self, runner):
        result = runner.invoke(main, ["db", "repair-dates", "--help"])
        assert result.exit_code == 0
        assert "--diagnose-only" in result.output or "diagnose" in result.output

    def test_db_snapshot_help(self, runner):
        result = runner.invoke(main, ["db", "snapshot", "--help"])
        assert result.exit_code == 0

    def test_db_diff_snapshots_help(self, runner):
        result = runner.invoke(main, ["db", "diff-snapshots", "--help"])
        assert result.exit_code == 0
