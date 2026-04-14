# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `DaemonConnectionError` exception (replaces shadowed `ConnectionError`)
- `Currency.__rmul__` for `3 * Currency(10)` support
- Export all public types from `mina_sdk`: `AccountBalance`, `AccountData`,
  `BlockInfo`, `DaemonStatus`, `PeerInfo`, `SendPaymentResult`,
  `SendDelegationResult`, `GraphQLError`, `DaemonConnectionError`,
  `CurrencyUnderflow`
- Input validation for `MinaDaemonClient` configuration parameters
- Docstrings on all public classes, methods, and dataclass fields
- 11 new unit tests (49 total)

### Fixed
- HTTP status code now checked before parsing JSON response body
- JSON decode errors are caught and wrapped as `DaemonConnectionError`
- Negative `Currency` values are rejected with `ValueError`

### Changed
- `Currency.__mul__` only accepts `int` scalars (was also accepting `Currency`,
  which produced nonsensical nanomina-squared units)
- `ConnectionError` is now an alias for `DaemonConnectionError` (backwards compatible)

## [0.1.0] - 2025-11-20

### Added
- Initial release
- `MinaDaemonClient` with GraphQL queries and mutations
- `Currency` type with nanomina-precision arithmetic
- Typed response dataclasses
- Automatic retry with configurable backoff
- Context manager support
- Unit tests with HTTP mocking
- Integration tests against live daemon
- CI workflows: lint, test, release, integration, schema drift
- PyPI publishing via trusted publishers
