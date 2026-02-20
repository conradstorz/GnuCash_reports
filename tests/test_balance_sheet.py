"""Tests for gcgaap.reports.balance_sheet."""

import json
from datetime import date
from unittest.mock import patch

import pytest

from gcgaap.config import GCGAAPConfig
from gcgaap.entity_map import EntityDefinition, EntityMap
from gcgaap.gnucash_access import GCAccount
from gcgaap.reports.balance_sheet import (
    BalanceCheckResult,
    BalanceSheet,
    BalanceSheetLine,
    check_entity_balance,
    classify_account_type,
    format_as_csv,
    format_as_json,
    format_as_text,
    generate_balance_sheet,
)
from tests.helpers import MockBook, make_account


# ---------------------------------------------------------------------------
# classify_account_type
# ---------------------------------------------------------------------------


def _acct(account_type: str, full_name: str = "Test Account") -> GCAccount:
    return GCAccount(
        guid="g",
        full_name=full_name,
        type=account_type,
        commodity_symbol="USD",
    )


class TestClassifyAccountType:
    def test_bank_is_asset(self):
        assert classify_account_type(_acct("BANK")) == "ASSET"

    def test_cash_is_asset(self):
        assert classify_account_type(_acct("CASH")) == "ASSET"

    def test_stock_is_asset(self):
        assert classify_account_type(_acct("STOCK")) == "ASSET"

    def test_mutual_is_asset(self):
        assert classify_account_type(_acct("MUTUAL")) == "ASSET"

    def test_receivable_is_asset(self):
        assert classify_account_type(_acct("RECEIVABLE")) == "ASSET"

    def test_trading_is_asset(self):
        assert classify_account_type(_acct("TRADING")) == "ASSET"

    def test_asset_type_is_asset(self):
        assert classify_account_type(_acct("ASSET")) == "ASSET"

    def test_credit_without_credit_in_name_is_asset(self):
        """CREDIT type with a non-credit name is treated as an asset."""
        assert classify_account_type(_acct("CREDIT", "Assets:Trading Line")) == "ASSET"

    def test_credit_with_credit_in_name_is_liability(self):
        """CREDIT type with 'credit' in the full name is a liability (credit card)."""
        acc = _acct("CREDIT", "Liabilities:Credit Card")
        assert classify_account_type(acc) == "LIABILITY"

    def test_liability_is_liability(self):
        assert classify_account_type(_acct("LIABILITY")) == "LIABILITY"

    def test_payable_is_liability(self):
        assert classify_account_type(_acct("PAYABLE")) == "LIABILITY"

    def test_equity_is_equity(self):
        assert classify_account_type(_acct("EQUITY")) == "EQUITY"

    def test_income_is_income(self):
        assert classify_account_type(_acct("INCOME")) == "INCOME"

    def test_expense_is_expense(self):
        assert classify_account_type(_acct("EXPENSE")) == "EXPENSE"

    def test_unknown_type_is_other(self):
        assert classify_account_type(_acct("WEIRD_TYPE")) == "OTHER"

    def test_lowercase_type_handled(self):
        """Type comparison is case-insensitive via .upper()."""
        acc = _acct("bank")
        # type.upper() == "BANK" → ASSET
        assert classify_account_type(acc) == "ASSET"


# ---------------------------------------------------------------------------
# BalanceSheetLine
# ---------------------------------------------------------------------------


class TestBalanceSheetLine:
    def test_default_level_is_zero(self):
        line = BalanceSheetLine(
            account_guid="a1",
            account_name="Assets:Checking",
            account_type="BANK",
            balance=1000.0,
        )
        assert line.level == 0
        assert line.balance == 1000.0

    def test_custom_level(self):
        line = BalanceSheetLine("a1", "Assets:Checking:Main", "BANK", 500.0, level=2)
        assert line.level == 2


# ---------------------------------------------------------------------------
# BalanceSheet
# ---------------------------------------------------------------------------


def _sample_balance_sheet() -> BalanceSheet:
    bs = BalanceSheet(as_of_date=date(2024, 12, 31))
    bs.assets = [
        BalanceSheetLine("a1", "Assets:Checking", "BANK", 100.0),
        BalanceSheetLine("a2", "Assets:Savings", "BANK", 200.0),
    ]
    bs.liabilities = [
        BalanceSheetLine("l1", "Liabilities:Card", "LIABILITY", 50.0),
    ]
    bs.equity = [
        BalanceSheetLine("e1", "Equity:Opening", "EQUITY", 250.0),
    ]
    return bs


class TestBalanceSheetProperties:
    def test_total_assets(self):
        bs = _sample_balance_sheet()
        assert bs.total_assets == pytest.approx(300.0)

    def test_total_liabilities(self):
        bs = _sample_balance_sheet()
        assert bs.total_liabilities == pytest.approx(50.0)

    def test_total_equity(self):
        bs = _sample_balance_sheet()
        assert bs.total_equity == pytest.approx(250.0)

    def test_total_liabilities_and_equity(self):
        bs = _sample_balance_sheet()
        assert bs.total_liabilities_and_equity == pytest.approx(300.0)

    def test_empty_balance_sheet_totals_are_zero(self):
        bs = BalanceSheet(as_of_date=date(2024, 1, 1))
        assert bs.total_assets == 0.0
        assert bs.total_liabilities == 0.0
        assert bs.total_equity == 0.0
        assert bs.total_liabilities_and_equity == 0.0

    def test_check_balance_balanced(self):
        bs = _sample_balance_sheet()
        is_balanced, delta = bs.check_balance()
        assert is_balanced is True
        assert delta == pytest.approx(0.0)

    def test_check_balance_imbalanced(self):
        bs = BalanceSheet(as_of_date=date(2024, 1, 1))
        bs.assets = [BalanceSheetLine("a1", "Assets", "BANK", 100.0)]
        bs.liabilities = [BalanceSheetLine("l1", "Liabilities", "LIABILITY", 60.0)]
        bs.equity = [BalanceSheetLine("e1", "Equity", "EQUITY", 30.0)]
        # Assets(100) - L+E(90) = 10
        is_balanced, delta = bs.check_balance()
        assert is_balanced is False
        assert delta == pytest.approx(10.0)

    def test_check_balance_custom_tolerance(self):
        bs = BalanceSheet(as_of_date=date(2024, 1, 1))
        bs.assets = [BalanceSheetLine("a1", "Assets", "BANK", 100.0)]
        bs.equity = [BalanceSheetLine("e1", "Equity", "EQUITY", 99.98)]
        # Delta = 0.02 — within 0.05 tolerance
        is_balanced, _ = bs.check_balance(tolerance=0.05)
        assert is_balanced is True
        # Outside 0.01 tolerance
        is_balanced2, _ = bs.check_balance(tolerance=0.01)
        assert is_balanced2 is False

    def test_default_entity_label_is_consolidated(self):
        bs = BalanceSheet(as_of_date=date(2024, 1, 1))
        assert bs.entity_label == "Consolidated"
        assert bs.entity_key is None


# ---------------------------------------------------------------------------
# Format functions
# ---------------------------------------------------------------------------


@pytest.fixture
def formatted_balance_sheet() -> BalanceSheet:
    bs = BalanceSheet(
        as_of_date=date(2024, 12, 31),
        entity_label="Test Corp",
        currency="USD",
    )
    bs.assets = [BalanceSheetLine("a1", "Assets:Checking", "BANK", 1000.0)]
    bs.liabilities = [BalanceSheetLine("l1", "Liabilities:Card", "LIABILITY", 200.0)]
    bs.equity = [BalanceSheetLine("e1", "Equity:Opening", "EQUITY", 800.0)]
    return bs


class TestFormatAsText:
    def test_contains_balance_sheet_header(self, formatted_balance_sheet):
        text = format_as_text(formatted_balance_sheet)
        assert "BALANCE SHEET" in text

    def test_contains_entity_label(self, formatted_balance_sheet):
        text = format_as_text(formatted_balance_sheet)
        assert "Test Corp" in text

    def test_contains_section_headers(self, formatted_balance_sheet):
        text = format_as_text(formatted_balance_sheet)
        assert "ASSETS" in text
        assert "LIABILITIES" in text
        assert "EQUITY" in text

    def test_contains_totals(self, formatted_balance_sheet):
        text = format_as_text(formatted_balance_sheet)
        assert "TOTAL ASSETS" in text
        assert "TOTAL LIABILITIES" in text
        assert "TOTAL EQUITY" in text

    def test_contains_balance_amount(self, formatted_balance_sheet):
        text = format_as_text(formatted_balance_sheet)
        assert "1,000.00" in text

    def test_balanced_sheet_shows_verification(self, formatted_balance_sheet):
        text = format_as_text(formatted_balance_sheet)
        assert "ACCOUNTING EQUATION VERIFIED" in text

    def test_imbalanced_sheet_shows_warning(self):
        bs = BalanceSheet(as_of_date=date(2024, 1, 1))
        bs.assets = [BalanceSheetLine("a1", "Assets", "BANK", 200.0)]
        bs.equity = [BalanceSheetLine("e1", "Equity", "EQUITY", 100.0)]
        text = format_as_text(bs)
        assert "WARNING" in text or "Imbalance" in text


class TestFormatAsCsv:
    def test_contains_section_labels(self, formatted_balance_sheet):
        csv_text = format_as_csv(formatted_balance_sheet)
        assert "ASSETS" in csv_text
        assert "LIABILITIES" in csv_text
        assert "EQUITY" in csv_text

    def test_contains_column_headers(self, formatted_balance_sheet):
        csv_text = format_as_csv(formatted_balance_sheet)
        assert "Section" in csv_text
        assert "Account" in csv_text
        assert "Balance" in csv_text

    def test_contains_entity_label(self, formatted_balance_sheet):
        csv_text = format_as_csv(formatted_balance_sheet)
        assert "Test Corp" in csv_text

    def test_contains_total_rows(self, formatted_balance_sheet):
        csv_text = format_as_csv(formatted_balance_sheet)
        assert "TOTAL ASSETS" in csv_text
        assert "TOTAL LIABILITIES" in csv_text
        assert "TOTAL EQUITY" in csv_text


class TestFormatAsJson:
    def test_returns_valid_json(self, formatted_balance_sheet):
        json_str = format_as_json(formatted_balance_sheet)
        data = json.loads(json_str)
        assert isinstance(data, dict)

    def test_top_level_key(self, formatted_balance_sheet):
        data = json.loads(format_as_json(formatted_balance_sheet))
        assert "balance_sheet" in data

    def test_sections_present(self, formatted_balance_sheet):
        data = json.loads(format_as_json(formatted_balance_sheet))
        bs = data["balance_sheet"]
        assert "assets" in bs
        assert "liabilities" in bs
        assert "equity" in bs

    def test_summary_present(self, formatted_balance_sheet):
        data = json.loads(format_as_json(formatted_balance_sheet))
        summary = data["balance_sheet"]["summary"]
        assert "total_assets" in summary
        assert "total_liabilities" in summary
        assert "total_equity" in summary
        assert "total_liabilities_and_equity" in summary
        assert "accounting_equation_balanced" in summary

    def test_summary_values_correct(self, formatted_balance_sheet):
        data = json.loads(format_as_json(formatted_balance_sheet))
        summary = data["balance_sheet"]["summary"]
        assert summary["total_assets"] == pytest.approx(1000.0)
        assert summary["total_liabilities"] == pytest.approx(200.0)
        assert summary["total_equity"] == pytest.approx(800.0)
        assert summary["accounting_equation_balanced"] is True

    def test_entity_and_date_fields(self, formatted_balance_sheet):
        data = json.loads(format_as_json(formatted_balance_sheet))
        bs = data["balance_sheet"]
        assert bs["entity"] == "Test Corp"
        assert bs["as_of_date"] == "2024-12-31"
        assert bs["currency"] == "USD"


# ---------------------------------------------------------------------------
# generate_balance_sheet
# ---------------------------------------------------------------------------


def _make_book_and_map_for_generate():
    """
    Returns (book, entity_map) for a simple balanced scenario:

        GnuCash balances (raw, sign-convention values):
            acc-asset   = +120   BANK    → ASSET    display = +120
            acc-equity  = -100   EQUITY  → EQUITY   display = +100  (negated)
            acc-income  = -30    INCOME  → not on balance sheet
            acc-expense = +10    EXPENSE → not on balance sheet

        Retained Earnings = -(income + expense) = -(-30 + 10) = 20
        Total Equity      = 100 + 20 = 120
        Total Assets      = 120  ✓ balanced
    """
    accounts = [
        make_account("acc-asset", "Assets:Checking", "BANK"),
        make_account("acc-equity", "Equity:Opening Balance", "EQUITY"),
        make_account("acc-income", "Income:Salary", "INCOME"),
        make_account("acc-expense", "Expenses:Food", "EXPENSE"),
    ]
    balances = {
        "acc-asset": 120.0,
        "acc-equity": -100.0,
        "acc-income": -30.0,
        "acc-expense": 10.0,
    }
    book = MockBook(accounts=accounts, balances=balances)

    entities = {
        "personal": EntityDefinition("personal", "Personal", "individual"),
        "unassigned": EntityDefinition("unassigned", "Unassigned", "individual"),
    }
    account_entities = {
        "acc-asset": "personal",
        "acc-equity": "personal",
        "acc-income": "personal",
        "acc-expense": "personal",
    }
    em = EntityMap(entities=entities, account_entities=account_entities)
    return book, em


MOCK_VALIDATE = "gcgaap.reports.balance_sheet.validate_for_reporting"


class TestGenerateBalanceSheet:
    def test_returns_balance_sheet_instance(self):
        book, em = _make_book_and_map_for_generate()
        with patch(MOCK_VALIDATE):
            bs = generate_balance_sheet(book, em, "2024-12-31")
        assert isinstance(bs, BalanceSheet)

    def test_balance_sheet_date(self):
        book, em = _make_book_and_map_for_generate()
        with patch(MOCK_VALIDATE):
            bs = generate_balance_sheet(book, em, "2024-12-31")
        assert bs.as_of_date == date(2024, 12, 31)

    def test_total_assets_correct(self):
        book, em = _make_book_and_map_for_generate()
        with patch(MOCK_VALIDATE):
            bs = generate_balance_sheet(book, em, "2024-12-31")
        assert bs.total_assets == pytest.approx(120.0)

    def test_equity_account_negated_for_display(self):
        """Equity accounts stored as -100 in GnuCash should display as +100."""
        book, em = _make_book_and_map_for_generate()
        with patch(MOCK_VALIDATE):
            bs = generate_balance_sheet(book, em, "2024-12-31")

        opening_lines = [l for l in bs.equity if "Opening Balance" in l.account_name]
        assert len(opening_lines) == 1
        assert opening_lines[0].balance == pytest.approx(100.0)

    def test_retained_earnings_added_to_equity(self):
        """Retained Earnings synthetic line calculated from income/expense."""
        book, em = _make_book_and_map_for_generate()
        with patch(MOCK_VALIDATE):
            bs = generate_balance_sheet(book, em, "2024-12-31")

        retained_lines = [l for l in bs.equity if "Retained Earnings" in l.account_name]
        assert len(retained_lines) == 1
        # -(income + expense) = -(-30 + 10) = 20
        assert retained_lines[0].balance == pytest.approx(20.0)

    def test_income_expense_accounts_absent_from_balance_sheet(self):
        """INCOME and EXPENSE accounts do not appear as line items."""
        book, em = _make_book_and_map_for_generate()
        with patch(MOCK_VALIDATE):
            bs = generate_balance_sheet(book, em, "2024-12-31")

        all_names = [l.account_name for l in bs.assets + bs.liabilities + bs.equity]
        assert "Income:Salary" not in all_names
        assert "Expenses:Food" not in all_names

    def test_accounting_equation_holds(self):
        book, em = _make_book_and_map_for_generate()
        with patch(MOCK_VALIDATE):
            bs = generate_balance_sheet(book, em, "2024-12-31")

        is_balanced, delta = bs.check_balance()
        assert is_balanced is True
        assert delta == pytest.approx(0.0)

    def test_entity_specific_report_sets_entity_fields(self):
        book, em = _make_book_and_map_for_generate()
        with patch(MOCK_VALIDATE):
            bs = generate_balance_sheet(book, em, "2024-12-31", entity_key="personal")

        assert bs.entity_key == "personal"
        assert bs.entity_label == "Personal"

    def test_consolidated_report_entity_key_is_none(self):
        book, em = _make_book_and_map_for_generate()
        with patch(MOCK_VALIDATE):
            bs = generate_balance_sheet(book, em, "2024-12-31", entity_key=None)

        assert bs.entity_key is None
        assert bs.entity_label == "Consolidated"

    def test_validation_failure_propagates(self):
        book, em = _make_book_and_map_for_generate()
        with patch(MOCK_VALIDATE, side_effect=RuntimeError("Strict validation FAILED")):
            with pytest.raises(RuntimeError, match="Strict validation FAILED"):
                generate_balance_sheet(book, em, "2024-12-31")

    def test_unbalanced_book_raises_value_error(self):
        """
        If accounting equation fails even after computing retained earnings,
        generate_balance_sheet raises ValueError.
        """
        # Asset = 200, Equity = -100 (display 100); no income/expense
        # Assets(200) != L+E(100) → should raise
        accounts = [
            make_account("acc-asset", "Assets:Checking", "BANK"),
            make_account("acc-equity", "Equity:Opening", "EQUITY"),
        ]
        balances = {"acc-asset": 200.0, "acc-equity": -100.0}
        book = MockBook(accounts=accounts, balances=balances)
        em = EntityMap(account_entities={"acc-asset": "personal", "acc-equity": "personal"})

        with patch(MOCK_VALIDATE):
            with pytest.raises(ValueError, match="ACCOUNTING EQUATION VIOLATION"):
                generate_balance_sheet(book, em, "2024-12-31")

    def test_with_liability_account(self):
        """Liability accounts stored as negative display as positive."""
        accounts = [
            make_account("acc-asset", "Assets:Checking", "BANK"),
            make_account("acc-liab", "Liabilities:Card", "LIABILITY"),
            make_account("acc-equity", "Equity:Opening", "EQUITY"),
        ]
        # Asset=200, Liability=-80 (display 80), Equity=-120 (display 120)
        # A(200) = L(80) + E(120) ✓
        balances = {
            "acc-asset": 200.0,
            "acc-liab": -80.0,
            "acc-equity": -120.0,
        }
        book = MockBook(accounts=accounts, balances=balances)
        em = EntityMap(account_entities={
            "acc-asset": "personal",
            "acc-liab": "personal",
            "acc-equity": "personal",
        })

        with patch(MOCK_VALIDATE):
            bs = generate_balance_sheet(book, em, "2024-12-31")

        assert bs.total_assets == pytest.approx(200.0)
        assert bs.total_liabilities == pytest.approx(80.0)
        assert bs.total_equity == pytest.approx(120.0)
        is_balanced, _ = bs.check_balance()
        assert is_balanced is True


# ---------------------------------------------------------------------------
# BalanceCheckResult
# ---------------------------------------------------------------------------


class TestBalanceCheckResult:
    def test_creation(self):
        result = BalanceCheckResult(
            entity_key="personal",
            entity_label="Personal",
            balanced=True,
            total_assets=1000.0,
            total_liabilities=200.0,
            total_equity=800.0,
        )
        assert result.entity_key == "personal"
        assert result.balanced is True
        assert result.error is None

    def test_unbalanced_result(self):
        result = BalanceCheckResult(
            entity_key=None,
            entity_label="Consolidated",
            balanced=False,
            imbalance=50.0,
        )
        assert result.balanced is False
        assert result.imbalance == 50.0

    def test_error_result(self):
        result = BalanceCheckResult(
            entity_key="biz",
            entity_label="Business",
            balanced=False,
            error="Something went wrong",
        )
        assert result.error == "Something went wrong"


# ---------------------------------------------------------------------------
# check_entity_balance
# ---------------------------------------------------------------------------


MOCK_GEN = "gcgaap.reports.balance_sheet.generate_balance_sheet"


class TestCheckEntityBalance:
    def _make_balanced_setup(self):
        accounts = [
            make_account("acc-asset", "Assets:Checking", "BANK"),
            make_account("acc-equity", "Equity:Opening", "EQUITY"),
        ]
        balances = {"acc-asset": 100.0, "acc-equity": -100.0}
        book = MockBook(accounts=accounts, balances=balances)
        em = EntityMap(account_entities={"acc-asset": "personal", "acc-equity": "personal"})
        config = GCGAAPConfig()
        return book, em, config

    def test_returns_balanced_result_on_success(self):
        book, em, config = self._make_balanced_setup()

        with patch(MOCK_VALIDATE):
            result = check_entity_balance(book, em, "2024-12-31", None, config)

        assert result.balanced is True
        assert result.error is None

    def test_consolidated_label_for_none_entity_key(self):
        book, em, config = self._make_balanced_setup()

        with patch(MOCK_VALIDATE):
            result = check_entity_balance(book, em, "2024-12-31", None, config)

        assert result.entity_label == "Consolidated (All Entities)"
        assert result.entity_key is None

    def test_parses_imbalance_from_value_error(self):
        """check_entity_balance extracts numeric values from a ValueError message."""
        book, em, config = self._make_balanced_setup()
        error_msg = (
            "ACCOUNTING EQUATION VIOLATION: Balance Sheet does not balance!\n"
            "Assets: 200.00\n"
            "Liabilities: 50.00\n"
            "Equity: 100.00\n"
            "Imbalance (A - L - E): 50.00\n"
            "This indicates a serious data integrity issue."
        )

        with patch(MOCK_GEN, side_effect=ValueError(error_msg)):
            result = check_entity_balance(book, em, "2024-12-31", None, config)

        assert result.balanced is False
        assert result.total_assets == pytest.approx(200.0)
        assert result.total_liabilities == pytest.approx(50.0)
        assert result.total_equity == pytest.approx(100.0)
        assert result.imbalance == pytest.approx(50.0)

    def test_stores_generic_value_error_as_error_field(self):
        """ValueError without imbalance format is stored in result.error."""
        book, em, config = self._make_balanced_setup()

        with patch(MOCK_GEN, side_effect=ValueError("Unexpected failure")):
            result = check_entity_balance(book, em, "2024-12-31", None, config)

        assert result.balanced is False
        assert result.error == "Unexpected failure"

    def test_uses_entity_label_from_entity_map(self):
        accounts = [
            make_account("acc-asset", "Assets:Checking", "BANK"),
            make_account("acc-equity", "Equity:Opening", "EQUITY"),
        ]
        balances = {"acc-asset": 100.0, "acc-equity": -100.0}
        book = MockBook(accounts=accounts, balances=balances)
        entities = {
            "personal": EntityDefinition("personal", "My Personal", "individual"),
            "unassigned": EntityDefinition("unassigned", "Unassigned", "individual"),
        }
        em = EntityMap(
            entities=entities,
            account_entities={"acc-asset": "personal", "acc-equity": "personal"},
        )
        config = GCGAAPConfig()

        with patch(MOCK_VALIDATE):
            result = check_entity_balance(book, em, "2024-12-31", "personal", config)

        assert result.entity_label == "My Personal"
