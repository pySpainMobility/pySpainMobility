# Changelog

All notable changes to this project are documented in this file.

## Unreleased

### Added
- Version 1 district OD data can retain origin and destination activity with
  `get_od_data(keep_activity=True)`, including the `trabajo` and `otros`
  labels across all processing backends. Municipality files lack activity
  columns, so requesting them now raises a clear error.

### Fixed
- Refuse to save date-range outputs when daily downloads are missing, or OD
  source days contain invalid mandatory rows; explicitly requested partial OD
  results exclude invalid days and use a `_partial` filename suffix.
- Keep OD output variants for activity and demographic dimensions in separate
  Parquet files, and replace finished files atomically.
- Exclude negative and non-finite OD trip and distance weights across pandas
  and Polars, and let the pandas backend write Parquet without optional Arrow.
- Validate OD calendar dates and hourly periods before including rows; flag
  invalid source days in acquisition manifests on both pandas and Polars paths.
- Apply failed-day exclusion before validating OD rows and report excluded
  rows whose weights or endpoints are invalid.
- Validate only requested zone relations when a source-ID subset is supplied.
- Reject nested node IDs and avoid overflow in per-origin cosine similarity
  for subnormal positive weights.

### Changed
- Require GeoPandas 1.1.4 or newer in its 1.1 series for the SQL injection fix
  and subsequent `to_postgis` hardening. This raises the minimum supported
  Python version to 3.10 and pandas version to 2.0.
- Move automated tests into `tests/` and keep live tests opt-in.
- Make Arrow and Dask optional pip extras and remove unused Matplotlib from
  runtime dependencies. Pandas input and output remain supported without Arrow.
- Reuse an unchanged, previously validated compressed download without
  decompressing it again on every cache hit.

## [2.0.0] - 2026-09-22

This major release introduces an auditable sparse-network analysis API and
makes Polars the preferred processing backend. Review code that relies on the
legacy default backend or treats territorial relations as arbitrary one-to-one
lookups before upgrading.

### Added
- Lazy/streaming Polars backend via `Mobility(backend="polars")`, installed with the base package.
- Automatic backend selection via the new `backend="auto"` default, preferring Polars, then Arrow, then pandas.
- `pyspainmobility.network`: auditable, directed CSR mobility networks with a stable node index and an optional NetworkX adapter (`pyspainmobility[network]`).
- Lazy temporal network snapshots with shared node IDs and explicit source/data coverage manifests.
- Spatial aggregation for OD data (Polars) and existing CSR networks (`P.T @ A @ P`) with complete-mapping validation and internalized-flow audits.
- `NodeIndex` contracts with optional zoning identifier/version, safe matrix alignment, and propagation through static, temporal, and spatial networks.
- Date-level pre-filter acquisition manifests from `Mobility`, consumable by temporal networks to distinguish failed/empty source files from zero-flow snapshots.
- `TemporalMobilityNetwork.sum_network()` and `mean_per_observed_day()` with an explicit observed-day denominator and temporal provenance.
- Optional CSR-native Infomap adapter (`pyspainmobility[infomap]`) with explicit directed semantics and reproducible, backend-neutral community partitions.
- Sparse node-strength, edge-change, destination-profile, and pairwise network-comparison metrics, also available through temporal snapshots.
- Explicit `sum`, `mean`, `max`, and `mutual` directed-to-undirected transformations with non-double-counted logical-flow accounting.
- Bounded LRU snapshot caching and Hive-partitioned Parquet dataset input for temporal networks, including partition-prunable date filters.
- Python-version test matrix and optional network-adapter CI checks.

### Changed
- OD, overnight-stay, and number-of-trips inputs can now be processed as one lazy multi-file Polars plan.
- Polars writes Parquet directly when `return_df=False`, avoiding an intermediate pandas DataFrame.
- Temporal snapshots attach provenance during CSR construction, avoiding a second full matrix copy.

### Fixed
- Normalized cached and freshly built `Zones` geometries to the same string
  `id` index contract.
- Added validated relation-to-network mappings: duplicate identical relations
  are safe, while missing or ambiguous targets now fail explicitly instead of
  silently selecting a correspondence. Added a district-to-province helper
  based on INE municipality codes.
- Preserved OD flows with missing demographic dimensions when `social_agg=True`.
- Made dot-thousands parsing row-local, so Polars and pandas results no longer depend on which other files are processed in the same batch.
- Aligned Date, Datetime, and pandas timestamps in temporal networks; period aggregation now scans selected OD rows once.
- Corrected undirected spatial flow accounting, source self-loop policies, custom weight labels, and provenance through composed transformations.
- Excluded acquired but invalid OD files from observed-day denominators using per-file parse status.
- Corrected empty-network cosine similarity and validated canonical sparse-matrix invariants.
- Removed repeated Infomap node-name copies and included direction in its network fingerprint.
- Kept ISO timestamp strings in their calendar-day snapshots, rejected malformed date strings, and retained Hive partition pruning.
- Made undirected audit records JSON-serialisable and preserved read-only network storage across pickle round trips.
- Prevented partially parsed source days from silently entering temporal averages; callers can now explicitly exclude their remaining OD rows.
- Preserved initial construction accounting through temporal, spatial, and undirected transformations.
- Rejected impossible ISO clock values, stabilised cosine metrics for extreme finite weights, and canonicalised harmless floating-point asymmetry after sparse projections.

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
