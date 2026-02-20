"""Tests for gcgaap.validate."""

import json

import pytest

from gcgaap.config import GCGAAPConfig
from gcgaap.entity_map import EntityDefinition, EntityMap
from gcgaap.validate import (
    BalancingAccountStatus,
    ValidationProblem,
    ValidationResult,
    check_cross_entity_balancing_accounts,
    scan_unmapped_accounts,
    validate_accounts,
    validate_book,
    validate_for_reporting,
    validate_transactions,
)
from tests.helpers import MockBook, make_account, make_split, make_transaction


# ---------------------------------------------------------------------------
# ValidationProblem
# ---------------------------------------------------------------------------


class TestValidationProblem:
    def test_error_creation(self):
        p = ValidationProblem("error", "Something failed")
        assert p.severity == "error"
        assert p.message == "Something failed"
        assert p.context is None

    def test_warning_with_context(self):
        p = ValidationProblem("warning", "Watch this", context="GUID: abc123")
        assert p.context == "GUID: abc123"

    def test_invalid_severity_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid severity"):
            ValidationProblem("critical", "wrong level")

    def test_invalid_severity_random_string(self):
        with pytest.raises(ValueError):
            ValidationProblem("info", "not allowed")

    def test_str_error_without_context(self):
        p = ValidationProblem("error", "Something failed")
        s = str(p)
        assert "[ERROR]" in s
        assert "Something failed" in s

    def test_str_warning_with_context(self):
        p = ValidationProblem("warning", "Watch out", context="line 42")
        s = str(p)
        assert "[WARNING]" in s
        assert "Watch out" in s
        assert "Context: line 42" in s

    def test_str_without_context_omits_context_line(self):
        p = ValidationProblem("error", "A problem")
        assert "Context" not in str(p)


# ---------------------------------------------------------------------------
# ValidationResult
# ---------------------------------------------------------------------------


class TestValidationResult:
    def test_empty_result_has_no_problems(self):
        r = ValidationResult()
        assert r.problems == []
        assert r.has_errors is False
        assert r.has_warnings is False
        assert r.error_count == 0
        assert r.warning_count == 0

    def test_add_error_sets_has_errors(self):
        r = ValidationResult()
        r.add_error("An error")
        assert r.has_errors is True
        assert r.error_count == 1
        assert r.has_warnings is False

    def test_add_warning_sets_has_warnings(self):
        r = ValidationResult()
        r.add_warning("A warning")
        assert r.has_warnings is True
        assert r.warning_count == 1
        assert r.has_errors is False

    def test_add_error_with_context(self):
        r = ValidationResult()
        r.add_error("Error msg", context="some context")
        assert r.problems[0].context == "some context"

    def test_multiple_problems_counted_correctly(self):
        r = ValidationResult()
        r.add_error("Error 1")
        r.add_error("Error 2")
        r.add_warning("Warning 1")
        assert r.error_count == 2
        assert r.warning_count == 1

    def test_format_as_text_passed(self):
        r = ValidationResult()
        text = r.format_as_text()
        assert "[PASSED]" in text
        assert "Errors: 0" in text
        assert "Warnings: 0" in text

    def test_format_as_text_failed(self):
        r = ValidationResult()
        r.add_error("Critical issue here")
        text = r.format_as_text()
        assert "[FAILED]" in text
        assert "Errors: 1" in text
        assert "Critical issue here" in text

    def test_format_as_text_passed_with_warnings(self):
        r = ValidationResult()
        r.add_warning("Minor issue")
        text = r.format_as_text()
        assert "PASSED WITH WARNINGS" in text

    def test_format_as_text_strict_mode_header(self):
        r = ValidationResult()
        text = r.format_as_text(strict_mode=True)
        assert "STRICT" in text

    def test_format_as_text_standard_mode_header(self):
        r = ValidationResult()
        text = r.format_as_text(strict_mode=False)
        assert "STANDARD" in text

    def test_format_as_text_includes_error_messages(self):
        r = ValidationResult()
        r.add_error("Error Alpha")
        r.add_error("Error Beta")
        text = r.format_as_text()
        assert "Error Alpha" in text
        assert "Error Beta" in text

    def test_format_as_json_passed(self):
        r = ValidationResult()
        data = json.loads(r.format_as_json())
        assert data["status"] == "passed"
        assert data["error_count"] == 0
        assert data["warning_count"] == 0
        assert data["problems"] == []

    def test_format_as_json_failed_with_errors(self):
        r = ValidationResult()
        r.add_error("An error")
        data = json.loads(r.format_as_json())
        assert data["status"] == "failed"
        assert data["error_count"] == 1
        assert len(data["problems"]) == 1
        assert data["problems"][0]["severity"] == "error"

    def test_format_as_json_warning_status(self):
        r = ValidationResult()
        r.add_warning("A warning")
        data = json.loads(r.format_as_json())
        assert data["status"] == "warning"

    def test_format_as_json_problem_structure(self):
        r = ValidationResult()
        r.add_error("msg", context="ctx")
        data = json.loads(r.format_as_json())
        problem = data["problems"][0]
        assert problem["severity"] == "error"
        assert problem["message"] == "msg"
        assert problem["context"] == "ctx"

    def test_format_as_csv_has_headers(self):
        r = ValidationResult()
        r.add_error("Test error")
        csv_text = r.format_as_csv()
        assert "Severity" in csv_text
        assert "Message" in csv_text
        assert "Context" in csv_text

    def test_format_as_csv_includes_problem_data(self):
        r = ValidationResult()
        r.add_error("Test error", context="ctx")
        r.add_warning("Test warning")
        csv_text = r.format_as_csv()
        assert "error" in csv_text
        assert "Test error" in csv_text
        assert "warning" in csv_text


# ---------------------------------------------------------------------------
# Helper: fully-mapped EntityMap for N accounts
# ---------------------------------------------------------------------------


def _fully_mapped_em(account_guids: list[str]) -> EntityMap:
    entities = {
        "personal": EntityDefinition("personal", "Personal", "individual"),
        "unassigned": EntityDefinition("unassigned", "Unassigned", "individual"),
    }
    return EntityMap(
        entities=entities,
        account_entities={guid: "personal" for guid in account_guids},
    )


# ---------------------------------------------------------------------------
# validate_accounts
# ---------------------------------------------------------------------------


class TestValidateAccounts:
    def test_all_mapped_produces_no_problems(self):
        accounts = [
            make_account("acc-001", "Assets:Checking", "BANK"),
            make_account("acc-002", "Income:Salary", "INCOME"),
        ]
        em = _fully_mapped_em(["acc-001", "acc-002"])
        book = MockBook(accounts=accounts)
        result = ValidationResult()

        validate_accounts(book, em, result, strict_mode=False, quiet=True)

        assert not result.has_errors
        assert not result.has_warnings

    def test_unmapped_account_warning_in_normal_mode(self):
        accounts = [make_account("acc-001", "Assets:Checking", "BANK")]
        em = EntityMap()  # nothing mapped
        book = MockBook(accounts=accounts)
        result = ValidationResult()

        validate_accounts(book, em, result, strict_mode=False, quiet=True)

        assert result.has_warnings
        assert not result.has_errors

    def test_unmapped_account_error_in_strict_mode(self):
        accounts = [make_account("acc-001", "Assets:Checking", "BANK")]
        em = EntityMap()
        book = MockBook(accounts=accounts)
        result = ValidationResult()

        validate_accounts(book, em, result, strict_mode=True, quiet=True)

        assert result.has_errors
        assert result.error_count >= 1

    def test_strict_mode_error_message_mentions_mapping(self):
        accounts = [make_account("acc-001", "Assets:Checking", "BANK")]
        em = EntityMap()
        book = MockBook(accounts=accounts)
        result = ValidationResult()

        validate_accounts(book, em, result, strict_mode=True, quiet=True)

        assert any("mapped" in p.message.lower() for p in result.problems if p.severity == "error")

    def test_imbalance_account_triggers_warning(self):
        accounts = [
            make_account("acc-001", "Assets:Checking", "BANK"),
            make_account("imb-001", "Imbalance-USD", "BANK"),
        ]
        em = _fully_mapped_em(["acc-001", "imb-001"])
        book = MockBook(accounts=accounts)
        result = ValidationResult()

        validate_accounts(book, em, result, strict_mode=False, quiet=True)

        assert result.has_warnings
        assert any("Imbalance" in p.message or "Orphan" in p.message for p in result.problems)

    def test_orphan_account_triggers_warning(self):
        accounts = [
            make_account("acc-001", "Assets:Checking", "BANK"),
            make_account("orp-001", "Orphan-USD", "BANK"),
        ]
        em = _fully_mapped_em(["acc-001", "orp-001"])
        book = MockBook(accounts=accounts)
        result = ValidationResult()

        validate_accounts(book, em, result, strict_mode=False, quiet=True)

        assert result.has_warnings

    def test_no_accounts_produces_no_problems(self):
        em = _fully_mapped_em([])
        book = MockBook(accounts=[])
        result = ValidationResult()

        validate_accounts(book, em, result, strict_mode=True, quiet=True)

        assert not result.has_errors
        assert not result.has_warnings


# ---------------------------------------------------------------------------
# validate_transactions
# ---------------------------------------------------------------------------


class TestValidateTransactions:
    def test_balanced_transactions_produce_no_errors(self):
        transactions = [
            make_transaction(
                "t1", "2024-01-01", "Balanced",
                [make_split("a1", 100.0), make_split("a2", -100.0)],
            ),
        ]
        book = MockBook(transactions=transactions)
        config = GCGAAPConfig(numeric_tolerance=0.01)
        result = ValidationResult()

        validate_transactions(book, config, result, quiet=True)

        assert not result.has_errors

    def test_unbalanced_transaction_produces_error(self):
        transactions = [
            make_transaction(
                "t1", "2024-01-01", "Unbalanced Txn",
                [make_split("a1", 100.0), make_split("a2", -90.0)],
            ),
        ]
        book = MockBook(transactions=transactions)
        config = GCGAAPConfig(numeric_tolerance=0.01)
        result = ValidationResult()

        validate_transactions(book, config, result, quiet=True)

        assert result.has_errors
        assert result.error_count == 1
        assert "Unbalanced" in result.problems[0].message

    def test_multiple_unbalanced_transactions(self):
        transactions = [
            make_transaction("t1", "2024-01-01", "Txn A",
                             [make_split("a1", 100.0), make_split("a2", -80.0)]),
            make_transaction("t2", "2024-01-02", "Txn B",
                             [make_split("a1", 50.0), make_split("a2", -30.0)]),
        ]
        book = MockBook(transactions=transactions)
        config = GCGAAPConfig(numeric_tolerance=0.01)
        result = ValidationResult()

        validate_transactions(book, config, result, quiet=True)

        assert result.error_count == 2

    def test_value_error_from_iter_transactions_adds_error(self):
        """ValueError raised by iter_transactions is caught and reported as an error."""

        class BadBook(MockBook):
            def iter_transactions(self):
                raise ValueError("Found 1 transaction(s) with data integrity errors")

        book = BadBook()
        config = GCGAAPConfig()
        result = ValidationResult()

        validate_transactions(book, config, result, quiet=True)

        assert result.has_errors

    def test_date_value_error_uses_date_message(self):
        """ValueError with 'datetime' in message generates 'invalid or missing date' error."""

        class DateErrorBook(MockBook):
            def iter_transactions(self):
                raise ValueError("Couldn't parse datetime string: ''")

        book = DateErrorBook()
        config = GCGAAPConfig()
        result = ValidationResult()

        validate_transactions(book, config, result, quiet=True)

        assert result.has_errors
        # The error message should mention "date"
        assert any("date" in p.message.lower() for p in result.problems)

    def test_transaction_balanced_within_custom_tolerance(self):
        """Transaction with small imbalance is OK within custom tolerance."""
        transactions = [
            make_transaction(
                "t1", "2024-01-01", "Nearly balanced",
                [make_split("a1", 100.0), make_split("a2", -99.99)],
            ),
        ]
        book = MockBook(transactions=transactions)
        config = GCGAAPConfig(numeric_tolerance=0.02)  # wider tolerance
        result = ValidationResult()

        validate_transactions(book, config, result, quiet=True)

        assert not result.has_errors


# ---------------------------------------------------------------------------
# scan_unmapped_accounts
# ---------------------------------------------------------------------------


class TestScanUnmappedAccounts:
    def test_returns_unmapped_accounts(self):
        accounts = [
            make_account("acc-001", "Assets:Checking", "BANK"),  # mapped
            make_account("acc-002", "Income:Other", "INCOME"),   # unmapped
        ]
        em = EntityMap(account_entities={"acc-001": "personal"})
        book = MockBook(accounts=accounts)

        unmapped = scan_unmapped_accounts(book, em)

        assert len(unmapped) == 1
        assert unmapped[0].guid == "acc-002"

    def test_returns_empty_list_when_all_mapped(self):
        accounts = [make_account("acc-001", "Assets:Checking", "BANK")]
        em = EntityMap(account_entities={"acc-001": "personal"})
        book = MockBook(accounts=accounts)

        unmapped = scan_unmapped_accounts(book, em)

        assert unmapped == []

    def test_returns_all_when_nothing_mapped(self):
        accounts = [
            make_account("a1", "Assets", "ASSET"),
            make_account("a2", "Income", "INCOME"),
        ]
        em = EntityMap()  # nothing mapped
        book = MockBook(accounts=accounts)

        unmapped = scan_unmapped_accounts(book, em)

        assert len(unmapped) == 2


# ---------------------------------------------------------------------------
# check_cross_entity_balancing_accounts
# ---------------------------------------------------------------------------


class TestCheckCrossEntityBalancingAccounts:
    def _two_entity_map(self) -> EntityMap:
        entities = {
            "personal": EntityDefinition("personal", "Personal", "individual"),
            "business": EntityDefinition("business", "Business LLC", "business"),
        }
        return EntityMap(
            entities=entities,
            account_entities={
                "eq-pers": "personal",
                "eq-biz": "business",
                "asset-001": "personal",
            },
        )

    def test_cross_entity_equity_account_detected(self):
        accounts = [
            make_account("eq-pers", "Equity:Cross-Entity Balancing", "EQUITY"),
        ]
        em = self._two_entity_map()
        book = MockBook(accounts=accounts)

        status_map = check_cross_entity_balancing_accounts(book, em)

        assert "personal" in status_map
        assert status_map["personal"].has_balancing_account is True
        assert "Equity:Cross-Entity Balancing" in status_map["personal"].balancing_accounts

    def test_inter_entity_equity_account_detected(self):
        accounts = [
            make_account("eq-biz", "Equity:Inter-Entity", "EQUITY"),
        ]
        em = self._two_entity_map()
        book = MockBook(accounts=accounts)

        status_map = check_cross_entity_balancing_accounts(book, em)

        assert status_map["business"].has_balancing_account is True

    def test_balancing_pattern_detected(self):
        accounts = [
            make_account("eq-pers", "Equity:Balancing Equity Account", "EQUITY"),
        ]
        em = self._two_entity_map()
        book = MockBook(accounts=accounts)

        status_map = check_cross_entity_balancing_accounts(book, em)

        assert status_map["personal"].has_balancing_account is True

    def test_regular_equity_account_not_detected(self):
        accounts = [
            make_account("asset-001", "Assets:Checking", "BANK"),
        ]
        em = self._two_entity_map()
        book = MockBook(accounts=accounts)

        status_map = check_cross_entity_balancing_accounts(book, em)

        assert status_map["personal"].has_balancing_account is False
        assert status_map["business"].has_balancing_account is False

    def test_non_equity_account_with_cross_entity_name_not_detected(self):
        """Only EQUITY accounts are checked."""
        accounts = [
            make_account("asset-001", "Assets:Cross-Entity Asset", "ASSET"),
        ]
        em = self._two_entity_map()
        book = MockBook(accounts=accounts)

        status_map = check_cross_entity_balancing_accounts(book, em)

        assert status_map["personal"].has_balancing_account is False

    def test_structural_entities_excluded(self):
        """Structural entities should not appear in the status map."""
        entities = {
            "placeholder_only_acct": EntityDefinition(
                "placeholder_only_acct", "Placeholder", "structural"
            ),
            "unassigned": EntityDefinition("unassigned", "Unassigned", "individual"),
        }
        em = EntityMap(entities=entities)
        book = MockBook(accounts=[])

        status_map = check_cross_entity_balancing_accounts(book, em)

        assert "placeholder_only_acct" not in status_map

    def test_empty_book_no_balancing_accounts(self):
        em = self._two_entity_map()
        book = MockBook(accounts=[])

        status_map = check_cross_entity_balancing_accounts(book, em)

        assert status_map["personal"].has_balancing_account is False
        assert status_map["business"].has_balancing_account is False


# ---------------------------------------------------------------------------
# validate_book
# ---------------------------------------------------------------------------


class TestValidateBook:
    def test_clean_book_no_problems(self):
        accounts = [make_account("acc-001", "Assets:Checking", "BANK")]
        transactions = [
            make_transaction(
                "t1", "2024-01-01", "Balanced",
                [make_split("acc-001", 100.0), make_split("acc-002", -100.0)],
            ),
        ]
        em = EntityMap(account_entities={"acc-001": "personal"})
        book = MockBook(accounts=accounts, transactions=transactions)

        result = validate_book(book, em, quiet=True)

        # May have warnings from unmapped acc-002 in the transaction,
        # but no errors (in normal mode)
        assert not result.has_errors

    def test_strict_mode_propagated(self):
        accounts = [make_account("acc-unmapped", "Assets:Checking", "BANK")]
        em = EntityMap()  # nothing mapped
        book = MockBook(accounts=accounts, transactions=[])

        result = validate_book(book, em, strict_mode=True, quiet=True)

        assert result.has_errors


# ---------------------------------------------------------------------------
# validate_for_reporting
# ---------------------------------------------------------------------------


class TestValidateForReporting:
    def test_raises_runtime_error_when_errors_exist(self):
        """validate_for_reporting raises RuntimeError if strict validation fails."""
        accounts = [make_account("acc-001", "Assets:Checking", "BANK")]
        em = EntityMap()  # nothing mapped → error in strict mode
        book = MockBook(accounts=accounts, transactions=[])

        with pytest.raises(RuntimeError, match="Strict validation FAILED"):
            validate_for_reporting(book, em)

    def test_returns_result_when_all_accounts_mapped(self):
        accounts = [make_account("acc-001", "Assets:Checking", "BANK")]
        em = EntityMap(account_entities={"acc-001": "personal"})
        book = MockBook(accounts=accounts, transactions=[])

        result = validate_for_reporting(book, em)

        assert not result.has_errors

    def test_result_type_is_validation_result(self):
        accounts = [make_account("acc-001", "Assets:Checking", "BANK")]
        em = EntityMap(account_entities={"acc-001": "personal"})
        book = MockBook(accounts=accounts, transactions=[])

        result = validate_for_reporting(book, em)

        assert isinstance(result, ValidationResult)
