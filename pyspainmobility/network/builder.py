"""Efficient construction of canonical sparse mobility networks."""

from pathlib import Path
from typing import Mapping, Optional, Sequence, Union

import numpy as np
import pandas as pd
import polars as pl
from scipy.sparse import coo_array

from .model import (
    NodeIndex,
    NetworkMetadata,
    NetworkSpec,
    SparseMobilityNetwork,
)


ODSource = Union[str, Path, pd.DataFrame, pl.DataFrame, pl.LazyFrame]


def _as_lazy_frame(data: ODSource) -> pl.LazyFrame:
    """Normalize supported tabular inputs without materialising Polars input."""
    if isinstance(data, pl.LazyFrame):
        return data
    if isinstance(data, pl.DataFrame):
        return data.lazy()
    if isinstance(data, pd.DataFrame):
        return pl.from_pandas(data, include_index=False).lazy()
    if isinstance(data, (str, Path)):
        path = Path(data)
        if path.is_dir():
            if next(path.rglob("*.parquet"), None) is None:
                raise ValueError(
                    "Parquet dataset directories must contain Parquet files."
                )
            return pl.scan_parquet(
                str(path / "**" / "*.parquet"), hive_partitioning=True
            )
        if path.suffix.lower() != ".parquet":
            raise ValueError(
                "Path inputs must be a Parquet file or dataset directory. "
                "Pass a Polars or pandas DataFrame for another tabular format."
            )
        return pl.scan_parquet(path)
    raise TypeError(
        "data must be a Parquet path, pandas.DataFrame, polars.DataFrame, "
        "or polars.LazyFrame."
    )


def _normalized_node_ids(node_ids: Sequence[object]) -> np.ndarray:
    if isinstance(node_ids, (str, bytes)):
        raise ValueError("node_ids must be a sequence of node IDs, not one string.")
    if any(value is None for value in node_ids):
        raise ValueError("node_ids must not contain null IDs.")
    values = np.asarray([str(value).strip() for value in node_ids], dtype=str)
    if values.ndim != 1:
        raise ValueError("node_ids must be a one-dimensional sequence.")
    if len(np.unique(values)) != len(values):
        raise ValueError("node_ids must be unique.")
    if any(not value for value in values):
        raise ValueError("node_ids must not contain empty IDs.")
    return values


def _selected_od_rows(
    lazy_frame: pl.LazyFrame,
    spec: NetworkSpec,
    extra_expressions: Sequence[pl.Expr] = (),
) -> pl.LazyFrame:
    """Select canonical OD columns after checking the source schema."""
    available = set(lazy_frame.collect_schema().names())
    required = {spec.origin, spec.destination, spec.weight}
    missing = sorted(required - available)
    if missing:
        raise ValueError("OD input is missing required columns: %s" % missing)
    return lazy_frame.select(
        [
            pl.col(spec.origin).cast(pl.String).str.strip_chars().alias("_origin"),
            pl.col(spec.destination)
            .cast(pl.String)
            .str.strip_chars()
            .alias("_destination"),
            pl.col(spec.weight).cast(pl.Float64, strict=False).alias("_weight"),
            *extra_expressions,
        ]
    )


def _invalid_od_condition() -> pl.Expr:
    """Return the conditions that cannot be represented in a flow network."""
    return (
        pl.col("_origin").is_null()
        | pl.col("_destination").is_null()
        | pl.col("_origin").eq("")
        | pl.col("_destination").eq("")
        | pl.col("_weight").is_null()
        | ~pl.col("_weight").is_finite()
        | (pl.col("_weight") < 0)
    )


def _valid_od_rows(selected: pl.LazyFrame) -> pl.LazyFrame:
    """Keep only rows which have a valid directed, non-negative flow."""
    return selected.filter(~_invalid_od_condition())


def _construction_provenance(
    provenance: Optional[Mapping[str, object]], metadata: NetworkMetadata
) -> Mapping[str, object]:
    """Record the accounting of the first lossy network representation."""
    details = {
        "input_edge_count": metadata.input_edge_count,
        "represented_edge_count": metadata.represented_edge_count,
        "input_weight": metadata.input_weight,
        "represented_weight": metadata.represented_weight,
        "dropped_self_loop_weight": metadata.dropped_self_loop_weight,
        "self_loops": metadata.self_loops,
    }
    result = dict(provenance or {})
    prior_history = list(result.get("history", ()))
    if not prior_history:
        prior_history = [
            {"kind": key, **value}
            for key, value in result.items()
            if key in {"temporal", "symmetrization", "spatial"}
        ]
    result["construction"] = details
    result["history"] = [{"kind": "construction", **details}, *prior_history]
    return result


def build_network(
    data: ODSource,
    *,
    spec: Optional[NetworkSpec] = None,
    node_ids: Optional[Sequence[object]] = None,
    node_index: Optional[NodeIndex] = None,
    provenance: Optional[Mapping[str, object]] = None,
) -> SparseMobilityNetwork:
    """Build a directed, weighted CSR network from processed OD observations.

    Repeated OD rows -- including rows separated by time, activity, or social
    dimensions -- are summed before the matrix is constructed. This is the
    only safe default for a static flow network.

    Parameters
    ----------
    data
        A processed OD Parquet path, a pandas/Polars DataFrame, or a Polars
        LazyFrame. It must contain the columns named in ``spec``.
    spec
        Construction rules. The MVP supports directed ``sum`` aggregation and
        retaining or dropping self-loops.
    node_ids
        Optional complete, ordered node universe. It preserves the same row
        and column positions across independently built networks and includes
        nodes with no observed flows. With ``None``, observed endpoints are
        sorted lexicographically to create a deterministic index.
    node_index
        Optional :class:`NodeIndex` replacing ``node_ids``. It associates the
        matrix with a zoning identifier/version and must not be combined with
        ``node_ids``.
    provenance
        Optional audit context carried into the immutable network result.

    Returns
    -------
    SparseMobilityNetwork
        Canonical CSR matrix, node IDs, and an audit trail. Missing or
        non-finite OD values are rejected rather than silently becoming a
        missing flow.
    """
    spec = NetworkSpec() if spec is None else spec
    if not isinstance(spec, NetworkSpec):
        raise TypeError("spec must be a NetworkSpec instance.")
    if node_ids is not None and node_index is not None:
        raise ValueError("Pass either node_ids or node_index, not both.")
    if node_index is not None:
        if not isinstance(node_index, NodeIndex):
            raise TypeError("node_index must be a NodeIndex instance.")
        node_ids = node_index.node_ids

    lazy_frame = _as_lazy_frame(data)
    selected = _selected_od_rows(lazy_frame, spec)
    invalid_rows = selected.filter(_invalid_od_condition()).select(
        pl.len().alias("count")
    )
    edge_query = (
        _valid_od_rows(selected)
        .group_by("_origin", "_destination")
        .agg(pl.col("_weight").sum())
    )
    invalid, edges = pl.collect_all([invalid_rows, edge_query])
    invalid_count = int(invalid.item(0, "count"))
    if invalid_count:
        raise ValueError(
            "%d OD rows have null, non-finite, negative, or invalid "
            "endpoint/weight values." % invalid_count
        )
    if edges.is_empty():
        if node_ids is None:
            raise ValueError("OD input contains no valid flow rows and no node_ids.")
        node_array = _normalized_node_ids(node_ids)
        matrix = coo_array((len(node_array), len(node_array)), dtype=np.float64).tocsr()
        metadata = NetworkMetadata(
            weight=spec.weight,
            directed=True,
            aggregation="sum",
            self_loops=spec.self_loops,
            node_universe="provided",
            input_edge_count=0,
            represented_edge_count=0,
            input_weight=0.0,
            represented_weight=0.0,
            dropped_self_loop_weight=0.0,
        )
        return SparseMobilityNetwork(
            matrix,
            node_array,
            metadata,
            _construction_provenance(provenance, metadata),
            node_index,
        )

    input_edge_count = edges.height
    input_weight = float(edges.get_column("_weight").sum())
    observed_nodes = (
        pl.concat(
            [
                edges.select(pl.col("_origin").alias("_node")),
                edges.select(pl.col("_destination").alias("_node")),
            ]
        )
        .unique()
        .sort("_node")
        .get_column("_node")
        .to_list()
    )
    loops = edges.filter(pl.col("_origin") == pl.col("_destination"))
    dropped_self_loop_weight = 0.0
    if spec.self_loops == "drop":
        dropped_self_loop_weight = float(loops.get_column("_weight").sum() or 0.0)
        edges = edges.filter(pl.col("_origin") != pl.col("_destination"))

    if node_ids is None:
        node_array = _normalized_node_ids(observed_nodes)
        node_universe = "observed"
    else:
        node_array = _normalized_node_ids(node_ids)
        node_universe = "provided"
        missing_observed = sorted(set(observed_nodes) - set(node_array))
        if missing_observed:
            raise ValueError(
                "node_ids does not cover every OD endpoint; examples: %s"
                % missing_observed[:5]
            )

    index_frame = pl.DataFrame(
        {"_node": node_array.tolist(), "_index": np.arange(len(node_array))}
    )
    indexed = (
        edges.join(
            index_frame.rename({"_node": "_origin", "_index": "_row"}),
            on="_origin",
            how="left",
        )
        .join(
            index_frame.rename({"_node": "_destination", "_index": "_column"}),
            on="_destination",
            how="left",
        )
    )
    unknown = indexed.filter(pl.col("_row").is_null() | pl.col("_column").is_null())
    if not unknown.is_empty():
        sample = unknown.select("_origin", "_destination").head(5).to_dicts()
        raise ValueError(
            "node_ids does not cover every OD endpoint; examples: %s" % sample
        )

    matrix = coo_array(
        (
            indexed.get_column("_weight").to_numpy(),
            (
                indexed.get_column("_row").to_numpy(),
                indexed.get_column("_column").to_numpy(),
            ),
        ),
        shape=(len(node_array), len(node_array)),
        dtype=np.float64,
    ).tocsr()
    matrix.sum_duplicates()
    matrix.eliminate_zeros()
    represented_weight = float(matrix.sum())
    metadata = NetworkMetadata(
        weight=spec.weight,
        directed=True,
        aggregation="sum",
        self_loops=spec.self_loops,
        node_universe=node_universe,
        input_edge_count=input_edge_count,
        represented_edge_count=matrix.nnz,
        input_weight=input_weight,
        represented_weight=represented_weight,
        dropped_self_loop_weight=dropped_self_loop_weight,
    )
    return SparseMobilityNetwork(
        matrix,
        node_array,
        metadata,
        _construction_provenance(provenance, metadata),
        node_index,
    )
