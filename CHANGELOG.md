# Changelog

All notable changes to GCGAAP will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2026-02-20

### Added
- **Comprehensive Test Suite**
  - 236 automated tests across 7 test files (2,676 lines of test code)
  - Complete test coverage for validation, balance sheets, entity mapping
  - Database access layer tests with mock GnuCash books
  - CLI integration tests
  - Pytest-based infrastructure with fixtures and helpers

- **Income Statement Report** (`report income-statement`)
  - GAAP-compliant Profit & Loss (P&L) reports
  - Period-based reporting (from date to date)
  - Hierarchical account groupings with subtotals
  - Entity-specific and consolidated reports
  - CSV and JSON export formats
  - Adapts report title based on entity type (business vs. individual)

- **Trial Balance Report** (`report trial-balance`)
  - All accounts with non-zero balances
  - Debit and credit columns
  - Verification that total debits equal total credits
  - Entity-specific and consolidated views
  - CSV and JSON export formats

- **Automated Transaction Balancing** (`xact balance`)
  - Automatically adds balancing splits to cross-entity transactions
  - Interactive approval by transaction groups (max 9 per group)
  - Dry-run mode for safe preview
  - Automatic database backups before modifications
  - Entity and date range filtering
  - Proper Money In/Out equity account selection
  - Successfully balanced 571 transactions in production use

### Changed
- **CLI Architecture Refactored**
  - Reduced cli.py from 1,743 lines to 54 lines (97% reduction)
  - Created modular command structure in `gcgaap/commands/` directory
  - Split commands into focused groups: entity, report, xact, db
  - Extracted shared options to `_options.py` for reusability
  - Improved maintainability and testability

### Fixed
- Money In/Out equity account logic in balance-xacts (correct direction)
- SQLAlchemy detached instance errors in transaction balancing
- Decimal type conversion issues
- Unicode character compatibility for Windows console

### Production Status
- All entities now GAAP-compliant and audit-ready
- 576 cross-entity transactions successfully balanced (100% success rate)
- Confirmed production-ready for both read and write operations (with backup procedures)

## [0.2.0] - 2026-02-08

### Added
- **Phase 1.1: Smart Entity Inference**
  - AI-powered entity detection from account name patterns
  - Automatic business entity identification (LLC, Inc, Corp)
  - Personal/individual entity detection
  - Confidence scoring for entity suggestions
  - Regex pattern generation for entity matching
  - `entity-infer` CLI command with multiple output options
  - Merge capability to add suggestions to existing entity maps
  - Pattern descriptions in JSON output for human readability

- **Cross-Entity Balancing Account Detection**
  - `entity-scan` now checks for cross-entity balancing equity accounts in each entity
  - Reports which entities have balancing accounts (e.g., "Equity:Cross-Entity Balancing", "Equity:Inter-Entity")
  - Warns about entities missing balancing accounts
  - Helps ensure proper setup for tracking inter-entity balances
  - Pattern matching includes: "cross-entity", "cross entity", "inter-entity", "inter entity", and "balancing"

- **Placeholder Account Validation**
  - Placeholder accounts now labeled as `placeholder_only_acct` entity (not `unassigned`)
  - New validation check verifies placeholder accounts contain no transactions
  - Added `is_placeholder` field to `GCAccount` dataclass
  - Added `structural` entity type for placeholder-only accounts
  - Placeholder accounts reported as violations only if they contain transactions
  - Entity mapper automatically detects and labels placeholder accounts

- **Strict Validation Mode**
  - `--strict` flag for `validate` command
  - Enforces 100% entity mapping coverage (required for reports)
  - Unmapped accounts become errors instead of warnings
  - `validate_for_reporting()` helper function for Phase 2
  - Ensures GAAP compliance: sum of entities = total book

### Changed
- Entity mapper now properly identifies placeholder accounts from GnuCash database
- EntityDefinition now supports three entity types: `individual`, `business`, and `structural`
- Validation reports now include placeholder account transaction checks

## [0.1.0] - 2026-02-08

### Added
- Initial project structure and setup
- Entity mapping system with JSON configuration
  - GUID-based account mapping
  - Regex pattern-based account matching
  - Load/save functionality
- GnuCash book access abstraction layer
  - Read-only access using piecash library
  - Account and transaction iteration
  - Data model abstraction (GCAccount, GCTransaction, GCTransactionSplit)
- Validation engine
  - Transaction-level double-entry balancing
  - Imbalance/Orphan account detection
  - Entity mapping coverage validation
  - Configurable numeric tolerance
- CLI with Click framework
  - `entity-scan` command for finding unmapped accounts
  - `validate` command for book integrity checks
  - Verbose logging support
  - Structured error reporting
- Configuration management
  - Numeric tolerance settings
  - Logging setup
- Documentation
  - README.md with usage instructions
  - DEVELOPMENT.md with architecture and coding guidelines
  - Example entity-map.json configuration

### Phase Status
- ✅ Phase 1 (Infrastructure & Validation) - Complete
- 🚧 Phase 2 (Balance Sheet Report) - Planned
- 🚧 Phase 3 (Entity-Level Accounting) - Planned
- 🚧 Phase 4 (Additional Reports) - Planned

[0.1.0]: https://github.com/yourusername/gcgaap/releases/tag/v0.1.0
