"""Data contracts for sparse mobility networks."""

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from types import MappingProxyType
from typing import Dict, Mapping, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd
import polars as pl
from scipy.sparse import csr_array, triu


class _ReadOnlyCSR(csr_array):
    """Prevent accidental changes to matrices held by cached networks."""

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_read_only", False) and name in {
            "data", "indices", "indptr", "_shape"
        }:
            raise AttributeError("Network adjacency is read-only.")
        super().__setattr__(name, value)

    def __setitem__(self, key: object, value: object) -> None:
        if getattr(self, "_read_only", False):
            raise TypeError("Network adjacency is read-only.")
        super().__setitem__(key, value)

    def __reduce__(self):
        return (
            _restore_read_only_csr,
            (self.data, self.indices, self.indptr, self.shape),
        )


def _read_only_csr(matrix: csr_array) -> csr_array:
    """Store arrays on immutable buffers, including against setflags(True)."""
    readonly = _ReadOnlyCSR(matrix, copy=False)
    readonly.data = np.frombuffer(readonly.data.tobytes(), dtype=readonly.data.dtype)
    readonly.indices = np.frombuffer(
        readonly.indices.tobytes(), dtype=readonly.indices.dtype
    )
    readonly.indptr = np.frombuffer(readonly.indptr.tobytes(), dtype=readonly.indptr.dtype)
    readonly._read_only = True
    return readonly


def _restore_read_only_csr(data, indices, indptr, shape) -> csr_array:
    matrix = csr_array((data, indices, indptr), shape=shape, copy=True)
    return _read_only_csr(matrix)


def _freeze_provenance(value: object) -> object:
    """Return an immutable, JSON-compatible audit value.

    Audit records cross public API boundaries and are commonly persisted with
    ``json.dumps``.  Normalising them here prevents a caller-owned NumPy array
    or nested list from changing a network after construction.
    """
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("Audit mapping keys must be strings.")
        return MappingProxyType(
            {key: _freeze_provenance(item) for key, item in value.items()}
        )
    if isinstance(value, np.ndarray):
        if value.ndim == 0:
            return _freeze_provenance(value.item())
        return tuple(_freeze_provenance(item) for item in value.tolist())
    if isinstance(value, np.generic):
        return _freeze_provenance(value.item())
    if isinstance(value, (frozenset, set)):
        return tuple(_freeze_provenance(item) for item in sorted(value, key=repr))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_provenance(item) for item in value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        if isinstance(value, float) and not np.isfinite(value):
            raise ValueError("Audit values must be finite.")
        return value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(
        "Audit values must be JSON-compatible scalars, mappings, or sequences; "
        "got %s." % type(value).__name__
    )


def _audit_value(value: object) -> object:
    """Return ordinary, serialisable containers from frozen provenance."""
    if isinstance(value, Mapping):
        return {key: _audit_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_audit_value(item) for item in value]
    return value


def _missing_node_id(value: object) -> bool:
    """Recognize scalar missing IDs before they are converted to strings."""
    try:
        if bool(pd.isna(value)):
            return True
    except (TypeError, ValueError):
        pass
    return isinstance(value, (float, np.floating)) and not np.isfinite(value)


def _append_provenance(
    previous: Optional[Mapping[str, object]], kind: str, details: Mapping[str, object]
) -> Dict[str, object]:
    """Preserve the latest operation and an ordered, extensible audit history."""
    result = dict(previous or {})
    history = list(result.get("history", ()))
    if not history:
        history = [
            {"kind": key, **_audit_value(value)}
            for key, value in result.items()
            if key in {"temporal", "symmetrization", "spatial"}
        ]
    history.append({"kind": kind, **details})
    result[kind] = dict(details)
    result["history"] = history
    return result


@dataclass(frozen=True)
class NodeIndex:
    """The scientific identity and order of a network's matrix nodes.

    ``node_ids[i]`` identifies row and column ``i``.  Zoning metadata is
    optional for backwards compatibility, but when provided it is checked
    before aligning or comparing networks.
    """

    node_ids: Sequence[object]
    zoning_id: Optional[str] = None
    zoning_version: Optional[str] = None

    def __post_init__(self) -> None:
        if isinstance(self.node_ids, (str, bytes)):
            raise ValueError("node_ids must be a sequence of node IDs, not one string.")
        source_ids = np.asarray(list(self.node_ids), dtype=object)
        if source_ids.ndim != 1:
            raise ValueError("node_ids must be one-dimensional.")
        if any(_missing_node_id(node_id) for node_id in source_ids):
            raise ValueError("node_ids must not contain null IDs.")
        node_ids = np.asarray(
            [str(node_id).strip() for node_id in source_ids], dtype=str
        )
        if len(np.unique(node_ids)) != len(node_ids):
            raise ValueError("node_ids must be unique.")
        if any(not node_id for node_id in node_ids):
            raise ValueError("node_ids must not contain empty IDs.")
        for name, value in (
            ("zoning_id", self.zoning_id),
            ("zoning_version", self.zoning_version),
        ):
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError("%s must be a non-empty string when provided." % name)
        node_ids = np.frombuffer(node_ids.tobytes(), dtype=node_ids.dtype)
        object.__setattr__(self, "node_ids", node_ids)

    def positions(self) -> Dict[str, int]:
        """Map node ID to the corresponding matrix row/column position."""
        return {node_id: index for index, node_id in enumerate(self.node_ids)}

    def assert_compatible(self, other: "NodeIndex") -> None:
        """Require equal zoning identity and exactly the same ordered nodes."""
        if not isinstance(other, NodeIndex):
            raise TypeError("other must be a NodeIndex.")
        if (
            self.zoning_id != other.zoning_id
            or self.zoning_version != other.zoning_version
        ):
            raise ValueError(
                "Node indexes have incompatible zoning metadata: %r/%r versus %r/%r."
                % (
                    self.zoning_id,
                    self.zoning_version,
                    other.zoning_id,
                    other.zoning_version,
                )
            )
        if not np.array_equal(self.node_ids, other.node_ids):
            raise ValueError("Node indexes have different node IDs or ordering.")

    def permutation_to(self, target: "NodeIndex") -> np.ndarray:
        """Return source positions ordered as ``target`` after compatibility checks."""
        if not isinstance(target, NodeIndex):
            raise TypeError("target must be a NodeIndex.")
        if (
            self.zoning_id != target.zoning_id
            or self.zoning_version != target.zoning_version
        ):
            raise ValueError(
                "Cannot align node indexes with different zoning metadata."
            )
        if len(self.node_ids) != len(target.node_ids) or set(self.node_ids) != set(
            target.node_ids
        ):
            raise ValueError("Cannot align node indexes with different node universes.")
        positions = self.positions()
        return np.asarray([positions[node_id] for node_id in target.node_ids])

    def describe(self) -> Dict[str, object]:
        """Return serialisable node-index identity metadata."""
        return {
            "node_count": len(self.node_ids),
            "zoning_id": self.zoning_id,
            "zoning_version": self.zoning_version,
        }


@dataclass(frozen=True)
class NetworkSpec:
    """Rules used to turn an OD table into a network.

    Only a directed, sum-aggregated network is implemented in the first
    release. Keeping these decisions in a value object makes later temporal,
    spatial, and undirected variants explicit instead of silently changing
    the meaning of an adjacency matrix.
    """

    origin: str = "id_origin"
    destination: str = "id_destination"
    weight: str = "n_trips"
    directed: bool = True
    aggregation: str = "sum"
    self_loops: str = "keep"

    def __post_init__(self) -> None:
        if not self.directed:
            raise ValueError(
                "Undirected OD construction is not implemented yet. Build a "
                "directed network, then use symmetrize_network() with an "
                "explicit rule."
            )
        if self.aggregation != "sum":
            raise ValueError("Only aggregation='sum' is supported.")
        if self.self_loops not in {"keep", "drop"}:
            raise ValueError("self_loops must be either 'keep' or 'drop'.")
        for name, value in (
            ("origin", self.origin),
            ("destination", self.destination),
            ("weight", self.weight),
        ):
            if not isinstance(value, str) or not value:
                raise ValueError("%s must be a non-empty column name." % name)
        if len({self.origin, self.destination, self.weight}) != 3:
            raise ValueError("origin, destination, and weight must use distinct columns.")


@dataclass(frozen=True)
class NetworkMetadata:
    """Auditable accounting information for a built network."""

    weight: str
    directed: bool
    aggregation: str
    self_loops: str
    node_universe: str
    input_edge_count: int
    represented_edge_count: int
    input_weight: float
    represented_weight: float
    dropped_self_loop_weight: float
    weight_normalization: Optional[str] = None

    def __post_init__(self) -> None:
        for name in ("weight", "aggregation", "self_loops", "node_universe"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError("%s must be a non-empty string." % name)
        if self.weight_normalization is not None and (
            not isinstance(self.weight_normalization, str)
            or not self.weight_normalization.strip()
        ):
            raise ValueError("weight_normalization must be a non-empty string.")
        for name in ("input_edge_count", "represented_edge_count"):
            value = getattr(self, name)
            if isinstance(value, (bool, np.bool_)) or not isinstance(
                value, (int, np.integer)
            ) or value < 0:
                raise ValueError("%s must be a non-negative integer." % name)
        for name in (
            "input_weight", "represented_weight", "dropped_self_loop_weight"
        ):
            value = getattr(self, name)
            if (
                isinstance(value, (bool, np.bool_))
                or not isinstance(value, (int, float, np.integer, np.floating))
                or not np.isfinite(value)
                or value < 0
            ):
                raise ValueError("%s must be finite and non-negative." % name)


@dataclass(frozen=True)
class CommunityPartition:
    """A reproducible community assignment over one :class:`NodeIndex`.

    Community labels are algorithm-specific identifiers: callers should use
    membership relations rather than compare their numeric values across runs.
    ``hierarchy`` stores the complete module path supplied by a multilevel
    algorithm; its first item is the corresponding top-level assignment.
    """

    node_index: NodeIndex
    assignments: Mapping[str, int]
    hierarchy: Mapping[str, Tuple[int, ...]]
    algorithm: str
    algorithm_version: Optional[str]
    parameters: Mapping[str, object]
    network_fingerprint: str
    algorithm_metrics: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.node_index, NodeIndex):
            raise TypeError("node_index must be a NodeIndex instance.")
        if not isinstance(self.algorithm, str) or not self.algorithm.strip():
            raise ValueError("algorithm must be a non-empty string.")
        if (
            not isinstance(self.network_fingerprint, str)
            or not self.network_fingerprint
        ):
            raise ValueError("network_fingerprint must be a non-empty string.")

        expected_ids = set(self.node_index.node_ids.tolist())
        assignment_ids = {str(node_id) for node_id in self.assignments}
        hierarchy_ids = {str(node_id) for node_id in self.hierarchy}
        if (
            len(assignment_ids) != len(self.assignments)
            or len(hierarchy_ids) != len(self.hierarchy)
        ):
            raise ValueError("Community node IDs collide after string normalization.")
        if assignment_ids != expected_ids or hierarchy_ids != expected_ids:
            raise ValueError(
                "assignments and hierarchy must each cover exactly the node index."
            )

        for module in self.assignments.values():
            if isinstance(module, (bool, np.bool_)) or not isinstance(
                module, (int, np.integer)
            ):
                raise ValueError("Community module IDs must be integers.")
        for path in self.hierarchy.values():
            if any(
                isinstance(module, (bool, np.bool_))
                or not isinstance(module, (int, np.integer))
                for module in path
            ):
                raise ValueError("Community hierarchy IDs must be integers.")
        assignments = {
            str(node_id): int(module) for node_id, module in self.assignments.items()
        }
        hierarchy = {
            str(node_id): tuple(int(module) for module in path)
            for node_id, path in self.hierarchy.items()
        }
        for node_id, path in hierarchy.items():
            if not path:
                raise ValueError(
                    "Each node hierarchy must contain at least one module."
                )
            if path[0] != assignments[node_id]:
                raise ValueError(
                    "The first hierarchy module must equal the top-level "
                    "assignment."
                )

        codelength = self.algorithm_metrics.get("codelength")
        num_top_modules = self.algorithm_metrics.get("num_top_modules")
        if codelength is not None and not np.isfinite(codelength):
            raise ValueError("codelength must be finite when provided.")
        if num_top_modules is not None and num_top_modules < 1:
            raise ValueError("num_top_modules must be positive when provided.")

        object.__setattr__(self, "assignments", MappingProxyType(assignments))
        object.__setattr__(self, "hierarchy", MappingProxyType(hierarchy))
        object.__setattr__(self, "parameters", _freeze_provenance(self.parameters))
        object.__setattr__(
            self, "algorithm_metrics", _freeze_provenance(self.algorithm_metrics)
        )

    @property
    def codelength(self) -> Optional[float]:
        """Infomap code length, when supplied by that adapter."""
        value = self.algorithm_metrics.get("codelength")
        return None if value is None else float(value)

    @property
    def num_top_modules(self) -> Optional[int]:
        """Infomap top-level module count, when supplied by that adapter."""
        value = self.algorithm_metrics.get("num_top_modules")
        return None if value is None else int(value)

    def module_of(self, node_id: object) -> int:
        """Return the algorithm's top-level module for ``node_id``."""
        try:
            return self.assignments[str(node_id)]
        except KeyError as error:
            raise KeyError("Unknown node ID: %r." % node_id) from error

    def communities(self) -> Dict[int, frozenset[str]]:
        """Group node IDs by top-level module without assuming label order."""
        result: Dict[int, set[str]] = {}
        for node_id, module in self.assignments.items():
            result.setdefault(module, set()).add(node_id)
        return {module: frozenset(node_ids) for module, node_ids in result.items()}

    def __reduce__(self):
        return (
            type(self),
            (
                self.node_index,
                dict(self.assignments),
                dict(self.hierarchy),
                self.algorithm,
                self.algorithm_version,
                dict(self.parameters),
                self.network_fingerprint,
                dict(self.algorithm_metrics),
            ),
        )


@dataclass(frozen=True)
class SparseMobilityNetwork:
    """A weighted mobility network with an immutable node contract.

    ``node_ids[i]`` is the zone represented by row and column ``i`` in
    ``adjacency``. The IDs are sorted lexicographically when inferred from
    the OD data, or retain the caller-provided order when ``node_ids`` is
    supplied to :func:`build_network`.
    """

    adjacency: csr_array
    node_ids: np.ndarray
    metadata: NetworkMetadata
    provenance: Optional[Mapping[str, object]] = None
    node_index: Optional[NodeIndex] = None
    _number_of_edges: int = field(init=False, repr=False, compare=False)
    _total_weight: float = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        matrix = csr_array(self.adjacency, dtype=np.float64, copy=True)
        if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
            raise ValueError("adjacency must be a square two-dimensional matrix.")
        if not isinstance(self.metadata, NetworkMetadata):
            raise TypeError("metadata must be a NetworkMetadata instance.")
        if self.provenance is not None and not isinstance(self.provenance, Mapping):
            raise TypeError("provenance must be a mapping when provided.")

        if any(_missing_node_id(node_id) for node_id in self.node_ids):
            raise ValueError("node_ids must not contain null IDs.")
        node_ids = np.asarray(self.node_ids, dtype=str).copy()
        if node_ids.ndim != 1 or len(node_ids) != matrix.shape[0]:
            raise ValueError(
                "node_ids must be one-dimensional and match the adjacency size."
            )
        if len(np.unique(node_ids)) != len(node_ids):
            raise ValueError("node_ids must be unique.")

        if self.node_index is None:
            node_index = NodeIndex(node_ids)
        elif not isinstance(self.node_index, NodeIndex):
            raise TypeError("node_index must be a NodeIndex instance.")
        else:
            node_index = self.node_index
            if not np.array_equal(node_ids, node_index.node_ids):
                raise ValueError("node_ids and node_index.node_ids must be identical.")

        matrix.sum_duplicates()
        matrix.sort_indices()
        matrix.eliminate_zeros()
        if not np.all(np.isfinite(matrix.data)) or np.any(matrix.data < 0):
            raise ValueError("adjacency weights must be finite and non-negative.")
        if not self.metadata.directed:
            difference = (matrix - matrix.T).tocsr()
            if difference.nnz and not np.allclose(
                difference.data, 0.0, rtol=1e-12, atol=1e-9
            ):
                raise ValueError("undirected adjacency must be symmetric.")
            # Sparse projection can change summation order in the two matrix
            # triangles. Canonicalise harmless round-off before freezing CSR.
            if difference.nnz:
                matrix = ((matrix + matrix.T) / 2.0).tocsr()
                matrix.sum_duplicates()
                matrix.eliminate_zeros()
        logical_count = (
            matrix.nnz
            if self.metadata.directed
            else int((matrix.nnz + np.count_nonzero(matrix.diagonal())) // 2)
        )
        logical_weight = (
            float(matrix.sum())
            if self.metadata.directed
            else float((matrix.sum() + matrix.diagonal().sum()) / 2)
        )
        if not np.isfinite(logical_weight):
            raise ValueError("Total adjacency weight must be finite.")
        if self.metadata.represented_edge_count != logical_count:
            raise ValueError("metadata edge count does not match adjacency.")
        if not np.isclose(
            self.metadata.represented_weight, logical_weight, rtol=1e-12, atol=1e-9
        ):
            raise ValueError("metadata represented weight does not match adjacency.")
        matrix = _read_only_csr(matrix)
        provenance = _freeze_provenance(self.provenance or {})
        object.__setattr__(self, "adjacency", matrix)
        object.__setattr__(self, "node_ids", node_index.node_ids)
        object.__setattr__(self, "provenance", provenance)
        object.__setattr__(self, "node_index", node_index)
        object.__setattr__(self, "_number_of_edges", logical_count)
        object.__setattr__(self, "_total_weight", logical_weight)

    def __reduce__(self):
        return (
            type(self),
            (
                self.adjacency,
                self.node_ids,
                self.metadata,
                _audit_value(self.provenance),
                self.node_index,
            ),
        )

    @property
    def number_of_nodes(self) -> int:
        """Number of nodes, including explicitly supplied isolates."""
        return self.adjacency.shape[0]

    @property
    def number_of_edges(self) -> int:
        """Number of logical non-zero edges under the direction contract."""
        return self._number_of_edges

    @property
    def total_weight(self) -> float:
        """Total logical edge weight without double-counting undirected pairs."""
        return self._total_weight

    def to_edge_table(
        self,
        origin: str = "id_origin",
        destination: str = "id_destination",
        weight: str = "weight",
        *,
        sort: bool = True,
    ) -> pl.DataFrame:
        """Return the sparse non-zero entries as a Polars edge table."""
        matrix = (
            self.adjacency
            if self.metadata.directed
            else triu(self.adjacency, format="coo")
        )
        coo = matrix.tocoo(copy=False)
        table = pl.DataFrame(
            {
                origin: self.node_ids[coo.row],
                destination: self.node_ids[coo.col],
                weight: coo.data,
            }
        )
        return table.sort([origin, destination]) if sort else table

    def audit(self) -> Dict[str, object]:
        """Return flow accounting together with matrix dimensions."""
        result = asdict(self.metadata)
        if result["weight_normalization"] is None:
            result.pop("weight_normalization")
        result.update(
            {
                "number_of_nodes": self.number_of_nodes,
                "number_of_edges": self.number_of_edges,
                "matrix_weight": self.total_weight,
            }
        )
        if not self.metadata.directed:
            result["stored_symmetric_matrix_weight"] = float(self.adjacency.sum())
        if self.provenance:
            result["provenance"] = _audit_value(self.provenance)
        if (
            self.node_index.zoning_id is not None
            or self.node_index.zoning_version is not None
        ):
            result["node_index"] = self.node_index.describe()
        return result

    def node_positions(self) -> Dict[str, int]:
        """Return the immutable node-ID-to-matrix-index mapping."""
        return self.node_index.positions()

    def align_to(
        self, target: Union["SparseMobilityNetwork", NodeIndex]
    ) -> "SparseMobilityNetwork":
        """Return this network reordered to a compatible target node index."""
        target_index = (
            target.node_index
            if isinstance(target, SparseMobilityNetwork)
            else target
        )
        if target_index is self.node_index:
            return self
        permutation = self.node_index.permutation_to(target_index)
        matrix = self.adjacency[permutation, :][:, permutation].tocsr()
        return SparseMobilityNetwork(
            matrix,
            target_index.node_ids,
            self.metadata,
            self.provenance,
            target_index,
        )
