# Changelog

All notable changes to GCGAAP will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Placeholder Account Validation**
  - Placeholder accounts now labeled as `placeholder_only_acct` entity (not `unassigned`)
  - New validation check verifies placeholder accounts contain no transactions
  - Added `is_placeholder` field to `GCAccount` dataclass
  - Added `structural` entity type for placeholder-only accounts
  - Placeholder accounts reported as violations only if they contain transactions
  - Entity mapper automatically detects and labels placeholder accounts

### Changed
- Entity mapper now properly identifies placeholder accounts from GnuCash database
- EntityDefinition now supports three entity types: `individual`, `business`, and `structural`
- Validation reports now include placeholder account transaction checks

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

- **Strict Validation Mode**
  - `--strict` flag for `validate` command
  - Enforces 100% entity mapping coverage (required for reports)
  - Unmapped accounts become errors instead of warnings
  - `validate_for_reporting()` helper function for Phase 2
  - Ensures GAAP compliance: sum of entities = total book

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
