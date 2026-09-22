"""NetworkX adapter; NetworkX is intentionally not the canonical backend."""

from typing import Any

from ..model import SparseMobilityNetwork


def to_networkx(
    network: SparseMobilityNetwork, *, edge_attribute: str = "weight"
) -> Any:
    """Convert a network to a weighted NetworkX graph preserving direction.

    NetworkX is imported only here, so installing pySpainMobility for sparse
    network work does not pull in a graph-object dependency. Install the
    optional adapter with ``pip install pyspainmobility[network]``.
    """
    try:
        import networkx as nx
    except ImportError as exc:
        raise ImportError(
            "to_networkx requires NetworkX. Install it with "
            "`pip install pyspainmobility[network]`."
        ) from exc

    graph_type = nx.DiGraph if network.metadata.directed else nx.Graph
    graph = nx.from_scipy_sparse_array(
        network.adjacency,
        create_using=graph_type,
        edge_attribute=edge_attribute,
    )
    graph = nx.relabel_nodes(
        graph,
        {index: node_id for index, node_id in enumerate(network.node_ids)},
    )
    graph.graph["pyspainmobility_audit"] = network.audit()
    return graph
