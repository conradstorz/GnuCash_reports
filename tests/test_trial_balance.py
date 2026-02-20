"""Tests for gcgaap.reports.trial_balance."""

import json
from datetime import date
from unittest.mock import patch

import pytest

from gcgaap.config import GCGAAPConfig
from gcgaap.entity_map import EntityDefinition, EntityMap
from gcgaap.reports.trial_balance import (
    TrialBalance,
    TrialBalanceLine,
    _assign_debit_credit,
    format_as_csv,
    format_as_json,
    format_as_text,
    generate_trial_balance,
)
from tests.helpers import MockBook, make_account, make_split, make_transaction


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def config() -> GCGAAPConfig:
    return GCGAAPConfig(numeric_tolerance=0.01)


def _fully_mapped_entity_map(accounts) -> EntityMap:
    entities = {
        "personal": EntityDefinition(key="personal", label="Personal", type="individual"),
        "unassigned": EntityDefinition(key="unassigned", label="Unassigned", type="individual"),
    }
    account_entities = {a.guid: "personal" for a in accounts}
    return EntityMap(entities=entities, account_entities=account_entities)


def _multi_entity_map(accounts) -> EntityMap:
    entities = {
        "personal": EntityDefinition(key="personal", label="Personal", type="individual"),
        "biz": EntityDefinition(key="biz", label="Biz LLC", type="business"),
        "unassigned": EntityDefinition(key="unassigned", label="Unassigned", type="individual"),
    }
    account_entities = {
        "asset-checking": "personal",
        "equity-ob": "personal",
        "inc-salary": "personal",
        "exp-food": "personal",
        "biz-asset": "biz",
        "biz-income": "biz",
    }
    return EntityMap(entities=entities, account_entities=account_entities)


def _make_standard_accounts():
    return [
        make_account("asset-checking", "Assets:Checking", "BANK"),
        make_account("equity-ob", "Equity:Opening Balance", "EQUITY"),
        make_account("inc-salary", "Income:Salary", "INCOME"),
        make_account("exp-food", "Expenses:Food", "EXPENSE"),
    ]


def _make_standard_balances():
    """
    Opening entry:  asset +100, equity -100
    Paycheck:       asset +50,  income -50
    Groceries:      asset -20,  expense +20

    Final balances:
        asset-checking: +130  → debit  130
        equity-ob:      -100  → credit 100
        inc-salary:     -50   → credit  50
        exp-food:       +20   → debit   20
    Total debits  = 150  (130 + 20)
    Total credits = 150  (100 + 50)
    """
    return {
        "asset-checking": 130.0,
        "equity-ob": -100.0,
        "inc-salary": -50.0,
        "exp-food": 20.0,
    }


# ---------------------------------------------------------------------------
# _assign_debit_credit
# ---------------------------------------------------------------------------


class TestAssignDebitCredit:
    def test_asset_positive_balance_is_debit(self):
        debit, credit = _assign_debit_credit(100.0, "ASSET")
        assert debit == 100.0
        assert credit == 0.0

    def test_asset_negative_balance_is_credit(self):
        debit, credit = _assign_debit_credit(-50.0, "ASSET")
        assert debit == 0.0
        assert credit == 50.0

    def test_expense_positive_balance_is_debit(self):
        debit, credit = _assign_debit_credit(200.0, "EXPENSE")
        assert debit == 200.0
        assert credit == 0.0

    def test_liability_negative_balance_is_credit(self):
        debit, credit = _assign_debit_credit(-75.0, "LIABILITY")
        assert debit == 0.0
        assert credit == 75.0

    def test_liability_positive_balance_is_debit(self):
        # Abnormal (contra) balance
        debit, credit = _assign_debit_credit(25.0, "LIABILITY")
        assert debit == 25.0
        assert credit == 0.0

    def test_equity_negative_balance_is_credit(self):
        debit, credit = _assign_debit_credit(-1000.0, "EQUITY")
        assert debit == 0.0
        assert credit == 1000.0

    def test_income_negative_balance_is_credit(self):
        debit, credit = _assign_debit_credit(-300.0, "INCOME")
        assert debit == 0.0
        assert credit == 300.0

    def test_income_positive_balance_is_debit(self):
        # Abnormal balance (net expense in income account)
        debit, credit = _assign_debit_credit(50.0, "INCOME")
        assert debit == 50.0
        assert credit == 0.0

    def test_zero_asset_produces_zeros(self):
        debit, credit = _assign_debit_credit(0.0, "ASSET")
        assert debit == 0.0
        assert credit == 0.0


# ---------------------------------------------------------------------------
# TrialBalance properties
# ---------------------------------------------------------------------------


class TestTrialBalanceProperties:
    def _make_tb(self, lines=None):
        return TrialBalance(
            as_of_date=date(2024, 12, 31),
            entity_key=None,
            entity_label="Consolidated",
            lines=lines or [],
        )

    def test_total_debits(self):
        lines = [
            TrialBalanceLine("a", "A", "BANK", "ASSET", 100.0, 0.0),
            TrialBalanceLine("b", "B", "EXPENSE", "EXPENSE", 50.0, 0.0),
        ]
        tb = self._make_tb(lines)
        assert tb.total_debits == 150.0

    def test_total_credits(self):
        lines = [
            TrialBalanceLine("a", "A", "EQUITY", "EQUITY", 0.0, 100.0),
            TrialBalanceLine("b", "B", "INCOME", "INCOME", 0.0, 50.0),
        ]
        tb = self._make_tb(lines)
        assert tb.total_credits == 150.0

    def test_is_balanced_when_equal(self):
        lines = [
            TrialBalanceLine("a", "A", "BANK", "ASSET", 100.0, 0.0),
            TrialBalanceLine("b", "B", "EQUITY", "EQUITY", 0.0, 100.0),
        ]
        tb = self._make_tb(lines)
        assert tb.is_balanced()

    def test_not_balanced_when_unequal(self):
        lines = [
            TrialBalanceLine("a", "A", "BANK", "ASSET", 100.0, 0.0),
            TrialBalanceLine("b", "B", "EQUITY", "EQUITY", 0.0, 50.0),
        ]
        tb = self._make_tb(lines)
        assert not tb.is_balanced()

    def test_imbalance_value(self):
        lines = [
            TrialBalanceLine("a", "A", "BANK", "ASSET", 100.0, 0.0),
            TrialBalanceLine("b", "B", "EQUITY", "EQUITY", 0.0, 60.0),
        ]
        tb = self._make_tb(lines)
        assert abs(tb.imbalance() - 40.0) < 0.001

    def test_empty_trial_balance_is_balanced(self):
        tb = self._make_tb([])
        assert tb.is_balanced()


# ---------------------------------------------------------------------------
# generate_trial_balance
# ---------------------------------------------------------------------------


class TestGenerateTrialBalance:
    def test_basic_balanced_books(self, config):
        accounts = _make_standard_accounts()
        balances = _make_standard_balances()
        book = MockBook(accounts=accounts, balances=balances)
        entity_map = _fully_mapped_entity_map(accounts)

        with patch("gcgaap.reports.trial_balance.validate_for_reporting"):
            tb = generate_trial_balance(book, entity_map, "2024-12-31",
                                        entity_key=None, config=config)

        assert tb.is_balanced()
        assert abs(tb.total_debits - 150.0) < 0.01
        assert abs(tb.total_credits - 150.0) < 0.01

    def test_asset_account_in_debit_column(self, config):
        accounts = _make_standard_accounts()
        balances = _make_standard_balances()
        book = MockBook(accounts=accounts, balances=balances)
        entity_map = _fully_mapped_entity_map(accounts)

        with patch("gcgaap.reports.trial_balance.validate_for_reporting"):
            tb = generate_trial_balance(book, entity_map, "2024-12-31",
                                        entity_key=None, config=config)

        asset_line = next(l for l in tb.lines if l.account_guid == "asset-checking")
        assert asset_line.debit == 130.0
        assert asset_line.credit == 0.0

    def test_equity_account_in_credit_column(self, config):
        accounts = _make_standard_accounts()
        balances = _make_standard_balances()
        book = MockBook(accounts=accounts, balances=balances)
        entity_map = _fully_mapped_entity_map(accounts)

        with patch("gcgaap.reports.trial_balance.validate_for_reporting"):
            tb = generate_trial_balance(book, entity_map, "2024-12-31",
                                        entity_key=None, config=config)

        equity_line = next(l for l in tb.lines if l.account_guid == "equity-ob")
        assert equity_line.credit == 100.0
        assert equity_line.debit == 0.0

    def test_income_account_in_credit_column(self, config):
        accounts = _make_standard_accounts()
        balances = _make_standard_balances()
        book = MockBook(accounts=accounts, balances=balances)
        entity_map = _fully_mapped_entity_map(accounts)

        with patch("gcgaap.reports.trial_balance.validate_for_reporting"):
            tb = generate_trial_balance(book, entity_map, "2024-12-31",
                                        entity_key=None, config=config)

        income_line = next(l for l in tb.lines if l.account_guid == "inc-salary")
        assert income_line.credit == 50.0
        assert income_line.debit == 0.0

    def test_expense_account_in_debit_column(self, config):
        accounts = _make_standard_accounts()
        balances = _make_standard_balances()
        book = MockBook(accounts=accounts, balances=balances)
        entity_map = _fully_mapped_entity_map(accounts)

        with patch("gcgaap.reports.trial_balance.validate_for_reporting"):
            tb = generate_trial_balance(book, entity_map, "2024-12-31",
                                        entity_key=None, config=config)

        exp_line = next(l for l in tb.lines if l.account_guid == "exp-food")
        assert exp_line.debit == 20.0
        assert exp_line.credit == 0.0

    def test_zero_balance_accounts_excluded(self, config):
        accounts = _make_standard_accounts()
        balances = {
            "asset-checking": 100.0,
            "equity-ob": -100.0,
            "inc-salary": 0.0,   # zero — should be excluded
            "exp-food": 0.0,     # zero — should be excluded
        }
        book = MockBook(accounts=accounts, balances=balances)
        entity_map = _fully_mapped_entity_map(accounts)

        with patch("gcgaap.reports.trial_balance.validate_for_reporting"):
            tb = generate_trial_balance(book, entity_map, "2024-12-31",
                                        entity_key=None, config=config)

        guids_in_tb = {l.account_guid for l in tb.lines}
        assert "inc-salary" not in guids_in_tb
        assert "exp-food" not in guids_in_tb

    def test_entity_filter_personal(self, config):
        accounts = [
            make_account("asset-checking", "Assets:Checking", "BANK"),
            make_account("equity-ob", "Equity:Opening Balance", "EQUITY"),
            make_account("inc-salary", "Income:Salary", "INCOME"),
            make_account("exp-food", "Expenses:Food", "EXPENSE"),
            make_account("biz-asset", "Business:Asset", "ASSET"),
            make_account("biz-income", "Business:Income", "INCOME"),
        ]
        balances = {
            "asset-checking": 130.0,
            "equity-ob": -100.0,
            "inc-salary": -50.0,
            "exp-food": 20.0,
            "biz-asset": 500.0,
            "biz-income": -500.0,
        }
        book = MockBook(accounts=accounts, balances=balances)
        entity_map = _multi_entity_map(accounts)

        with patch("gcgaap.reports.trial_balance.validate_for_reporting"):
            tb = generate_trial_balance(book, entity_map, "2024-12-31",
                                        entity_key="personal", config=config)

        guids_in_tb = {l.account_guid for l in tb.lines}
        assert "biz-asset" not in guids_in_tb
        assert "biz-income" not in guids_in_tb
        assert "asset-checking" in guids_in_tb

    def test_accounts_sorted_by_name(self, config):
        accounts = _make_standard_accounts()
        balances = _make_standard_balances()
        book = MockBook(accounts=accounts, balances=balances)
        entity_map = _fully_mapped_entity_map(accounts)

        with patch("gcgaap.reports.trial_balance.validate_for_reporting"):
            tb = generate_trial_balance(book, entity_map, "2024-12-31",
                                        entity_key=None, config=config)

        names = [l.account_name for l in tb.lines]
        assert names == sorted(names)

    def test_entity_label_consolidated_when_no_entity(self, config):
        accounts = _make_standard_accounts()
        balances = _make_standard_balances()
        book = MockBook(accounts=accounts, balances=balances)
        entity_map = _fully_mapped_entity_map(accounts)

        with patch("gcgaap.reports.trial_balance.validate_for_reporting"):
            tb = generate_trial_balance(book, entity_map, "2024-12-31",
                                        entity_key=None, config=config)

        assert tb.entity_label == "Consolidated"

    def test_entity_label_from_entity_map(self, config):
        accounts = [
            make_account("asset-checking", "Assets:Checking", "BANK"),
            make_account("equity-ob", "Equity:Opening Balance", "EQUITY"),
        ]
        balances = {"asset-checking": 100.0, "equity-ob": -100.0}
        book = MockBook(accounts=accounts, balances=balances)
        entities = {
            "alice": EntityDefinition(key="alice", label="Alice Smith", type="individual"),
            "unassigned": EntityDefinition(key="unassigned", label="Unassigned", type="individual"),
        }
        entity_map = EntityMap(
            entities=entities,
            account_entities={"asset-checking": "alice", "equity-ob": "alice"},
        )

        with patch("gcgaap.reports.trial_balance.validate_for_reporting"):
            tb = generate_trial_balance(book, entity_map, "2024-12-31",
                                        entity_key="alice", config=config)

        assert tb.entity_label == "Alice Smith"


# ---------------------------------------------------------------------------
# format_as_text
# ---------------------------------------------------------------------------


class TestFormatAsText:
    def _make_tb(self):
        lines = [
            TrialBalanceLine("a", "Assets:Checking", "BANK", "ASSET", 130.0, 0.0, level=1),
            TrialBalanceLine("b", "Equity:Opening Balance", "EQUITY", "EQUITY", 0.0, 100.0, level=1),
            TrialBalanceLine("c", "Income:Salary", "INCOME", "INCOME", 0.0, 50.0, level=1),
            TrialBalanceLine("d", "Expenses:Food", "EXPENSE", "EXPENSE", 20.0, 0.0, level=1),
        ]
        return TrialBalance(
            as_of_date=date(2024, 12, 31),
            entity_key=None,
            entity_label="Consolidated",
            lines=lines,
        )

    def test_contains_trial_balance_header(self):
        text = format_as_text(self._make_tb())
        assert "TRIAL BALANCE" in text

    def test_contains_totals_row(self):
        text = format_as_text(self._make_tb())
        assert "TOTALS" in text

    def test_balanced_shows_ok(self):
        text = format_as_text(self._make_tb())
        assert "[OK]" in text

    def test_imbalanced_shows_warning(self):
        lines = [
            TrialBalanceLine("a", "Assets:Checking", "BANK", "ASSET", 200.0, 0.0),
            TrialBalanceLine("b", "Equity:Opening Balance", "EQUITY", "EQUITY", 0.0, 100.0),
        ]
        tb = TrialBalance(
            as_of_date=date(2024, 12, 31),
            entity_key=None,
            entity_label="Consolidated",
            lines=lines,
        )
        text = format_as_text(tb)
        assert "[X]" in text or "IMBALANCE" in text

    def test_account_names_appear(self):
        text = format_as_text(self._make_tb())
        assert "Assets:Checking" in text
        assert "Income:Salary" in text

    def test_date_in_output(self):
        text = format_as_text(self._make_tb())
        assert "2024" in text


# ---------------------------------------------------------------------------
# format_as_csv
# ---------------------------------------------------------------------------


class TestFormatAsCsv:
    def _make_tb(self):
        return TrialBalance(
            as_of_date=date(2024, 12, 31),
            entity_key=None,
            entity_label="Consolidated",
            lines=[
                TrialBalanceLine("a", "Assets:Checking", "BANK", "ASSET", 100.0, 0.0),
                TrialBalanceLine("b", "Equity:Opening Balance", "EQUITY", "EQUITY", 0.0, 100.0),
            ],
        )

    def test_csv_has_column_headers(self):
        csv_text = format_as_csv(self._make_tb())
        assert "Account" in csv_text and "Debit" in csv_text and "Credit" in csv_text

    def test_csv_has_totals_row(self):
        csv_text = format_as_csv(self._make_tb())
        assert "TOTALS" in csv_text

    def test_csv_account_appears(self):
        csv_text = format_as_csv(self._make_tb())
        assert "Assets:Checking" in csv_text


# ---------------------------------------------------------------------------
# format_as_json
# ---------------------------------------------------------------------------


class TestFormatAsJson:
    def _make_tb(self):
        return TrialBalance(
            as_of_date=date(2024, 12, 31),
            entity_key="personal",
            entity_label="Personal",
            lines=[
                TrialBalanceLine("a", "Assets:Checking", "BANK", "ASSET", 100.0, 0.0),
                TrialBalanceLine("b", "Equity:Opening Balance", "EQUITY", "EQUITY", 0.0, 100.0),
            ],
        )

    def test_json_is_valid(self):
        result = json.loads(format_as_json(self._make_tb()))
        assert "trial_balance" in result

    def test_json_summary_present(self):
        result = json.loads(format_as_json(self._make_tb()))
        summary = result["trial_balance"]["summary"]
        assert "total_debits" in summary
        assert "total_credits" in summary
        assert "is_balanced" in summary

    def test_json_balanced_flag_true(self):
        result = json.loads(format_as_json(self._make_tb()))
        assert result["trial_balance"]["summary"]["is_balanced"] is True

    def test_json_entity_key(self):
        result = json.loads(format_as_json(self._make_tb()))
        assert result["trial_balance"]["entity_key"] == "personal"

    def test_json_date_formatted(self):
        result = json.loads(format_as_json(self._make_tb()))
        assert result["trial_balance"]["as_of_date"] == "2024-12-31"

    def test_json_accounts_list(self):
        result = json.loads(format_as_json(self._make_tb()))
        accounts = result["trial_balance"]["accounts"]
        assert len(accounts) == 2
        assert "account_name" in accounts[0]
