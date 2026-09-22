"""Sparse metrics and reproducible comparisons for mobility networks."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional, Tuple

import numpy as np
import polars as pl
from scipy.sparse import diags, triu

from .model import NodeIndex, SparseMobilityNetwork


@dataclass(frozen=True)
class NetworkComparison:
    """Summary of a pairwise comparison on one aligned node index.

    ``flow_increase`` and ``flow_decrease`` measure the total positive and
    negative changes in edge weights. They include changes on persistent edges
    as well as edges that appeared or disappeared.
    """

    node_index: NodeIndex
    weight: str
    weight_normalization: Optional[str]
    left_label: Optional[str]
    right_label: Optional[str]
    left_edge_count: int
    right_edge_count: int
    shared_edge_count: int
    added_edge_count: int
    removed_edge_count: int
    edge_jaccard: float
    weighted_jaccard: float
    cosine_similarity: float
    left_weight: float
    right_weight: float
    shared_weight: float
    union_weight: float
    flow_increase: float
    flow_decrease: float

    @property
    def edge_turnover(self) -> float:
        """Fraction of the union edge set not shared by both networks."""
        return 1.0 - self.edge_jaccard

    def audit(self) -> dict[str, object]:
        """Return a serialisable record of all comparison values."""
        result = asdict(self)
        result["node_index"] = self.node_index.describe()
        result["edge_turnover"] = self.edge_turnover
        return result


def _aligned_pair(
    left: SparseMobilityNetwork, right: SparseMobilityNetwork
) -> Tuple[SparseMobilityNetwork, SparseMobilityNetwork]:
    """Return networks with exactly matching node identities and ordering."""
    if not isinstance(left, SparseMobilityNetwork):
        raise TypeError("left must be a SparseMobilityNetwork instance.")
    if not isinstance(right, SparseMobilityNetwork):
        raise TypeError("right must be a SparseMobilityNetwork instance.")
    if left.metadata.directed != right.metadata.directed:
        raise ValueError("Cannot compare directed and undirected networks.")
    if left.metadata.weight != right.metadata.weight:
        raise ValueError("Cannot compare networks with different weight fields.")
    if left.metadata.weight_normalization != right.metadata.weight_normalization:
        raise ValueError("Cannot compare networks with different weight normalization.")
    if left.node_index is right.node_index:
        return left, right
    if (
        left.node_index.zoning_id == right.node_index.zoning_id
        and left.node_index.zoning_version == right.node_index.zoning_version
        and np.array_equal(left.node_ids, right.node_ids)
    ):
        return left, right
    return left, right.align_to(left.node_index)


def _comparison_matrix(network: SparseMobilityNetwork):
    """Return one sparse entry per logical edge for aggregate comparison."""
    if network.metadata.directed:
        return network.adjacency
    return triu(network.adjacency, format="csr")


def _strength_arrays(
    network: SparseMobilityNetwork,
) -> Tuple[np.ndarray, np.ndarray]:
    """Compute in/out strengths without densifying the matrix."""
    matrix = network.adjacency
    out_strength = np.asarray(matrix.sum(axis=1)).ravel()
    in_strength = np.asarray(matrix.sum(axis=0)).ravel()
    return out_strength, in_strength


def _row_scales(matrix) -> np.ndarray:
    """Return one non-zero scaling factor per CSR row without densifying it."""
    scales = np.zeros(matrix.shape[0], dtype=np.float64)
    for row in range(matrix.shape[0]):
        values = matrix.data[matrix.indptr[row] : matrix.indptr[row + 1]]
        if values.size:
            scales[row] = float(np.max(values))
    return scales


def _stable_row_cosine(left_matrix, right_matrix) -> np.ndarray:
    """Cosine per CSR row, stable for both very large and tiny weights."""
    left_scales = _row_scales(left_matrix)
    right_scales = _row_scales(right_matrix)
    left_active = left_scales > 0
    right_active = right_scales > 0
    left_normalized = diags(
        np.divide(1.0, left_scales, out=np.ones_like(left_scales), where=left_active)
    ) @ left_matrix
    right_normalized = diags(
        np.divide(1.0, right_scales, out=np.ones_like(right_scales), where=right_active)
    ) @ right_matrix
    dot = np.asarray(left_normalized.multiply(right_normalized).sum(axis=1)).ravel()
    left_norm = np.sqrt(
        np.asarray(left_normalized.multiply(left_normalized).sum(axis=1)).ravel()
    )
    right_norm = np.sqrt(
        np.asarray(right_normalized.multiply(right_normalized).sum(axis=1)).ravel()
    )
    similarity = np.zeros(left_matrix.shape[0], dtype=np.float64)
    both_empty = ~left_active & ~right_active
    active_in_both = left_active & right_active
    similarity[both_empty] = 1.0
    similarity[active_in_both] = (
        dot[active_in_both] / (left_norm[active_in_both] * right_norm[active_in_both])
    )
    return similarity


def _stable_sparse_cosine(left_matrix, right_matrix) -> float:
    """Global sparse cosine after separate, scale-preserving normalisation."""
    if left_matrix.nnz == 0 and right_matrix.nnz == 0:
        return 1.0
    if left_matrix.nnz == 0 or right_matrix.nnz == 0:
        return 0.0
    left_scale = float(np.max(left_matrix.data))
    right_scale = float(np.max(right_matrix.data))
    left_normalized = left_matrix / left_scale
    right_normalized = right_matrix / right_scale
    denominator = float(
        np.sqrt(left_normalized.multiply(left_normalized).sum())
        * np.sqrt(right_normalized.multiply(right_normalized).sum())
    )
    return float(left_normalized.multiply(right_normalized).sum() / denominator)


def node_strengths(network: SparseMobilityNetwork) -> pl.DataFrame:
    """Return weighted row/column strengths for every node.

    For undirected networks ``total_strength`` counts a self-loop once, as one
    mobility flow incident on that zone. NetworkX's weighted graph degree
    counts an undirected self-loop twice; callers needing that graph-theoretic
    convention should use the NetworkX adapter explicitly.
    """
    if not isinstance(network, SparseMobilityNetwork):
        raise TypeError("network must be a SparseMobilityNetwork instance.")
    out_strength, in_strength = _strength_arrays(network)
    total_strength = (
        out_strength + in_strength
        if network.metadata.directed
        else out_strength
    )
    return pl.DataFrame(
        {
            "node_id": network.node_ids,
            "out_strength": out_strength,
            "in_strength": in_strength,
            "total_strength": total_strength,
        }
    )


def destination_similarity(
    left: SparseMobilityNetwork, right: SparseMobilityNetwork
) -> pl.DataFrame:
    """Return per-origin cosine similarity between destination flow profiles.

    A node with no outgoing flow in either network has similarity 1.0; a node
    that is inactive in only one network has similarity 0.0. This makes the
    convention explicit instead of silently excluding zero-strength origins.
    """
    left, right = _aligned_pair(left, right)
    left_matrix = left.adjacency
    right_matrix = right.adjacency
    similarity = _stable_row_cosine(left_matrix, right_matrix)
    return pl.DataFrame(
        {
            "node_id": left.node_ids,
            "destination_cosine_similarity": similarity,
        }
    )


def edge_changes(
    left: SparseMobilityNetwork, right: SparseMobilityNetwork
) -> pl.DataFrame:
    """Return added, removed, and weight-changed logical edges.

    The result contains only the union of non-zero edges, never a dense
    node-by-node table. ``delta_weight`` is ``right_weight - left_weight``.
    """
    left, right = _aligned_pair(left, right)
    keys = ["id_origin", "id_destination"]
    left_edges = left.to_edge_table(*keys, weight="left_weight", sort=False)
    right_edges = right.to_edge_table(*keys, weight="right_weight", sort=False)
    combined = pl.concat([left_edges, right_edges], how="diagonal_relaxed")
    return (
        combined.group_by(keys)
        .agg(
            pl.col("left_weight").fill_null(0.0).sum().alias("left_weight"),
            pl.col("right_weight").fill_null(0.0).sum().alias("right_weight"),
        )
        .with_columns(
            (pl.col("right_weight") - pl.col("left_weight")).alias(
                "delta_weight"
            )
        )
        .with_columns(
            pl.when(pl.col("left_weight") == 0)
            .then(pl.lit("added"))
            .when(pl.col("right_weight") == 0)
            .then(pl.lit("removed"))
            .when(pl.col("delta_weight") > 0)
            .then(pl.lit("increased"))
            .when(pl.col("delta_weight") < 0)
            .then(pl.lit("decreased"))
            .otherwise(pl.lit("unchanged"))
            .alias("change")
        )
        .sort(keys)
    )


def _ratio(numerator: float, denominator: float, both_empty: float) -> float:
    """Divide metrics with an explicit empty-network convention."""
    if denominator == 0:
        return both_empty
    return float(numerator / denominator)


def compare_networks(
    left: SparseMobilityNetwork,
    right: SparseMobilityNetwork,
    *,
    left_label: Optional[object] = None,
    right_label: Optional[object] = None,
) -> NetworkComparison:
    """Compare two aligned weighted networks without densifying."""
    left, right = _aligned_pair(left, right)
    left_matrix = _comparison_matrix(left)
    right_matrix = _comparison_matrix(right)
    shared_edge_count = left_matrix.astype(bool).multiply(
        right_matrix.astype(bool)
    ).nnz
    union = left_matrix.maximum(right_matrix)
    shared = left_matrix.minimum(right_matrix)
    left_weight = left.total_weight
    right_weight = right.total_weight
    shared_weight = float(shared.sum())
    union_weight = float(union.sum())
    cosine = _stable_sparse_cosine(left_matrix, right_matrix)
    edge_union_count = union.nnz
    return NetworkComparison(
        node_index=left.node_index,
        weight=left.metadata.weight,
        weight_normalization=left.metadata.weight_normalization,
        left_label=None if left_label is None else str(left_label),
        right_label=None if right_label is None else str(right_label),
        left_edge_count=left.number_of_edges,
        right_edge_count=right.number_of_edges,
        shared_edge_count=shared_edge_count,
        added_edge_count=right.number_of_edges - shared_edge_count,
        removed_edge_count=left.number_of_edges - shared_edge_count,
        edge_jaccard=_ratio(
            shared_edge_count, edge_union_count, both_empty=1.0
        ),
        weighted_jaccard=_ratio(shared_weight, union_weight, both_empty=1.0),
        cosine_similarity=cosine,
        left_weight=left_weight,
        right_weight=right_weight,
        shared_weight=shared_weight,
        union_weight=union_weight,
        flow_increase=float((right_matrix - left_matrix).maximum(0).sum()),
        flow_decrease=float((left_matrix - right_matrix).maximum(0).sum()),
    )


__all__ = [
    "NetworkComparison",
    "compare_networks",
    "destination_similarity",
    "edge_changes",
    "node_strengths",
]
