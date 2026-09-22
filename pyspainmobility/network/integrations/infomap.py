"""Optional Infomap integration for canonical sparse mobility networks."""

from __future__ import annotations

import hashlib
from typing import Any, Dict, Tuple

import numpy as np

from ..model import CommunityPartition, SparseMobilityNetwork


def _load_infomap() -> Any:
    """Import Infomap only when this optional adapter is invoked."""
    try:
        import infomap
    except ImportError as error:
        raise ImportError(
            "Infomap support requires the optional dependency. "
            "Install it with 'pip install pyspainmobility[infomap]'."
        ) from error
    return infomap


def _network_fingerprint(network: SparseMobilityNetwork) -> str:
    """Return a deterministic identity for the exact CSR adapter input."""
    matrix = network.adjacency
    digest = hashlib.sha256()
    digest.update(np.asarray(matrix.shape, dtype=np.int64).tobytes())
    for value in (
        str(network.metadata.directed),
        network.metadata.weight,
        network.metadata.weight_normalization or "",
        network.metadata.aggregation,
        network.node_index.zoning_id or "",
        network.node_index.zoning_version or "",
        *network.node_ids.tolist(),
    ):
        digest.update(value.encode("utf-8"))
        digest.update(b"\0")
    digest.update(np.asarray(matrix.indptr, dtype=np.int64).tobytes())
    digest.update(np.asarray(matrix.indices, dtype=np.int64).tobytes())
    digest.update(np.asarray(matrix.data, dtype=np.float64).tobytes())
    return digest.hexdigest()


def to_infomap(network: SparseMobilityNetwork) -> Any:
    """Create a weighted Infomap network directly from its CSR matrix.

    The adapter passes the canonical zone IDs as Infomap node names, including
    explicit isolates. No edge-table or NetworkX materialisation is involved.
    """
    if not isinstance(network, SparseMobilityNetwork):
        raise TypeError("network must be a SparseMobilityNetwork instance.")
    infomap = _load_infomap()
    return infomap.Network.from_scipy_sparse_matrix(
        network.adjacency,
        directed=network.metadata.directed,
        weighted=True,
        node_ids=network.node_ids.tolist(),
    )


def _external_node_id(names: Dict[object, str], internal_node_id: object) -> str:
    """Translate an Infomap-internal node ID back to the canonical zone ID."""
    return str(names.get(internal_node_id, internal_node_id))


def _validate_complete_partition(
    network: SparseMobilityNetwork, assignments: Dict[str, int]
) -> None:
    expected_ids = set(network.node_ids.tolist())
    received_ids = set(assignments)
    if expected_ids != received_ids:
        missing = sorted(expected_ids - received_ids)
        unexpected = sorted(received_ids - expected_ids)
        raise RuntimeError(
            "Infomap did not return a partition covering the node index "
            "(missing=%r, unexpected=%r)." % (missing, unexpected)
        )


def run_infomap(
    network: SparseMobilityNetwork,
    *,
    seed: int = 123,
    num_trials: int = 1,
    two_level: bool = False,
    markov_time: float | None = None,
    **options: object,
) -> CommunityPartition:
    """Run Infomap and return a backend-neutral, auditable partition.

    OD weights are interpreted by Infomap as edge weights for its random-walk
    flow model; they are not themselves the resulting flow values.
    ``seed`` and ``num_trials`` are retained in the returned provenance to make
    stochastic optimisation repeatable. The network direction is fixed by the
    canonical mobility contract and cannot be overridden here.
    """
    forbidden = {"directed", "flow_model", "args", "options"} & set(options)
    if forbidden:
        if "directed" in forbidden:
            raise ValueError(
                "directed cannot be overridden: it is fixed by the network's "
                "stored direction contract."
            )
        raise ValueError(
            "Infomap direction/flow-model options cannot override the network "
            "contract: %s" % sorted(forbidden)
        )
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise TypeError("seed must be an integer.")
    if isinstance(num_trials, bool) or not isinstance(num_trials, int) or num_trials < 1:
        raise ValueError("num_trials must be a positive integer.")
    if markov_time is not None and (
        isinstance(markov_time, bool)
        or not isinstance(markov_time, (int, float))
        or not np.isfinite(markov_time)
        or markov_time <= 0
    ):
        raise ValueError(
            "markov_time must be a positive number when provided."
        )

    infomap = _load_infomap()
    run_options: Dict[str, object] = {
        "seed": seed,
        "num_trials": num_trials,
        "two_level": two_level,
        **options,
    }
    if markov_time is not None:
        run_options["markov_time"] = float(markov_time)

    result = infomap.run(to_infomap(network), **run_options)
    names = result.names
    assignments = {
        _external_node_id(names, internal_id): int(module)
        for internal_id, module in result.modules().items()
    }
    hierarchy: Dict[str, Tuple[int, ...]] = {
        _external_node_id(names, internal_id): tuple(
            int(item) for item in path
        )
        for internal_id, path in result.multilevel_modules().items()
    }
    _validate_complete_partition(network, assignments)
    if set(hierarchy) != set(assignments):
        raise RuntimeError(
            "Infomap did not return a complete multilevel partition."
        )

    return CommunityPartition(
        node_index=network.node_index,
        assignments=assignments,
        hierarchy=hierarchy,
        algorithm="infomap",
        algorithm_version=getattr(infomap, "__version__", None),
        parameters={"directed": network.metadata.directed, **run_options},
        network_fingerprint=_network_fingerprint(network),
        algorithm_metrics={
            "codelength": float(result.codelength),
            "num_top_modules": int(result.num_top_modules),
        },
    )


__all__ = ["run_infomap", "to_infomap"]
