# Changelog

All notable changes to this project are documented in this file.

## [1.1.2] - 2026-02-28

### Fixed
- Prevented decimal inflation in OD/overnight/number-of-trips parsing by using numeric parsing with conditional thousands stripping instead of forced dot compaction.
- Added a clearer `RuntimeError` when MITMA date discovery fails due to temporary upstream network/server issues.
- Fixed `available_mobility_data()` downloaded-file detection to recognize both raw RSS filenames and library-managed versioned files (`_v1`/`_v2`).
- Added Dask-to-pandas fallback handling for overnight stays and number-of-trips processing paths to match OD behavior.
- Updated documentation deployment workflow to use official GitHub Pages actions (`upload-pages-artifact` + `deploy-pages`) for more reliable publishing.

### Added
- Optional live smoke tests (`test_live_pipeline_smoke.py`) to validate real MITMA download/parsing pipelines and guard against value inflation regressions.

## [1.1.1] - 2026-02-12

### Fixed
- Python 3.9 compatibility issue in type annotations (`dict | None` replaced with `Optional[dict]`).

### Changed
- Conda runtime dependency updated from `dask-core` to `dask` to avoid future `dask-expr` import issues.

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
