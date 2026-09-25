"""Verified spatial aggregation for OD tables and sparse networks."""

from collections.abc import Mapping as MappingABC
from dataclasses import replace
from pathlib import Path
from typing import Mapping, Optional, Sequence, Union

import numpy as np
import pandas as pd
import polars as pl
from scipy.sparse import coo_array

from .builder import (
    ODSource,
    _as_lazy_frame,
    _invalid_od_condition,
    _normalized_node_ids,
    _pandas_to_polars,
    _selected_od_rows,
    _string_identifier_expression,
    build_network,
)
from .model import (
    NodeIndex,
    NetworkMetadata,
    NetworkSpec,
    SparseMobilityNetwork,
    _append_provenance,
    _missing_node_id,
)


MappingSource = Union[Mapping[object, object], pd.DataFrame, pl.DataFrame, Path, str]


def _mapping_table(
    mapping: MappingSource,
    source_column: str,
    target_column: str,
) -> pl.DataFrame:
    """Return a validated one-source-to-one-target spatial correspondence."""
    if isinstance(mapping, MappingABC):
        frame = pl.DataFrame(
            {
                source_column: [
                    None if _missing_node_id(value) else str(value).strip()
                    for value in mapping.keys()
                ],
                target_column: [
                    None if _missing_node_id(value) else str(value).strip()
                    for value in mapping.values()
                ],
            }
        )
    elif isinstance(mapping, pl.DataFrame):
        frame = mapping
    elif isinstance(mapping, pd.DataFrame):
        frame = _pandas_to_polars(mapping)
    elif isinstance(mapping, (str, Path)):
        path = Path(mapping)
        if path.suffix.lower() != ".parquet":
            raise ValueError("Mapping paths must be Parquet files.")
        frame = pl.read_parquet(path)
    else:
        raise TypeError(
            "mapping must be a dict-like object, pandas/Polars DataFrame, "
            "or Parquet path."
        )

    available = set(frame.columns)
    required = {source_column, target_column}
    missing = sorted(required - available)
    if missing:
        raise ValueError("Spatial mapping is missing required columns: %s" % missing)
    table = frame.select(
        _string_identifier_expression(source_column, frame.schema[source_column]).alias("_source"),
        _string_identifier_expression(target_column, frame.schema[target_column]).alias("_target"),
    )
    invalid = table.filter(
        pl.col("_source").is_null()
        | pl.col("_target").is_null()
        | pl.col("_source").eq("")
        | pl.col("_target").eq("")
    )
    if not invalid.is_empty():
        raise ValueError("Spatial mapping contains null or empty source/target IDs.")
    duplicate_sources = table.group_by("_source").len().filter(pl.col("len") > 1)
    if not duplicate_sources.is_empty():
        examples = duplicate_sources.head(5).get_column("_source").to_list()
        raise ValueError(
            "Spatial mapping must map each source node once; duplicates include: %s"
            % examples
        )
    return table


def _projection(
    network: SparseMobilityNetwork,
    mapping: MappingSource,
    source_column: str,
    target_column: str,
    target_node_ids: Optional[Sequence[object]],
):
    """Build the source-to-target projection matrix and mapping diagnostics."""
    table = _mapping_table(mapping, source_column, target_column)
    mapping_dict = dict(
        zip(
            table.get_column("_source").to_list(),
            table.get_column("_target").to_list(),
        )
    )
    source_ids = network.node_ids.tolist()
    missing = [node_id for node_id in source_ids if node_id not in mapping_dict]
    if missing:
        raise ValueError(
            "Spatial mapping does not cover every network node; examples: %s"
            % missing[:5]
        )
    mapped_targets = [mapping_dict[node_id] for node_id in source_ids]
    if target_node_ids is None:
        target_ids = _normalized_node_ids(sorted(set(mapped_targets)))
    else:
        target_ids = _normalized_node_ids(target_node_ids)
        unknown = sorted(set(mapped_targets) - set(target_ids))
        if unknown:
            raise ValueError(
                "target_node_ids does not cover mapping targets; examples: %s"
                % unknown[:5]
            )
    target_positions = {node_id: index for index, node_id in enumerate(target_ids)}
    projection = coo_array(
        (
            np.ones(len(source_ids), dtype=np.float64),
            (
                np.arange(len(source_ids), dtype=np.int64),
                np.asarray(
                    [target_positions[target] for target in mapped_targets],
                    dtype=np.int64,
                ),
            ),
        ),
        shape=(len(source_ids), len(target_ids)),
        dtype=np.float64,
    ).tocsr()
    return projection, target_ids, table.height


def _spatial_provenance(
    *,
    method: str,
    mapping_rows: int,
    source_network: SparseMobilityNetwork,
    target_matrix,
    target_node_count: int,
    dropped_target_self_loop_weight: float,
) -> Mapping[str, object]:
    """Create auditable accounting for a many-to-one spatial aggregation."""
    source_self_loop_weight = float(source_network.adjacency.diagonal().sum())
    target_self_loop_weight = float(target_matrix.diagonal().sum())
    target_weight = (
        float(target_matrix.sum())
        if source_network.metadata.directed
        else float((target_matrix.sum() + target_self_loop_weight) / 2)
    )
    return {
        "spatial": {
            "method": method,
            "mapping_row_count": mapping_rows,
            "source_node_count": source_network.number_of_nodes,
            "target_node_count": target_node_count,
            "source_weight": source_network.total_weight,
            "target_weight_before_target_loop_policy": target_weight,
            "source_self_loop_weight": source_self_loop_weight,
            "target_self_loop_weight_before_target_loop_policy": (
                target_self_loop_weight
            ),
            "internalized_weight": target_self_loop_weight - source_self_loop_weight,
            "dropped_target_self_loop_weight": dropped_target_self_loop_weight,
        }
    }


def _apply_target_loop_policy(matrix, self_loops: str):
    if self_loops not in {"keep", "drop"}:
        raise ValueError("self_loops must be either 'keep' or 'drop'.")
    matrix = matrix.tocsr(copy=True)
    dropped_weight = 0.0
    if self_loops == "drop":
        dropped_weight = float(matrix.diagonal().sum())
        matrix.setdiag(0)
        matrix.eliminate_zeros()
    return matrix, dropped_weight


def aggregate_network(
    network: SparseMobilityNetwork,
    mapping: MappingSource,
    *,
    source_column: str = "source_id",
    target_column: str = "target_id",
    target_node_ids: Optional[Sequence[object]] = None,
    target_node_index: Optional[NodeIndex] = None,
    self_loops: str = "keep",
) -> SparseMobilityNetwork:
    """Aggregate a CSR network with the exact projection ``P.T @ A @ P``.

    The mapping must assign every source node to exactly one target node.
    Many-to-one mappings turn between-source flows into target self-loops;
    these are retained by default and reported as ``internalized_weight`` in
    ``network.audit()['provenance']['spatial']``.  Set ``self_loops='drop'``
    only when that loss is intentional and auditable.
    """
    if not isinstance(network, SparseMobilityNetwork):
        raise TypeError("network must be a SparseMobilityNetwork.")
    if target_node_ids is not None and target_node_index is not None:
        raise ValueError("Pass either target_node_ids or target_node_index, not both.")
    if target_node_index is not None:
        if not isinstance(target_node_index, NodeIndex):
            raise TypeError("target_node_index must be a NodeIndex instance.")
        target_node_ids = target_node_index.node_ids
    projection, target_ids, mapping_rows = _projection(
        network, mapping, source_column, target_column, target_node_ids
    )
    full_target = (projection.T @ network.adjacency @ projection).tocsr()
    full_target.sum_duplicates()
    full_target.eliminate_zeros()
    if not network.metadata.directed:
        original_loops = np.bincount(
            projection.indices,
            weights=network.adjacency.diagonal(),
            minlength=len(target_ids),
        )
        # Each internalized undirected edge lands twice on the diagonal.
        full_target.setdiag((full_target.diagonal() + original_loops) / 2)
        full_target.eliminate_zeros()
    projected_weight = (
        float(full_target.sum())
        if network.metadata.directed
        else float((full_target.sum() + full_target.diagonal().sum()) / 2)
    )
    if not np.isclose(
        projected_weight, network.total_weight, rtol=1e-12, atol=1e-9
    ):
        raise RuntimeError("Spatial aggregation did not preserve total source flow.")
    target_matrix, dropped_weight = _apply_target_loop_policy(full_target, self_loops)
    represented_count = (
        target_matrix.nnz
        if network.metadata.directed
        else int(
            (target_matrix.nnz + np.count_nonzero(target_matrix.diagonal())) // 2
        )
    )
    represented_weight = (
        float(target_matrix.sum())
        if network.metadata.directed
        else float((target_matrix.sum() + target_matrix.diagonal().sum()) / 2)
    )
    metadata = NetworkMetadata(
        weight=network.metadata.weight,
        directed=network.metadata.directed,
        aggregation=network.metadata.aggregation,
        self_loops=self_loops,
        node_universe="provided" if target_node_ids is not None else "mapped",
        input_edge_count=network.number_of_edges,
        represented_edge_count=represented_count,
        input_weight=network.total_weight,
        represented_weight=represented_weight,
        dropped_self_loop_weight=dropped_weight,
        weight_normalization=network.metadata.weight_normalization,
    )
    spatial = _spatial_provenance(
        method="sparse_projection",
        mapping_rows=mapping_rows,
        source_network=network,
        target_matrix=full_target,
        target_node_count=len(target_ids),
        dropped_target_self_loop_weight=dropped_weight,
    )["spatial"]
    provenance = _append_provenance(
        network.provenance, "spatial", spatial
    )
    return SparseMobilityNetwork(
        target_matrix,
        target_ids,
        metadata,
        provenance,
        target_node_index,
    )


def aggregate_od_network(
    data: ODSource,
    mapping: MappingSource,
    *,
    spec: Optional[NetworkSpec] = None,
    source_column: str = "source_id",
    target_column: str = "target_id",
    target_node_ids: Optional[Sequence[object]] = None,
    target_node_index: Optional[NodeIndex] = None,
    self_loops: str = "keep",
) -> SparseMobilityNetwork:
    """Aggregate processed OD data spatially in Polars before CSR creation.

    This is the preferred route when the OD table is still available: joins
    and aggregation happen in the tabular engine, avoiding an intermediate
    fine-resolution adjacency matrix.  It has the same mapping and flow-audit
    guarantees as :func:`aggregate_network`.
    """
    spec = NetworkSpec() if spec is None else spec
    if not isinstance(spec, NetworkSpec):
        raise TypeError("spec must be a NetworkSpec instance.")
    if self_loops not in {"keep", "drop"}:
        raise ValueError("self_loops must be either 'keep' or 'drop'.")
    if target_node_ids is not None and target_node_index is not None:
        raise ValueError("Pass either target_node_ids or target_node_index, not both.")
    if target_node_index is not None:
        if not isinstance(target_node_index, NodeIndex):
            raise TypeError("target_node_index must be a NodeIndex instance.")
        target_node_ids = target_node_index.node_ids
    source = _as_lazy_frame(data)
    selected = _selected_od_rows(source, spec)
    table = _mapping_table(mapping, source_column, target_column)
    origin_mapping = table.rename({"_source": "_origin", "_target": "_mapped_origin"})
    destination_mapping = table.rename(
        {"_source": "_destination", "_target": "_mapped_destination"}
    )
    mapped = selected.join(origin_mapping.lazy(), on="_origin", how="left").join(
        destination_mapping.lazy(), on="_destination", how="left"
    )
    invalid = mapped.filter(_invalid_od_condition()).select(pl.len().alias("count"))
    valid_source = mapped.filter(~_invalid_od_condition())
    unmapped = valid_source.filter(
        pl.col("_mapped_origin").is_null() | pl.col("_mapped_destination").is_null()
    ).select(pl.len().alias("count"))
    valid = (
        valid_source.filter(pl.col("_origin") != pl.col("_destination"))
        if spec.self_loops == "drop"
        else valid_source
    )
    statistics = valid.select(
        [
            pl.col("_weight").sum().alias("source_weight"),
            pl.when(pl.col("_origin") == pl.col("_destination"))
            .then(pl.col("_weight"))
            .otherwise(0.0)
            .sum()
            .alias("source_self_loop_weight"),
            pl.when(pl.col("_mapped_origin") == pl.col("_mapped_destination"))
            .then(pl.col("_weight"))
            .otherwise(0.0)
            .sum()
            .alias("target_self_loop_weight"),
        ]
    )
    source_loops = valid_source.filter(
        pl.col("_origin") == pl.col("_destination")
    ).select(pl.col("_weight").sum().alias("weight"))
    mapped_nodes = pl.concat(
        [
            valid_source.select(pl.col("_mapped_origin").alias("node")),
            valid_source.select(pl.col("_mapped_destination").alias("node")),
        ]
    ).unique().sort("node")
    network_ready = valid.select(
        pl.col("_mapped_origin").alias(spec.origin),
        pl.col("_mapped_destination").alias(spec.destination),
        pl.col("_weight").alias(spec.weight),
    )
    # Build target edges during the diagnostics collection. Passing
    # ``network_ready`` lazily to build_network would scan the OD source again.
    target_edges = network_ready.group_by(spec.origin, spec.destination).agg(
        pl.col(spec.weight).sum()
    )
    (
        invalid_frame,
        unmapped_frame,
        stats,
        source_loops_frame,
        mapped_nodes_frame,
        target_edges_frame,
    ) = pl.collect_all(
        [invalid, unmapped, statistics, source_loops, mapped_nodes, target_edges]
    )
    invalid_count = int(invalid_frame.item(0, "count"))
    if invalid_count:
        raise ValueError(
            "%d OD rows have null, non-finite, negative, or invalid "
            "endpoint/weight values." % invalid_count
        )
    unmapped_count = int(unmapped_frame.item(0, "count"))
    if unmapped_count:
        raise ValueError(
            "%d OD rows cannot be mapped to the target zoning." % unmapped_count
        )

    target_spec = NetworkSpec(
        origin=spec.origin,
        destination=spec.destination,
        weight=spec.weight,
        self_loops=self_loops,
    )
    inferred_target_ids = mapped_nodes_frame.get_column("node").to_list()
    if target_node_ids is not None:
        unknown_targets = sorted(
            set(inferred_target_ids) - set(_normalized_node_ids(target_node_ids))
        )
        if unknown_targets:
            raise ValueError(
                "target_node_ids does not cover mapping targets; examples: %s"
                % unknown_targets[:5]
            )
    network = build_network(
        target_edges_frame,
        spec=target_spec,
        node_ids=(
            None
            if target_node_index is not None
            else (target_node_ids if target_node_ids is not None else inferred_target_ids)
        ),
        node_index=target_node_index,
    )
    source_weight = float(stats.item(0, "source_weight") or 0.0)
    target_self_loop_weight = float(stats.item(0, "target_self_loop_weight") or 0.0)
    source_self_loop_weight = float(stats.item(0, "source_self_loop_weight") or 0.0)
    dropped_source_self_loop_weight = (
        float(source_loops_frame.item(0, "weight") or 0.0)
        if spec.self_loops == "drop"
        else 0.0
    )
    spatial = {
        "method": "od_polars",
        "mapping_row_count": table.height,
        "source_weight": source_weight,
        "target_weight_before_target_loop_policy": source_weight,
        "source_self_loop_weight": source_self_loop_weight,
        "dropped_source_self_loop_weight": dropped_source_self_loop_weight,
        "target_self_loop_weight_before_target_loop_policy": target_self_loop_weight,
        "internalized_weight": target_self_loop_weight - source_self_loop_weight,
        "dropped_target_self_loop_weight": network.metadata.dropped_self_loop_weight,
    }
    provenance = _append_provenance(network.provenance, "spatial", spatial)
    return SparseMobilityNetwork(
        network.adjacency,
        network.node_ids,
        (
            replace(network.metadata, node_universe="mapped")
            if target_node_ids is None
            else network.metadata
        ),
        provenance,
        network.node_index,
    )
