"""
Shared test helpers for GCGAAP unit tests.

Provides factory functions for creating test data objects and a MockBook
that stands in for GnuCashBook without requiring a real GnuCash file or piecash.
"""

from __future__ import annotations

from gcgaap.gnucash_access import GCAccount, GCTransaction, GCTransactionSplit


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


def make_account(
    guid: str,
    full_name: str,
    account_type: str,
    commodity: str = "USD",
    parent_guid: str | None = None,
    is_placeholder: bool = False,
) -> GCAccount:
    """Create a GCAccount with sensible defaults."""
    return GCAccount(
        guid=guid,
        full_name=full_name,
        type=account_type,
        commodity_symbol=commodity,
        parent_guid=parent_guid,
        is_placeholder=is_placeholder,
    )


def make_split(account_guid: str, value: float, memo: str | None = None) -> GCTransactionSplit:
    """Create a GCTransactionSplit."""
    return GCTransactionSplit(account_guid=account_guid, value=value, memo=memo)


def make_transaction(
    guid: str,
    post_date: str,
    description: str,
    splits: list[GCTransactionSplit],
) -> GCTransaction:
    """Create a GCTransaction."""
    return GCTransaction(
        guid=guid,
        post_date=post_date,
        description=description,
        splits=splits,
    )


# ---------------------------------------------------------------------------
# MockBook
# ---------------------------------------------------------------------------


class MockBook:
    """
    Lightweight stand-in for GnuCashBook used in unit tests.

    Bypasses piecash entirely by accepting pre-built GCAccount and
    GCTransaction objects.  Supports the context-manager protocol so it can
    be used in ``with MockBook(...) as book:`` expressions.
    """

    def __init__(
        self,
        accounts: list[GCAccount] | None = None,
        transactions: list[GCTransaction] | None = None,
        balances: dict[str, float] | None = None,
    ) -> None:
        self._accounts: list[GCAccount] = accounts or []
        self._transactions: list[GCTransaction] = transactions or []
        self._balances: dict[str, float] = balances or {}

    # Context-manager protocol -----------------------------------------------

    def __enter__(self) -> "MockBook":
        return self

    def __exit__(self, *args) -> None:
        pass

    # GnuCashBook interface ---------------------------------------------------

    def iter_accounts(self):
        return iter(self._accounts)

    def iter_transactions(self):
        return iter(self._transactions)

    def get_account_by_guid(self, guid: str) -> GCAccount | None:
        for acc in self._accounts:
            if acc.guid == guid:
                return acc
        return None

    def get_account_balances(
        self,
        as_of_date,
        account_guids: list[str] | None = None,
    ) -> dict[str, float]:
        if account_guids is not None:
            return {g: self._balances.get(g, 0.0) for g in account_guids}
        return dict(self._balances)

    def get_account_balance(self, account_guid: str, as_of_date) -> float:
        return self._balances.get(account_guid, 0.0)

    def get_period_account_balances(
        self,
        from_date,
        to_date,
        account_guids: list[str] | None = None,
    ) -> dict[str, float]:
        from datetime import datetime

        balances: dict[str, float] = {}

        if account_guids is not None:
            for g in account_guids:
                balances[g] = 0.0
        else:
            for acc in self._accounts:
                balances[acc.guid] = 0.0

        for txn in self._transactions:
            txn_date = datetime.strptime(txn.post_date, "%Y-%m-%d").date()
            if txn_date < from_date or txn_date > to_date:
                continue
            for split in txn.splits:
                if account_guids is not None and split.account_guid not in balances:
                    continue
                balances[split.account_guid] = balances.get(split.account_guid, 0.0) + split.value

        return balances
