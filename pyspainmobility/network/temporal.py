"""Temporal mobility networks with explicit observation coverage."""

from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, Iterator, Literal, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd
import polars as pl

from .builder import (
    ODSource,
    _as_lazy_frame,
    _invalid_od_condition,
    _normalized_node_ids,
    _selected_od_rows,
    build_network,
)
from .model import (
    NodeIndex,
    NetworkMetadata,
    NetworkSpec,
    SparseMobilityNetwork,
    _append_provenance,
)
from .metrics import (
    NetworkComparison,
    compare_networks,
    destination_similarity,
    edge_changes,
    node_strengths,
)


def _date_label(value: object) -> str:
    """Return the calendar date used by every temporal-network operation."""
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.isoformat()
    label = str(value).strip()
    try:
        return date.fromisoformat(label).isoformat()
    except ValueError as error:
        try:
            return datetime.fromisoformat(label.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            raise ValueError(
                "Date labels must be ISO-8601 dates or timestamps."
            ) from error


def _date_labels(values: Optional[Sequence[object]], name: str) -> Tuple[str, ...]:
    """Normalize a date sequence to a deterministic, duplicate-free tuple."""
    if values is None:
        return ()
    if isinstance(values, (str, bytes)):
        raise ValueError("%s must be a sequence of dates, not one string." % name)
    labels = tuple(sorted(_date_label(value) for value in values))
    if len(set(labels)) != len(labels):
        raise ValueError("%s must not contain duplicate dates." % name)
    return labels


def _time_expression(column: str) -> pl.Expr:
    return pl.col(column).cast(pl.String).str.strip_chars()


def _calendar_date_expression(column: str, dtype: object) -> pl.Expr:
    """Use identical day labels for Date, Datetime and string columns."""
    if dtype == pl.Date:
        return pl.col(column).cast(pl.String)
    if isinstance(dtype, pl.Datetime):
        return pl.col(column).dt.date().cast(pl.String)
    raw = _time_expression(column)
    # Validate the complete value before retaining its source-calendar day.
    # Offset datetimes are parsed only for validation: converting them to UTC
    # before extracting the day would move observations around midnight.
    plain_date = raw.str.strptime(pl.Date, "%Y-%m-%d", strict=False)
    naive_timestamp = pl.coalesce(
        [
            raw.str.strptime(
                pl.Datetime(), "%Y-%m-%dT%H:%M:%S%.f", strict=False
            ),
            raw.str.strptime(
                pl.Datetime(), "%Y-%m-%d %H:%M:%S%.f", strict=False
            ),
        ]
    )
    offset_timestamp = pl.coalesce(
        [
            raw.str.strptime(
                pl.Datetime(time_zone="UTC"),
                "%Y-%m-%dT%H:%M:%S%.f%#z",
                strict=False,
            ),
            raw.str.strptime(
                pl.Datetime(time_zone="UTC"),
                "%Y-%m-%d %H:%M:%S%.f%#z",
                strict=False,
            ),
        ]
    )
    valid_timestamp = pl.coalesce(
        [
            plain_date.cast(pl.String),
            naive_timestamp.cast(pl.String),
            offset_timestamp.cast(pl.String),
        ]
    ).is_not_null()
    return (
        pl.when(valid_timestamp)
        .then(raw.str.slice(0, 10).str.strptime(pl.Date, "%Y-%m-%d", strict=False))
        .otherwise(None)
        .cast(pl.String)
    )


def _date_filter_expression(
    column: str, labels: Sequence[str], dtype: object
) -> pl.Expr:
    """Filter dates while preserving Parquet partition pruning for Date data."""
    if dtype == pl.Date:
        try:
            values = [date.fromisoformat(label) for label in labels]
        except ValueError as error:
            raise ValueError(
                "Date-typed time columns require ISO-8601 date labels."
            ) from error
        return pl.col(column).is_in(values)
    return _calendar_date_expression(column, dtype).is_in(labels)


AcquisitionManifest = Union[pd.DataFrame, pl.DataFrame]


def _manifest_dates(
    manifest: AcquisitionManifest,
    requested_dates: Tuple[str, ...],
    date_column: str,
    status_column: str,
) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    """Validate a file-acquisition manifest and return all/observed dates."""
    if isinstance(manifest, pd.DataFrame):
        frame = pl.from_pandas(manifest, include_index=False)
    elif isinstance(manifest, pl.DataFrame):
        frame = manifest
    else:
        raise TypeError("acquisition_manifest must be a pandas or Polars DataFrame.")
    required = {date_column, status_column}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(
            "Acquisition manifest is missing required columns: %s" % missing
        )
    table = frame.select(
        _calendar_date_expression(date_column, frame.schema[date_column]).alias("_date"),
        pl.col(status_column)
        .cast(pl.String)
        .str.strip_chars()
        .str.to_lowercase()
        .alias("_status"),
        *(
            [
                pl.col("parse_status")
                .cast(pl.String)
                .str.strip_chars()
                .str.to_lowercase()
                .alias("_parse_status")
            ]
            if "parse_status" in frame.columns
            else []
        ),
    )
    invalid = table.filter(
        pl.col("_date").is_null()
        | pl.col("_date").eq("")
        | pl.col("_status").is_null()
        | pl.col("_status").eq("")
    )
    if not invalid.is_empty():
        raise ValueError("Acquisition manifest contains null or empty dates/statuses.")
    duplicates = table.group_by("_date").len().filter(pl.col("len") > 1)
    if not duplicates.is_empty():
        raise ValueError("Acquisition manifest must have exactly one row per date.")
    known_statuses = {"available", "missing", "failed", "empty"}
    unknown_statuses = set(table.get_column("_status").to_list()) - known_statuses
    if unknown_statuses:
        raise ValueError(
            "Acquisition manifest has unsupported statuses: %s"
            % sorted(unknown_statuses)
        )
    if "_parse_status" in table.columns:
        parse_statuses = set(table.get_column("_parse_status").to_list())
        unknown_parse_statuses = parse_statuses - {
            "not_processed", "valid", "empty", "failed"
        }
        if unknown_parse_statuses:
            raise ValueError(
                "Acquisition manifest has unsupported parse_status values: %s"
                % sorted(unknown_parse_statuses, key=str)
            )
    all_dates = tuple(sorted(table.get_column("_date").to_list()))
    if requested_dates:
        missing_requested = sorted(set(requested_dates) - set(all_dates))
        if missing_requested:
            raise ValueError(
                "Acquisition manifest does not cover requested dates: %s"
                % missing_requested[:5]
            )
        table = table.filter(pl.col("_date").is_in(requested_dates))
        all_dates = requested_dates
    observed_rows = table.filter(pl.col("_status") == "available")
    if "_parse_status" in table.columns:
        observed_rows = observed_rows.filter(
            pl.col("_parse_status").is_in(["valid", "empty"])
        )
    observed = tuple(
        sorted(
            observed_rows.get_column("_date").to_list()
        )
    )
    return all_dates, observed


@dataclass(frozen=True)
class TemporalCoverage:
    """Distinguish requested, source-observed, and data-bearing dates.

    ``source_dates`` comes from a caller-provided source manifest when one is
    available: for example, the list of downloaded MITMA files that were
    successfully parsed.  It can therefore contain a date with an empty OD
    file.  Without such a manifest it is inferred from OD rows and empty
    observed days cannot be distinguished from unavailable source days.
    """

    requested_dates: Tuple[str, ...]
    source_dates: Tuple[str, ...]
    data_dates: Tuple[str, ...]
    source_manifest_provided: bool
    excluded_data_dates: Tuple[str, ...] = ()
    excluded_data_weight: float = 0.0

    def __post_init__(self) -> None:
        requested = _date_labels(self.requested_dates, "requested_dates")
        source = _date_labels(self.source_dates, "source_dates")
        data = _date_labels(self.data_dates, "data_dates")
        excluded = _date_labels(self.excluded_data_dates, "excluded_data_dates")
        if not set(source).issubset(requested):
            raise ValueError("source_dates must be a subset of requested_dates.")
        if not set(data).issubset(source):
            raise ValueError("data_dates must be a subset of source_dates.")
        if not self.source_manifest_provided and source != data:
            raise ValueError(
                "Without a source manifest, source_dates must equal data_dates."
            )
        if not set(excluded).issubset(requested) or set(excluded) & set(data):
            raise ValueError(
                "excluded_data_dates must be requested dates absent from data_dates."
            )
        if not np.isfinite(self.excluded_data_weight) or self.excluded_data_weight < 0:
            raise ValueError("excluded_data_weight must be finite and non-negative.")
        object.__setattr__(self, "requested_dates", requested)
        object.__setattr__(self, "source_dates", source)
        object.__setattr__(self, "data_dates", data)
        object.__setattr__(self, "excluded_data_dates", excluded)
        object.__setattr__(self, "excluded_data_weight", float(self.excluded_data_weight))

    @property
    def missing_source_dates(self) -> Tuple[str, ...]:
        """Requested dates known to be absent from the source manifest."""
        if not self.source_manifest_provided:
            return ()
        return tuple(sorted(set(self.requested_dates) - set(self.source_dates)))

    @property
    def empty_observed_dates(self) -> Tuple[str, ...]:
        """Observed source dates for which the OD table has no rows."""
        return tuple(sorted(set(self.source_dates) - set(self.data_dates)))

    @property
    def unresolved_requested_dates(self) -> Tuple[str, ...]:
        """Requested dates whose source availability is unknown."""
        if self.source_manifest_provided:
            return ()
        return tuple(sorted(set(self.requested_dates) - set(self.data_dates)))

    def audit(self) -> Dict[str, object]:
        """Return JSON-friendly coverage counts and explicit date categories."""
        return {
            "requested_day_count": len(self.requested_dates),
            "observed_source_day_count": len(self.source_dates),
            "data_day_count": len(self.data_dates),
            "source_manifest_provided": self.source_manifest_provided,
            "missing_source_dates": list(self.missing_source_dates),
            "empty_observed_dates": list(self.empty_observed_dates),
            "unresolved_requested_dates": list(self.unresolved_requested_dates),
            "excluded_failed_data_dates": list(self.excluded_data_dates),
            "excluded_failed_data_weight": self.excluded_data_weight,
        }


@dataclass
class TemporalMobilityNetwork:
    """Lazy snapshots that share one immutable node index.

    Snapshot matrices are constructed only when requested. An LRU cache bounds
    retained CSR matrices while every snapshot uses the same ``node_ids``, so
    entries at the same matrix coordinates refer to the same zones.
    """

    _source: pl.LazyFrame = field(repr=False)
    time_column: str
    spec: NetworkSpec
    node_ids: np.ndarray
    coverage: TemporalCoverage
    max_cached_snapshots: Optional[int] = 32
    _cache: OrderedDict[str, SparseMobilityNetwork] = field(
        default_factory=OrderedDict, repr=False
    )
    node_index: Optional[NodeIndex] = None
    _time_dtype: object = field(init=False, repr=False)
    _source_date_set: frozenset[str] = field(init=False, repr=False)
    _data_date_set: frozenset[str] = field(init=False, repr=False)
    _empty_date_set: frozenset[str] = field(init=False, repr=False)
    _missing_date_set: frozenset[str] = field(init=False, repr=False)
    _configuration_locked: bool = field(default=False, init=False, repr=False)

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_configuration_locked", False) and name in {
            "_source",
            "time_column",
            "spec",
            "node_ids",
            "coverage",
            "max_cached_snapshots",
            "node_index",
        }:
            raise AttributeError(
                "Temporal network configuration is immutable; build a new "
                "temporal network to change it."
            )
        super().__setattr__(name, value)

    def __post_init__(self) -> None:
        if self.max_cached_snapshots is not None and (
            isinstance(self.max_cached_snapshots, bool)
            or not isinstance(self.max_cached_snapshots, int)
            or self.max_cached_snapshots < 0
        ):
            raise ValueError(
                "max_cached_snapshots must be a non-negative integer or None."
            )
        node_ids = _normalized_node_ids(self.node_ids)
        if self.node_index is None:
            self.node_index = NodeIndex(node_ids)
        elif not isinstance(self.node_index, NodeIndex):
            raise TypeError("node_index must be a NodeIndex instance.")
        elif not np.array_equal(node_ids, self.node_index.node_ids):
            raise ValueError("node_ids and node_index.node_ids must be identical.")
        self.node_ids = self.node_index.node_ids
        self._time_dtype = self._source.collect_schema()[self.time_column]
        self._source_date_set = frozenset(self.coverage.source_dates)
        self._data_date_set = frozenset(self.coverage.data_dates)
        self._empty_date_set = self._source_date_set - self._data_date_set
        self._missing_date_set = (
            frozenset(self.coverage.requested_dates) - self._source_date_set
            if self.coverage.source_manifest_provided
            else frozenset()
        )
        self._configuration_locked = True

    def _date_filter(self, label: str) -> pl.Expr:
        """Build a schema-aware one-date filter for lazy snapshot scans."""
        return _date_filter_expression(self.time_column, [label], self._time_dtype)

    def _cache_get(self, label: str) -> Optional[SparseMobilityNetwork]:
        """Fetch and refresh one LRU entry when snapshot caching is enabled."""
        if label not in self._cache:
            return None
        network = self._cache.pop(label)
        self._cache[label] = network
        return network

    def _cache_put(self, label: str, network: SparseMobilityNetwork) -> None:
        """Store one snapshot and evict the least recently used entry."""
        if self.max_cached_snapshots == 0:
            return
        self._cache[label] = network
        if self.max_cached_snapshots is not None:
            while len(self._cache) > self.max_cached_snapshots:
                self._cache.popitem(last=False)

    @property
    def number_of_observed_days(self) -> int:
        """Days known observed in the source, including known empty days."""
        return len(self.coverage.source_dates)

    def snapshot(self, when: object) -> SparseMobilityNetwork:
        """Return the cached or lazily built network for one observed date."""
        label = _date_label(when)
        cached = self._cache_get(label)
        if cached is not None:
            return cached
        if label not in self._source_date_set:
            if label in self._missing_date_set:
                raise ValueError(
                    "%s is missing from the observed source manifest." % label
                )
            raise ValueError(
                "%s is not an observed date in this temporal network." % label
            )

        if label in self._empty_date_set:
            empty = pl.DataFrame(
                {
                    self.spec.origin: [],
                    self.spec.destination: [],
                    self.spec.weight: [],
                }
            )
            network = build_network(
                empty,
                spec=self.spec,
                node_index=self.node_index,
                provenance={"temporal": {"date": label}},
            )
        else:
            network = build_network(
                self._source.filter(self._date_filter(label)),
                spec=self.spec,
                node_index=self.node_index,
                provenance={"temporal": {"date": label}},
            )
        self._cache_put(label, network)
        return network

    def clear_cache(self) -> None:
        """Release all cached snapshot matrices without changing the source."""
        self._cache.clear()

    def snapshots(
        self, include_empty: bool = False
    ) -> Iterator[Tuple[str, SparseMobilityNetwork]]:
        """Yield snapshots in date order, building each one only on demand."""
        dates = (
            self.coverage.source_dates
            if include_empty
            else self.coverage.data_dates
        )
        for label in dates:
            yield label, self.snapshot(label)

    def _observed_dates_for_aggregation(
        self, dates: Optional[Sequence[object]]
    ) -> Tuple[str, ...]:
        """Validate the denominator used by temporal aggregations."""
        selected = (
            self.coverage.source_dates
            if dates is None
            else _date_labels(dates, "dates")
        )
        if not selected:
            raise ValueError("At least one observed source date is required.")
        unavailable = sorted(set(selected) - self._source_date_set)
        if unavailable:
            raise ValueError(
                "Temporal aggregation requires observed source dates; unavailable: %s"
                % unavailable[:5]
            )
        return selected

    def _aggregate_network(
        self, dates: Optional[Sequence[object]], mean: bool
    ) -> SparseMobilityNetwork:
        """Aggregate selected OD rows in one scan, then construct one CSR."""
        selected = self._observed_dates_for_aggregation(dates)
        selected_with_data = tuple(
            label for label in selected if label in self._data_date_set
        )
        summed = build_network(
            self._source.filter(
                _date_filter_expression(
                    self.time_column, selected_with_data, self._time_dtype
                )
            ),
            spec=self.spec,
            node_index=self.node_index,
        )
        denominator = len(selected)
        aggregation = "mean_per_observed_day" if mean else "sum"
        matrix = summed.adjacency
        input_weight = summed.metadata.input_weight
        dropped_self_loop_weight = summed.metadata.dropped_self_loop_weight
        if mean:
            matrix = (matrix / denominator).tocsr()
            input_weight /= denominator
            dropped_self_loop_weight /= denominator
        metadata = NetworkMetadata(
            weight=self.spec.weight,
            directed=True,
            aggregation=aggregation,
            self_loops=self.spec.self_loops,
            node_universe="provided",
            input_edge_count=summed.metadata.input_edge_count,
            represented_edge_count=matrix.nnz,
            input_weight=input_weight,
            represented_weight=float(matrix.sum()),
            dropped_self_loop_weight=dropped_self_loop_weight,
            weight_normalization="per_observed_day" if mean else None,
        )
        provenance = _append_provenance(
            summed.provenance,
            "temporal",
            {
                "aggregation": aggregation,
                "observed_dates": list(selected),
                "observed_day_count": denominator,
                "source_manifest_provided": self.coverage.source_manifest_provided,
            },
        )
        return SparseMobilityNetwork(
            matrix,
            self.node_index.node_ids,
            metadata,
            provenance,
            self.node_index,
        )

    def sum_network(
        self, dates: Optional[Sequence[object]] = None
    ) -> SparseMobilityNetwork:
        """Sum flows across selected observed source dates."""
        return self._aggregate_network(dates, mean=False)

    def mean_per_observed_day(
        self, dates: Optional[Sequence[object]] = None
    ) -> SparseMobilityNetwork:
        """Average flows over selected observed source dates.

        Known empty observed dates remain in the denominator.  A requested
        date that is missing or failed in the source manifest raises instead
        of being converted to a zero-flow day.
        """
        return self._aggregate_network(dates, mean=True)

    def snapshot_strengths(self, when: object) -> pl.DataFrame:
        """Return in/out weighted strength for every node on one observed day."""
        return node_strengths(self.snapshot(when))

    def compare_snapshots(
        self, left: object, right: object
    ) -> NetworkComparison:
        """Compare two observed dates with a shared node-index contract."""
        left_label = _date_label(left)
        right_label = _date_label(right)
        return compare_networks(
            self.snapshot(left_label),
            self.snapshot(right_label),
            left_label=left_label,
            right_label=right_label,
        )

    def snapshot_edge_changes(self, left: object, right: object) -> pl.DataFrame:
        """Return the sparse union of directed-edge changes between two dates."""
        return edge_changes(self.snapshot(left), self.snapshot(right))

    def destination_stability(self, left: object, right: object) -> pl.DataFrame:
        """Return per-origin destination-profile similarity between two dates."""
        return destination_similarity(self.snapshot(left), self.snapshot(right))

    def audit(self) -> Dict[str, object]:
        """Return temporal coverage and cache status."""
        result = self.coverage.audit()
        result.update(
            {
                "number_of_nodes": len(self.node_ids),
                "cached_snapshot_count": len(self._cache),
                "max_cached_snapshots": self.max_cached_snapshots,
                "cached_snapshot_dates": list(self._cache),
            }
        )
        if (
            self.node_index.zoning_id is not None
            or self.node_index.zoning_version is not None
        ):
            result["node_index"] = self.node_index.describe()
        return result


def build_temporal_network(
    data: ODSource,
    *,
    spec: Optional[NetworkSpec] = None,
    time_column: str = "date",
    requested_dates: Optional[Sequence[object]] = None,
    observed_dates: Optional[Sequence[object]] = None,
    acquisition_manifest: Optional[AcquisitionManifest] = None,
    manifest_date_column: str = "date",
    manifest_status_column: str = "status",
    node_ids: Optional[Sequence[object]] = None,
    node_index: Optional[NodeIndex] = None,
    max_cached_snapshots: Optional[int] = 32,
    failed_data_policy: Literal["error", "exclude"] = "error",
) -> TemporalMobilityNetwork:
    """Create a lazy, coverage-aware set of temporal mobility snapshots.

    ``observed_dates`` is deliberately separate from OD rows. Pass the dates
    of source files successfully obtained/parsed to correctly represent an
    observed day with zero OD rows. Prefer ``acquisition_manifest`` from
    ``Mobility.get_acquisition_manifest()``: it also records failed and empty
    source files before OD filtering. If both are omitted, source coverage is
    inferred from data rows and requested-but-empty dates stay unresolved.

    ``data`` may be a Hive-partitioned Parquet directory such as
    ``date=2024-01-01/part-0.parquet``. The partition column is available as
    ``time_column`` and date filters retain Polars partition pruning. By
    default at most 32 snapshot matrices are retained; pass ``None`` for an
    unbounded cache or ``0`` to disable snapshot caching.

    If a source manifest marks a day as failed but the OD table still contains
    its rows, the default ``failed_data_policy='error'`` stops the pipeline:
    a partial day must never enter an observed-day average. Pass ``'exclude'``
    to deliberately remove every row for such failed dates.
    """
    spec = NetworkSpec() if spec is None else spec
    if not isinstance(spec, NetworkSpec):
        raise TypeError("spec must be a NetworkSpec instance.")
    if observed_dates is not None and acquisition_manifest is not None:
        raise ValueError(
            "Pass either observed_dates or acquisition_manifest, not both."
        )
    if node_ids is not None and node_index is not None:
        raise ValueError("Pass either node_ids or node_index, not both.")
    if node_index is not None:
        if not isinstance(node_index, NodeIndex):
            raise TypeError("node_index must be a NodeIndex instance.")
        node_ids = node_index.node_ids
    if not isinstance(time_column, str) or not time_column:
        raise ValueError("time_column must be a non-empty column name.")
    if failed_data_policy not in {"error", "exclude"}:
        raise ValueError("failed_data_policy must be either 'error' or 'exclude'.")

    source = _as_lazy_frame(data)
    schema = source.collect_schema()
    available = set(schema.names())
    if time_column not in available:
        raise ValueError("OD input is missing time_column=%r." % time_column)

    requested_provided = requested_dates is not None
    requested = _date_labels(requested_dates, "requested_dates")
    if acquisition_manifest is not None:
        manifest_dates, observed = _manifest_dates(
            acquisition_manifest,
            requested,
            manifest_date_column,
            manifest_status_column,
        )
        if not requested:
            requested = manifest_dates
    else:
        observed = _date_labels(observed_dates, "observed_dates")
    if requested and observed and not set(observed).issubset(requested):
        raise ValueError("observed_dates must be a subset of requested_dates.")
    if not requested:
        requested = observed

    scoped_source = source
    if requested_provided:
        canonical_date = _calendar_date_expression(time_column, schema[time_column])
        scoped_source = scoped_source.filter(
            _date_filter_expression(time_column, requested, schema[time_column])
            | canonical_date.is_null()
        )

    def inspect_source(frame: pl.LazyFrame):
        selected = _selected_od_rows(
            frame,
            spec,
            [_calendar_date_expression(time_column, schema[time_column]).alias("_date")],
        )
        invalid_condition = (
            _invalid_od_condition() | pl.col("_date").is_null() | pl.col("_date").eq("")
        )
        valid = selected.filter(~invalid_condition)
        invalid_query = selected.filter(invalid_condition).select(pl.len().alias("count"))
        dates_query = valid.select("_date").unique().sort("_date")
        weights_query = valid.group_by("_date").agg(
            pl.col("_weight").sum().alias("_weight")
        )
        nodes_query = (
            pl.concat(
                [
                    valid.select(pl.col("_origin").alias("_node")),
                    valid.select(pl.col("_destination").alias("_node")),
                ]
            )
            .unique()
            .sort("_node")
        )
        invalid, dates, nodes, weights = pl.collect_all(
            [invalid_query, dates_query, nodes_query, weights_query]
        )
        invalid_count = int(invalid.item(0, "count"))
        if invalid_count:
            raise ValueError(
                "%d OD rows have invalid endpoint, weight, or date values."
                % invalid_count
            )
        return (
            tuple(dates.get_column("_date").to_list()),
            nodes,
            dict(zip(weights.get_column("_date").to_list(), weights.get_column("_weight").to_list())),
        )

    data_dates, nodes_frame, date_weights = inspect_source(scoped_source)
    if not requested:
        requested = data_dates
    source_dates = (
        observed
        if observed_dates is not None or acquisition_manifest is not None
        else data_dates
    )
    failed_dates_with_data = tuple(sorted(set(data_dates) - set(source_dates)))
    excluded_data_weight = 0.0
    if failed_dates_with_data:
        if failed_data_policy == "error":
            raise ValueError(
                "OD input contains rows for dates not observed by the source "
                "manifest: %s. This usually indicates a partially failed "
                "source day; remove it upstream or pass failed_data_policy='exclude'."
                % list(failed_dates_with_data[:5])
            )
        scoped_source = scoped_source.filter(
            ~_date_filter_expression(
                time_column, failed_dates_with_data, schema[time_column]
            )
        )
        excluded_data_weight = float(
            sum(date_weights[label] for label in failed_dates_with_data)
        )
        data_dates, nodes_frame, _ = inspect_source(scoped_source)
    coverage = TemporalCoverage(
        requested_dates=requested,
        source_dates=source_dates,
        data_dates=data_dates,
        source_manifest_provided=(
            observed_dates is not None or acquisition_manifest is not None
        ),
        excluded_data_dates=(
            failed_dates_with_data if failed_data_policy == "exclude" else ()
        ),
        excluded_data_weight=excluded_data_weight,
    )

    if node_ids is None:
        if nodes_frame.is_empty():
            raise ValueError("OD input contains no valid flow rows and no node_ids.")
        node_array = _normalized_node_ids(nodes_frame.get_column("_node").to_list())
    else:
        node_array = _normalized_node_ids(node_ids)
        unknown = set(nodes_frame.get_column("_node").to_list()) - set(node_array)
        if unknown:
            raise ValueError(
                "node_ids does not cover every OD endpoint; examples: %s"
                % sorted(unknown)[:5]
            )

    return TemporalMobilityNetwork(
        _source=scoped_source,
        time_column=time_column,
        spec=spec,
        node_ids=node_array,
        coverage=coverage,
        node_index=node_index,
        max_cached_snapshots=max_cached_snapshots,
    )
