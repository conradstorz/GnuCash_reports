"""Tests for gcgaap.gnucash_access."""

from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from gcgaap.gnucash_access import (
    GCAccount,
    GCTransaction,
    GCTransactionSplit,
    GnuCashBook,
    parse_date,
)


# ---------------------------------------------------------------------------
# GCAccount
# ---------------------------------------------------------------------------


class TestGCAccount:
    def test_basic_creation(self):
        acc = GCAccount(
            guid="abc123",
            full_name="Assets:Checking",
            type="BANK",
            commodity_symbol="USD",
        )
        assert acc.guid == "abc123"
        assert acc.full_name == "Assets:Checking"
        assert acc.type == "BANK"
        assert acc.commodity_symbol == "USD"
        assert acc.parent_guid is None
        assert acc.is_placeholder is False

    def test_with_parent_and_placeholder(self):
        acc = GCAccount(
            guid="child",
            full_name="Assets:Checking:Main",
            type="BANK",
            commodity_symbol="USD",
            parent_guid="parent-guid",
            is_placeholder=True,
        )
        assert acc.parent_guid == "parent-guid"
        assert acc.is_placeholder is True

    def test_is_imbalance_account_imbalance_prefix(self):
        acc = GCAccount("g", "Imbalance-USD", "BANK", "USD")
        assert acc.is_imbalance_account() is True

    def test_is_imbalance_account_case_insensitive(self):
        acc = GCAccount("g", "imbalance-EUR", "BANK", "EUR")
        assert acc.is_imbalance_account() is True

    def test_is_imbalance_account_orphan_prefix(self):
        acc = GCAccount("g", "Orphan-USD", "BANK", "USD")
        assert acc.is_imbalance_account() is True

    def test_is_imbalance_account_orphan_lowercase(self):
        acc = GCAccount("g", "orphan-GBP", "BANK", "GBP")
        assert acc.is_imbalance_account() is True

    def test_is_imbalance_account_false_for_normal(self):
        acc = GCAccount("g", "Assets:Checking", "BANK", "USD")
        assert acc.is_imbalance_account() is False

    def test_is_imbalance_account_false_for_equity(self):
        acc = GCAccount("g", "Equity:Opening Balance", "EQUITY", "USD")
        assert acc.is_imbalance_account() is False


# ---------------------------------------------------------------------------
# GCTransactionSplit
# ---------------------------------------------------------------------------


class TestGCTransactionSplit:
    def test_required_fields(self):
        split = GCTransactionSplit(account_guid="acc-001", value=100.0)
        assert split.account_guid == "acc-001"
        assert split.value == 100.0
        assert split.quantity is None
        assert split.memo is None

    def test_all_fields(self):
        split = GCTransactionSplit(
            account_guid="acc-002",
            value=-50.0,
            quantity=-50.0,
            memo="Salary deposit",
        )
        assert split.quantity == -50.0
        assert split.memo == "Salary deposit"

    def test_negative_value(self):
        split = GCTransactionSplit(account_guid="acc-003", value=-200.0)
        assert split.value == -200.0


# ---------------------------------------------------------------------------
# GCTransaction
# ---------------------------------------------------------------------------


class TestGCTransaction:
    def _make(self, *values) -> GCTransaction:
        splits = [
            GCTransactionSplit(account_guid=f"acc-{i}", value=v)
            for i, v in enumerate(values)
        ]
        return GCTransaction(
            guid="txn-001",
            post_date="2024-01-01",
            description="Test Transaction",
            splits=splits,
        )

    def test_total_value_balanced(self):
        txn = self._make(100.0, -100.0)
        assert txn.total_value() == pytest.approx(0.0)

    def test_total_value_unbalanced(self):
        txn = self._make(100.0, -90.0)
        assert txn.total_value() == pytest.approx(10.0)

    def test_total_value_multiple_splits(self):
        txn = self._make(100.0, -60.0, -40.0)
        assert txn.total_value() == pytest.approx(0.0)

    def test_total_value_empty_splits(self):
        txn = GCTransaction(guid="g", post_date="2024-01-01", description="X", splits=[])
        assert txn.total_value() == 0.0

    def test_is_balanced_true(self):
        txn = self._make(100.0, -100.0)
        assert txn.is_balanced() is True

    def test_is_balanced_within_default_tolerance(self):
        txn = self._make(100.0, -99.999)
        assert txn.is_balanced(tolerance=0.01) is True

    def test_is_balanced_within_tolerance_strictly(self):
        # 100.0 - 99.992 = 0.008, which is < 0.01
        txn = self._make(100.0, -99.992)
        assert txn.is_balanced(tolerance=0.01) is True

    def test_is_balanced_false_outside_tolerance(self):
        txn = self._make(100.0, -90.0)
        assert txn.is_balanced() is False

    def test_is_balanced_custom_tolerance(self):
        txn = self._make(100.0, -99.0)
        assert txn.is_balanced(tolerance=2.0) is True
        assert txn.is_balanced(tolerance=0.5) is False

    def test_creation_stores_fields(self):
        splits = [GCTransactionSplit("a1", 50.0), GCTransactionSplit("a2", -50.0)]
        txn = GCTransaction(
            guid="txn-xyz",
            post_date="2024-06-15",
            description="Paycheck",
            splits=splits,
        )
        assert txn.guid == "txn-xyz"
        assert txn.post_date == "2024-06-15"
        assert txn.description == "Paycheck"
        assert len(txn.splits) == 2


# ---------------------------------------------------------------------------
# GnuCashBook
# ---------------------------------------------------------------------------


class TestGnuCashBookErrors:
    def test_file_not_found_raises(self, tmp_path):
        """FileNotFoundError when the book file doesn't exist."""
        book = GnuCashBook(tmp_path / "nonexistent.gnucash")
        with pytest.raises(FileNotFoundError):
            book.__enter__()

    def test_iter_accounts_requires_open_book(self, tmp_path):
        book = GnuCashBook(tmp_path / "book.gnucash")
        with pytest.raises(RuntimeError, match="not opened"):
            list(book.iter_accounts())

    def test_iter_transactions_requires_open_book(self, tmp_path):
        book = GnuCashBook(tmp_path / "book.gnucash")
        with pytest.raises(RuntimeError, match="not opened"):
            list(book.iter_transactions())

    def test_get_account_by_guid_requires_open_book(self, tmp_path):
        book = GnuCashBook(tmp_path / "book.gnucash")
        with pytest.raises(RuntimeError, match="not opened"):
            book.get_account_by_guid("some-guid")

    def test_get_account_balances_requires_open_book(self, tmp_path):
        book = GnuCashBook(tmp_path / "book.gnucash")
        with pytest.raises(RuntimeError, match="not opened"):
            book.get_account_balances(date.today())


def _make_mock_piecash_account(
    guid: str,
    fullname: str,
    account_type: str,
    mnemonic: str = "USD",
    has_parent: bool = True,
    parent_guid: str = "parent-001",
    placeholder: bool = False,
) -> MagicMock:
    """Build a mock piecash account object."""
    mock_commodity = MagicMock()
    mock_commodity.mnemonic = mnemonic

    mock_account = MagicMock()
    mock_account.guid = guid
    mock_account.fullname = fullname
    mock_account.type = account_type
    mock_account.commodity = mock_commodity
    mock_account.placeholder = placeholder

    if has_parent:
        mock_parent = MagicMock()
        mock_parent.guid = parent_guid
        mock_account.parent = mock_parent
    else:
        mock_account.parent = None

    return mock_account


def _make_mock_piecash_transaction(
    guid: str,
    description: str,
    post_date_str: str,
    split_data: list[tuple],
) -> MagicMock:
    """
    Build a mock piecash transaction object.

    split_data: list of (account_guid, account_name, value, quantity, memo)
    """
    mock_post_date = MagicMock()
    mock_post_date.strftime.return_value = post_date_str

    splits = []
    for acct_guid, acct_name, value, quantity, memo in split_data:
        mock_split = MagicMock()
        mock_split.account.guid = acct_guid
        mock_split.account.name = acct_name
        mock_split.value = Decimal(str(value))
        mock_split.quantity = Decimal(str(quantity))
        mock_split.memo = memo
        splits.append(mock_split)

    mock_txn = MagicMock()
    mock_txn.guid = guid
    mock_txn.description = description
    mock_txn.post_date = mock_post_date
    mock_txn.splits = splits

    return mock_txn


class TestGnuCashBookIterAccounts:
    def test_converts_piecash_account_to_gc_account(self, tmp_path):
        """iter_accounts converts piecash account objects into GCAccount instances."""
        book_file = tmp_path / "book.gnucash"
        book_file.touch()

        mock_pc_acct = _make_mock_piecash_account(
            "acc-001", "Assets:Checking", "BANK", parent_guid="root-001"
        )
        mock_piecash_book = MagicMock()
        mock_piecash_book.accounts = [mock_pc_acct]

        book = GnuCashBook(book_file)
        book._book = mock_piecash_book

        accounts = list(book.iter_accounts())

        assert len(accounts) == 1
        acc = accounts[0]
        assert acc.guid == "acc-001"
        assert acc.full_name == "Assets:Checking"
        assert acc.type == "BANK"
        assert acc.commodity_symbol == "USD"
        assert acc.parent_guid == "root-001"
        assert acc.is_placeholder is False

    def test_no_parent_sets_parent_guid_none(self, tmp_path):
        """Accounts without a parent get parent_guid = None."""
        book_file = tmp_path / "book.gnucash"
        book_file.touch()

        mock_pc_acct = _make_mock_piecash_account(
            "root-001", "Root", "ASSET", has_parent=False
        )
        mock_piecash_book = MagicMock()
        mock_piecash_book.accounts = [mock_pc_acct]

        book = GnuCashBook(book_file)
        book._book = mock_piecash_book

        accounts = list(book.iter_accounts())
        assert accounts[0].parent_guid is None

    def test_placeholder_flag_preserved(self, tmp_path):
        book_file = tmp_path / "book.gnucash"
        book_file.touch()

        mock_pc_acct = _make_mock_piecash_account(
            "ph-001", "Placeholder Account", "ASSET", placeholder=True
        )
        mock_piecash_book = MagicMock()
        mock_piecash_book.accounts = [mock_pc_acct]

        book = GnuCashBook(book_file)
        book._book = mock_piecash_book

        accounts = list(book.iter_accounts())
        assert accounts[0].is_placeholder is True

    def test_multiple_accounts(self, tmp_path):
        book_file = tmp_path / "book.gnucash"
        book_file.touch()

        pc_accounts = [
            _make_mock_piecash_account("a1", "Assets:Checking", "BANK"),
            _make_mock_piecash_account("a2", "Income:Salary", "INCOME"),
            _make_mock_piecash_account("a3", "Expenses:Food", "EXPENSE"),
        ]
        mock_piecash_book = MagicMock()
        mock_piecash_book.accounts = pc_accounts

        book = GnuCashBook(book_file)
        book._book = mock_piecash_book

        accounts = list(book.iter_accounts())
        assert len(accounts) == 3
        guids = {acc.guid for acc in accounts}
        assert guids == {"a1", "a2", "a3"}


class TestGnuCashBookIterTransactions:
    def test_converts_piecash_transaction(self, tmp_path):
        """iter_transactions converts piecash transactions to GCTransaction."""
        book_file = tmp_path / "book.gnucash"
        book_file.touch()

        mock_txn = _make_mock_piecash_transaction(
            "txn-001",
            "Paycheck",
            "2024-01-15",
            [
                ("acc-001", "Checking", 1000.0, 1000.0, "deposit"),
                ("acc-002", "Income", -1000.0, -1000.0, None),
            ],
        )
        mock_piecash_book = MagicMock()
        mock_piecash_book.transactions = [mock_txn]

        book = GnuCashBook(book_file)
        book._book = mock_piecash_book

        transactions = list(book.iter_transactions())

        assert len(transactions) == 1
        txn = transactions[0]
        assert txn.guid == "txn-001"
        assert txn.post_date == "2024-01-15"
        assert txn.description == "Paycheck"
        assert len(txn.splits) == 2
        assert txn.splits[0].value == pytest.approx(1000.0)
        assert txn.splits[0].memo == "deposit"
        assert txn.splits[1].value == pytest.approx(-1000.0)
        assert txn.splits[1].memo is None

    def test_bad_date_transaction_causes_value_error(self, tmp_path):
        """iter_transactions raises ValueError after encountering a bad-date transaction."""
        book_file = tmp_path / "book.gnucash"
        book_file.touch()

        # Transaction with a post_date that fails strftime
        bad_post_date = MagicMock()
        bad_post_date.strftime.side_effect = ValueError("Couldn't parse datetime string: ''")

        mock_split = MagicMock()
        mock_split.account.name = "Checking"
        mock_split.account.guid = "acc-001"
        mock_split.value = Decimal("50.00")
        mock_split.quantity = Decimal("50.00")
        mock_split.memo = None

        mock_txn = MagicMock()
        mock_txn.guid = "txn-bad"
        mock_txn.description = "Bad transaction"
        mock_txn.post_date = bad_post_date
        mock_txn.splits = [mock_split]

        mock_piecash_book = MagicMock()
        mock_piecash_book.transactions = [mock_txn]

        book = GnuCashBook(book_file)
        book._book = mock_piecash_book

        with pytest.raises(ValueError, match="data integrity"):
            list(book.iter_transactions())

    def test_good_transactions_yielded_before_error(self, tmp_path):
        """
        Healthy transactions are yielded before the ValueError is raised at the end.

        The generator yields all valid transactions, then raises ValueError
        after the loop if any bad ones were encountered.
        """
        book_file = tmp_path / "book.gnucash"
        book_file.touch()

        good_txn = _make_mock_piecash_transaction(
            "txn-good", "Good", "2024-01-01",
            [("a1", "Checking", 100.0, 100.0, None), ("a2", "Income", -100.0, -100.0, None)],
        )
        bad_post_date = MagicMock()
        bad_post_date.strftime.side_effect = ValueError("Couldn't parse datetime string: ''")

        bad_split = MagicMock()
        bad_split.account.name = "Checking"
        bad_split.account.guid = "acc-001"
        bad_split.value = Decimal("50.00")
        bad_split.quantity = Decimal("50.00")
        bad_split.memo = None

        bad_txn = MagicMock()
        bad_txn.guid = "txn-bad"
        bad_txn.description = "Bad"
        bad_txn.post_date = bad_post_date
        bad_txn.splits = [bad_split]

        mock_piecash_book = MagicMock()
        mock_piecash_book.transactions = [good_txn, bad_txn]

        book = GnuCashBook(book_file)
        book._book = mock_piecash_book

        # Using a generator manually: consume good transaction then see error
        gen = book.iter_transactions()
        first = next(gen)
        assert first.guid == "txn-good"

        with pytest.raises(ValueError):
            next(gen)  # this triggers the end-of-loop raise


class TestGnuCashBookGetAccountByGuid:
    def test_found(self, tmp_path):
        book_file = tmp_path / "book.gnucash"
        book_file.touch()

        mock_pc_acct = _make_mock_piecash_account("acc-999", "Assets:Savings", "BANK")
        mock_piecash_book = MagicMock()
        mock_piecash_book.accounts = [mock_pc_acct]

        book = GnuCashBook(book_file)
        book._book = mock_piecash_book

        result = book.get_account_by_guid("acc-999")
        assert result is not None
        assert result.guid == "acc-999"

    def test_not_found_returns_none(self, tmp_path):
        book_file = tmp_path / "book.gnucash"
        book_file.touch()

        mock_piecash_book = MagicMock()
        mock_piecash_book.accounts = []

        book = GnuCashBook(book_file)
        book._book = mock_piecash_book

        assert book.get_account_by_guid("nonexistent") is None


class TestGnuCashBookContextManager:
    def test_exit_closes_book(self, tmp_path):
        """__exit__ calls close() on the piecash book and clears _book."""
        book_file = tmp_path / "book.gnucash"
        book_file.touch()

        mock_piecash_book = MagicMock()
        book = GnuCashBook(book_file)
        book._book = mock_piecash_book

        book.__exit__(None, None, None)

        mock_piecash_book.close.assert_called_once()
        assert book._book is None

    def test_exit_clears_book_even_if_close_raises(self, tmp_path):
        """_book is set to None even if close() raises an exception."""
        book_file = tmp_path / "book.gnucash"
        book_file.touch()

        mock_piecash_book = MagicMock()
        mock_piecash_book.close.side_effect = RuntimeError("close error")

        book = GnuCashBook(book_file)
        book._book = mock_piecash_book

        book.__exit__(None, None, None)  # Should not raise
        assert book._book is None


# ---------------------------------------------------------------------------
# parse_date
# ---------------------------------------------------------------------------


class TestParseDate:
    def test_valid_date(self):
        d = parse_date("2024-01-15")
        assert d == date(2024, 1, 15)

    def test_valid_date_end_of_year(self):
        d = parse_date("2023-12-31")
        assert d == date(2023, 12, 31)

    def test_valid_date_start_of_year(self):
        d = parse_date("2025-01-01")
        assert d == date(2025, 1, 1)

    def test_wrong_format_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid date format"):
            parse_date("01/15/2024")

    def test_invalid_month_raises(self):
        with pytest.raises(ValueError):
            parse_date("2024-13-01")

    def test_invalid_day_raises(self):
        with pytest.raises(ValueError):
            parse_date("2024-01-32")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            parse_date("")

    def test_slash_format_raises(self):
        with pytest.raises(ValueError):
            parse_date("2024/01/15")
