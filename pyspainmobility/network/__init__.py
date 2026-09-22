"""Network-science representations of processed mobility OD data.

The canonical representation is a SciPy CSR adjacency matrix paired with a
stable, explicit node index. Optional packages are exposed through adapters
in :mod:`pyspainmobility.network.integrations`.
"""

from .builder import build_network
from .metrics import (
    NetworkComparison,
    compare_networks,
    destination_similarity,
    edge_changes,
    node_strengths,
)
from .model import (
    CommunityPartition,
    NodeIndex,
    NetworkMetadata,
    NetworkSpec,
    SparseMobilityNetwork,
)
from .spatial import aggregate_network, aggregate_od_network
from .temporal import TemporalCoverage, TemporalMobilityNetwork, build_temporal_network
from .transforms import SymmetrizationMethod, symmetrize_network

__all__ = [
    "NetworkMetadata",
    "NetworkComparison",
    "CommunityPartition",
    "NodeIndex",
    "NetworkSpec",
    "SparseMobilityNetwork",
    "SymmetrizationMethod",
    "build_network",
    "compare_networks",
    "destination_similarity",
    "edge_changes",
    "node_strengths",
    "aggregate_network",
    "aggregate_od_network",
    "TemporalCoverage",
    "TemporalMobilityNetwork",
    "build_temporal_network",
    "symmetrize_network",
]
