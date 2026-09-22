"""Explicit representation changes for canonical mobility networks."""

from __future__ import annotations

from typing import Literal

from scipy.sparse import triu

from .model import NetworkMetadata, SparseMobilityNetwork, _append_provenance


SymmetrizationMethod = Literal["sum", "mean", "max", "mutual"]


def _logical_weight(matrix) -> float:
    """Sum one triangle of a symmetric adjacency, including self-loops."""
    return float(triu(matrix, format="csr").sum())


def symmetrize_network(
    network: SparseMobilityNetwork,
    *,
    method: SymmetrizationMethod = "sum",
) -> SparseMobilityNetwork:
    """Turn a directed OD network into an auditable undirected network.

    The returned adjacency is symmetric, with one logical undirected edge per
    unordered node pair. The explicit rule determines its edge weight:

    - ``sum``: total bilateral OD flow, ``A[i, j] + A[j, i]``;
    - ``mean``: mean bilateral OD flow, treating a missing direction as zero;
    - ``max``: strongest direction;
    - ``mutual``: weakest direction, removing non-reciprocal pairs.

    Self-loops are preserved once under every rule. Provenance records both
    logical edge weight and stored symmetric-matrix weight, avoiding accidental
    double counting of off-diagonal edges.
    """
    if not isinstance(network, SparseMobilityNetwork):
        raise TypeError("network must be a SparseMobilityNetwork instance.")
    if not network.metadata.directed:
        raise ValueError(
            "symmetrize_network requires a directed input network."
        )
    if method not in {"sum", "mean", "max", "mutual"}:
        raise ValueError(
            "method must be one of 'sum', 'mean', 'max', or 'mutual'."
        )

    matrix = network.adjacency
    transpose = matrix.T.tocsr()
    if method == "sum":
        result = (matrix + transpose).tocsr()
        result.setdiag(matrix.diagonal())
    elif method == "mean":
        result = ((matrix + transpose) / 2.0).tocsr()
    elif method == "max":
        result = matrix.maximum(transpose).tocsr()
    else:
        result = matrix.minimum(transpose).tocsr()
    result.sum_duplicates()
    result.eliminate_zeros()

    logical_weight = _logical_weight(result)
    logical_edge_count = triu(result, format="csr").nnz
    metadata = NetworkMetadata(
        weight=network.metadata.weight,
        directed=False,
        aggregation="symmetrize_%s" % method,
        self_loops=network.metadata.self_loops,
        node_universe=network.metadata.node_universe,
        input_edge_count=network.number_of_edges,
        represented_edge_count=logical_edge_count,
        input_weight=network.total_weight,
        represented_weight=logical_weight,
        dropped_self_loop_weight=0.0,
        weight_normalization=network.metadata.weight_normalization,
    )
    provenance = _append_provenance(network.provenance, "symmetrization", {
        "method": method,
        "input_directed": True,
        "input_weight": network.total_weight,
        "logical_undirected_weight": logical_weight,
        "stored_symmetric_matrix_weight": float(result.sum()),
    })
    return SparseMobilityNetwork(
        result,
        network.node_ids,
        metadata,
        provenance,
        network.node_index,
    )


__all__ = ["SymmetrizationMethod", "symmetrize_network"]
