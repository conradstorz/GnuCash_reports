"""Tests for gcgaap.repair."""

from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from gcgaap.repair import (
    RepairResult,
    create_backup,
    diagnose_empty_reconcile_dates,
    repair_empty_reconcile_dates,
    verify_repair,
)


# ---------------------------------------------------------------------------
# RepairResult
# ---------------------------------------------------------------------------


class TestRepairResult:
    def test_creation_success(self, tmp_path):
        result = RepairResult(
            success=True,
            items_fixed=5,
            backup_path=tmp_path / "backup.gnucash",
            message="All fixed",
        )
        assert result.success is True
        assert result.items_fixed == 5
        assert result.message == "All fixed"

    def test_creation_failure(self, tmp_path):
        result = RepairResult(
            success=False,
            items_fixed=0,
            backup_path=tmp_path / "backup.gnucash",
            message="Nothing to fix",
        )
        assert result.success is False

    def test_backup_path_field(self, tmp_path):
        bp = tmp_path / "backup.gnucash"
        result = RepairResult(success=True, items_fixed=3, backup_path=bp, message="ok")
        assert result.backup_path == bp


# ---------------------------------------------------------------------------
# create_backup
# ---------------------------------------------------------------------------


class TestCreateBackup:
    def test_creates_backup_file_with_same_content(self, tmp_path):
        db_path = tmp_path / "mybook.gnucash"
        db_path.write_bytes(b"fake gnucash content")

        backup = create_backup(db_path)

        assert backup.exists()
        assert backup.read_bytes() == b"fake gnucash content"

    def test_backup_filename_contains_backup_marker(self, tmp_path):
        db_path = tmp_path / "mybook.gnucash"
        db_path.write_bytes(b"data")

        backup = create_backup(db_path)

        assert ".backup_" in str(backup.name)

    def test_backup_has_gnucash_extension(self, tmp_path):
        db_path = tmp_path / "mybook.gnucash"
        db_path.write_bytes(b"data")

        backup = create_backup(db_path)

        assert backup.suffix == ".gnucash"

    def test_backup_in_same_directory(self, tmp_path):
        db_path = tmp_path / "mybook.gnucash"
        db_path.write_bytes(b"data")

        backup = create_backup(db_path)

        assert backup.parent == tmp_path

    def test_raises_io_error_when_source_missing(self, tmp_path):
        """create_backup raises IOError when the source file does not exist."""
        db_path = tmp_path / "nonexistent.gnucash"

        with pytest.raises(IOError, match="Could not create backup"):
            create_backup(db_path)


# ---------------------------------------------------------------------------
# diagnose_empty_reconcile_dates
# ---------------------------------------------------------------------------


class TestDiagnoseEmptyReconcileDates:
    def _setup_mock_conn(self, count: int, descriptions: list[str]) -> MagicMock:
        """Build a mock sqlite3 connection for diagnose tests."""
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = lambda s: s
        mock_conn.__exit__ = MagicMock(return_value=False)

        # fetchone returns a dict-like row for row_factory = sqlite3.Row pattern
        count_row = {"count": count}
        desc_rows = [{"description": d} for d in descriptions]

        mock_cursor.fetchone.return_value = count_row
        mock_cursor.fetchall.return_value = desc_rows

        return mock_conn

    def test_returns_count_and_descriptions(self, tmp_path):
        db_path = tmp_path / "book.gnucash"
        db_path.touch()

        mock_conn = self._setup_mock_conn(3, ["Txn A", "Txn B"])

        with patch("gcgaap.repair.sqlite3.connect", return_value=mock_conn):
            count, descs = diagnose_empty_reconcile_dates(db_path)

        assert count == 3
        assert descs == ["Txn A", "Txn B"]

    def test_connection_closed_after_diagnosis(self, tmp_path):
        db_path = tmp_path / "book.gnucash"
        db_path.touch()

        mock_conn = self._setup_mock_conn(0, [])

        with patch("gcgaap.repair.sqlite3.connect", return_value=mock_conn):
            diagnose_empty_reconcile_dates(db_path)

        mock_conn.close.assert_called_once()

    def test_zero_count_no_descriptions(self, tmp_path):
        db_path = tmp_path / "book.gnucash"
        db_path.touch()

        mock_conn = self._setup_mock_conn(0, [])

        with patch("gcgaap.repair.sqlite3.connect", return_value=mock_conn):
            count, descs = diagnose_empty_reconcile_dates(db_path)

        assert count == 0
        assert descs == []


# ---------------------------------------------------------------------------
# repair_empty_reconcile_dates
# ---------------------------------------------------------------------------


def _setup_repair_conn(count_before: int, count_after: int, rows_affected: int) -> MagicMock:
    """
    Build a mock connection for repair_empty_reconcile_dates.

    The function calls cursor.fetchone() twice:
        1. COUNT before repair  → returns (count_before,)
        2. COUNT after repair   → returns (count_after,)
    cursor.rowcount is used to determine how many rows were fixed.
    """
    mock_cursor = MagicMock()
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    mock_cursor.fetchone.side_effect = [(count_before,), (count_after,)]
    mock_cursor.rowcount = rows_affected

    return mock_conn, mock_cursor


class TestRepairEmptyReconcileDates:
    def test_no_issues_found_returns_clean_result(self, tmp_path):
        db_path = tmp_path / "book.gnucash"
        db_path.touch()

        mock_conn, _ = _setup_repair_conn(0, 0, 0)

        with patch("gcgaap.repair.sqlite3.connect", return_value=mock_conn):
            with patch("gcgaap.repair.create_backup") as mock_backup:
                mock_backup.return_value = tmp_path / "backup.gnucash"
                result = repair_empty_reconcile_dates(db_path)

        assert result.success is True
        assert result.items_fixed == 0
        assert "clean" in result.message.lower()

    def test_successful_repair_returns_fixed_count(self, tmp_path):
        db_path = tmp_path / "book.gnucash"
        db_path.touch()

        mock_conn, _ = _setup_repair_conn(5, 0, 5)

        with patch("gcgaap.repair.sqlite3.connect", return_value=mock_conn):
            with patch("gcgaap.repair.create_backup") as mock_backup:
                mock_backup.return_value = tmp_path / "backup.gnucash"
                result = repair_empty_reconcile_dates(db_path)

        assert result.success is True
        assert result.items_fixed == 5
        mock_conn.commit.assert_called_once()

    def test_partial_repair_returns_failure(self, tmp_path):
        db_path = tmp_path / "book.gnucash"
        db_path.touch()

        mock_conn, _ = _setup_repair_conn(5, 2, 3)

        with patch("gcgaap.repair.sqlite3.connect", return_value=mock_conn):
            with patch("gcgaap.repair.create_backup") as mock_backup:
                mock_backup.return_value = tmp_path / "backup.gnucash"
                result = repair_empty_reconcile_dates(db_path)

        assert result.success is False
        assert result.items_fixed == 3
        assert "Partial" in result.message or "partial" in result.message.lower()

    def test_backup_created_by_default(self, tmp_path):
        db_path = tmp_path / "book.gnucash"
        db_path.touch()

        mock_conn, _ = _setup_repair_conn(0, 0, 0)

        with patch("gcgaap.repair.sqlite3.connect", return_value=mock_conn):
            with patch("gcgaap.repair.create_backup") as mock_backup:
                mock_backup.return_value = tmp_path / "backup.gnucash"
                repair_empty_reconcile_dates(db_path, create_backup_first=True)

        mock_backup.assert_called_once_with(db_path)

    def test_no_backup_when_disabled(self, tmp_path):
        db_path = tmp_path / "book.gnucash"
        db_path.touch()

        mock_conn, _ = _setup_repair_conn(0, 0, 0)

        with patch("gcgaap.repair.sqlite3.connect", return_value=mock_conn):
            with patch("gcgaap.repair.create_backup") as mock_backup:
                result = repair_empty_reconcile_dates(db_path, create_backup_first=False)

        mock_backup.assert_not_called()
        assert result.backup_path is None

    def test_connection_closed_after_repair(self, tmp_path):
        db_path = tmp_path / "book.gnucash"
        db_path.touch()

        mock_conn, _ = _setup_repair_conn(0, 0, 0)

        with patch("gcgaap.repair.sqlite3.connect", return_value=mock_conn):
            with patch("gcgaap.repair.create_backup") as mock_backup:
                mock_backup.return_value = tmp_path / "backup.gnucash"
                repair_empty_reconcile_dates(db_path)

        mock_conn.close.assert_called_once()


# ---------------------------------------------------------------------------
# verify_repair
# ---------------------------------------------------------------------------


class TestVerifyRepair:
    def _setup_conn_for_verify(self, rows: list[dict]) -> MagicMock:
        """rows: list of dicts like {'description': '...', 'empty_dates': N}."""
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.side_effect = rows
        return mock_conn

    def test_all_clean_returns_true(self, tmp_path):
        db_path = tmp_path / "book.gnucash"
        db_path.touch()

        mock_conn = self._setup_conn_for_verify([
            {"description": "Test Txn", "empty_dates": 0},
        ])

        with patch("gcgaap.repair.sqlite3.connect", return_value=mock_conn):
            result = verify_repair(db_path, ["guid-001"])

        assert result is True

    def test_dirty_transaction_returns_false(self, tmp_path):
        db_path = tmp_path / "book.gnucash"
        db_path.touch()

        mock_conn = self._setup_conn_for_verify([
            {"description": "Bad Txn", "empty_dates": 2},
        ])

        with patch("gcgaap.repair.sqlite3.connect", return_value=mock_conn):
            result = verify_repair(db_path, ["guid-bad"])

        assert result is False

    def test_mixed_results_returns_false(self, tmp_path):
        db_path = tmp_path / "book.gnucash"
        db_path.touch()

        mock_conn = self._setup_conn_for_verify([
            {"description": "Clean Txn", "empty_dates": 0},
            {"description": "Dirty Txn", "empty_dates": 1},
        ])

        with patch("gcgaap.repair.sqlite3.connect", return_value=mock_conn):
            result = verify_repair(db_path, ["guid-clean", "guid-dirty"])

        assert result is False

    def test_empty_guid_list_returns_true(self, tmp_path):
        db_path = tmp_path / "book.gnucash"
        db_path.touch()

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = MagicMock()

        with patch("gcgaap.repair.sqlite3.connect", return_value=mock_conn):
            result = verify_repair(db_path, [])

        assert result is True

    def test_connection_closed_after_verify(self, tmp_path):
        db_path = tmp_path / "book.gnucash"
        db_path.touch()

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None  # guid not found → skip
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with patch("gcgaap.repair.sqlite3.connect", return_value=mock_conn):
            verify_repair(db_path, ["guid-missing"])

        mock_conn.close.assert_called_once()
