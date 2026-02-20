"""
Shared pytest fixtures for GCGAAP tests.
"""

import pytest

from gcgaap.config import GCGAAPConfig
from gcgaap.entity_map import EntityDefinition, EntityMap
from tests.helpers import MockBook, make_account, make_split, make_transaction


@pytest.fixture
def sample_config() -> GCGAAPConfig:
    """Default GCGAAP configuration."""
    return GCGAAPConfig(numeric_tolerance=0.01)


@pytest.fixture
def simple_entity_map() -> EntityMap:
    """
    EntityMap with personal and business entities.

    Explicit account-to-entity mappings:
        acc-asset, acc-liab, acc-equity, acc-income, acc-expense → personal
        acc-biz                                                   → business
    """
    entities = {
        "personal": EntityDefinition(key="personal", label="Personal", type="individual"),
        "business": EntityDefinition(key="business", label="Business LLC", type="business"),
        "unassigned": EntityDefinition(key="unassigned", label="Unassigned", type="individual"),
    }
    account_entities = {
        "acc-asset": "personal",
        "acc-liab": "personal",
        "acc-equity": "personal",
        "acc-income": "personal",
        "acc-expense": "personal",
        "acc-biz": "business",
    }
    return EntityMap(entities=entities, account_entities=account_entities)


@pytest.fixture
def balanced_book_accounts() -> list:
    """
    Accounts for a simple balanced test book.

    GnuCash sign conventions:
        BANK    balances are positive  (debit-normal)
        EQUITY  balances are negative  (credit-normal)
        INCOME  balances are negative  (credit-normal)
        EXPENSE balances are positive  (debit-normal)
    """
    return [
        make_account("acc-asset", "Assets:Checking", "BANK"),
        make_account("acc-equity", "Equity:Opening Balance", "EQUITY"),
        make_account("acc-income", "Income:Salary", "INCOME"),
        make_account("acc-expense", "Expenses:Food", "EXPENSE"),
    ]


@pytest.fixture
def balanced_book_balances() -> dict:
    """
    Account balances that satisfy Assets = Liabilities + Equity:

        Opening entry : asset +100, equity -100        (Σ = 0)
        Paycheck      : asset +30,  income -30         (Σ = 0)
        Groceries     : asset -10,  expense +10        (Σ = 0)

        Final balances:
            acc-asset   = +120   → display = 120   (ASSET)
            acc-equity  = -100   → display = 100   (EQUITY, negated)
            acc-income  = -30    → retained earnings
            acc-expense = +10    → retained earnings

        Retained Earnings = -(income + expense) = -(-30 + 10) = 20
        Total Equity      = 100 + 20 = 120
        Total Assets      = 120  ✓
    """
    return {
        "acc-asset": 120.0,
        "acc-equity": -100.0,
        "acc-income": -30.0,
        "acc-expense": 10.0,
    }


@pytest.fixture
def balanced_mock_book(balanced_book_accounts, balanced_book_balances) -> MockBook:
    """MockBook pre-loaded with a balanced set of accounts and balances."""
    return MockBook(
        accounts=balanced_book_accounts,
        balances=balanced_book_balances,
    )


@pytest.fixture
def fully_mapped_entity_map(balanced_book_accounts) -> EntityMap:
    """EntityMap that maps every account in *balanced_book_accounts* to 'personal'."""
    entities = {
        "personal": EntityDefinition(key="personal", label="Personal", type="individual"),
        "unassigned": EntityDefinition(key="unassigned", label="Unassigned", type="individual"),
    }
    account_entities = {acc.guid: "personal" for acc in balanced_book_accounts}
    return EntityMap(entities=entities, account_entities=account_entities)
