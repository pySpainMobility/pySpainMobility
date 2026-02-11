# Changelog

All notable changes to this project are documented in this file.

## [1.1.0] - 2026-02-11

### Added
- `Mobility(backend=...)` with `arrow` (default) and `pandas` support.
- Additional test coverage for translation/parsing/output path and backend behavior.

### Changed
- Automatic fallback from Arrow to pandas with a warning when `pyarrow` is not available.
- `Zones` download behavior aligned with lazy loading (download on first data request).
- Documentation workflow now builds docs from the repository code (`.[docs]`) instead of the PyPI package.

### Fixed
- `output_directory` handling in zone-related loading paths.
- Robust column translation/normalization when source headers differ in case/BOM format.
- Flow-size preprocessing where numeric values include separators.
