Mobility networks
=================

The network module turns processed origin-destination (OD) rows into a SciPy
CSR matrix. Rows and columns share a stable :class:`~pyspainmobility.network.model.NodeIndex`.
NetworkX and Infomap are optional adapters; the sparse matrix is the main
representation.

Build a network
---------------

Repeated rows for an origin-destination pair are summed, including rows from
different hours or categories. Filter the OD table first when you need a
particular period, hour, or category. Construction is directed; choose whether
to keep or drop self-loops explicitly.

.. code-block:: python

   import polars as pl
   from pyspainmobility import NodeIndex, NetworkSpec, build_network

   od = pl.DataFrame({
       "date": ["2024-01-01", "2024-01-01", "2024-01-03"],
       "id_origin": ["A", "A", "B"],
       "id_destination": ["B", "B", "A"],
       "n_trips": [3.0, 2.0, 4.0],
   })
   nodes = NodeIndex(["A", "B", "C"], zoning_id="example", zoning_version="v1")
   network = build_network(
       od,
       spec=NetworkSpec(weight="n_trips", self_loops="keep"),
       node_index=nodes,
   )

   print(network.adjacency)  # A -> B has weight 5; C remains an isolate
   print(network.to_edge_table())
   print(network.audit())

The node index preserves the same matrix ordering across periods and includes
isolates. A comparison rejects incompatible zoning identities, weight fields,
or normalizations. To form an undirected network, call
:func:`~pyspainmobility.network.transforms.symmetrize_network` with a named
rule such as ``sum`` or ``mutual``.

Compare observed days
---------------------

Use an acquisition manifest from :meth:`~pyspainmobility.mobility.mobility.Mobility.get_acquisition_manifest`
when working with downloaded data. It distinguishes a missing or failed file
from an observed day with no OD rows. When a manifest is unavailable, pass
``observed_dates`` explicitly; otherwise availability can only be inferred
from OD rows.

.. code-block:: python

   from pyspainmobility import build_temporal_network

   temporal = build_temporal_network(
       od,
       node_index=nodes,
       requested_dates=["2024-01-01", "2024-01-02", "2024-01-03"],
       observed_dates=["2024-01-01", "2024-01-03"],
   )
   print(temporal.coverage.missing_source_dates)  # ('2024-01-02',)
   print(temporal.snapshot("2024-01-01").to_edge_table())
   print(temporal.compare_snapshots("2024-01-01", "2024-01-03").audit())
   print(temporal.mean_per_observed_day().audit())

The mean divides by two observed days in this example. A missing day is not
treated as zero flow. Snapshots use one shared node index and a bounded cache.
For long periods with frequent day queries, use a date-partitioned Parquet
dataset so Polars can prune other days.

Spatial aggregation and metrics
-------------------------------

An exact mapping assigning each source node to one target group permits
flow-preserving aggregation. Source-zone flows that become internal to a
target group appear as self-loops by default. The audit records any flow
removed by ``self_loops="drop"``.

.. code-block:: python

   from pyspainmobility import aggregate_network, node_strengths

   grouped = aggregate_network(network, {"A": "P", "B": "P", "C": "Q"})
   print(grouped.audit()["provenance"]["spatial"])
   print(node_strengths(network))

For an OD table that is still available, use
:func:`~pyspainmobility.network.spatial.aggregate_od_network` to aggregate
before building the fine-resolution matrix. :class:`~pyspainmobility.zones.zones.Zones`
can provide a checked mapping to province codes with ``get_province_mapping()``.
The helper uses the selected zoning level and supports version-1 municipality
sets. A zone spanning several municipalities is accepted when they all belong
to one province; missing codes and zones spanning multiple provinces raise.
Code validation checks the five-digit format and province prefix 01–52,
including Ceuta and Melilla, without checking historical municipality registries.
Fractional zone splitting and automatic conversion between different zoning
versions are not supported.

For direct province-level input, use ``Mobility(zones="provinces")``. It sums
district-source OD, overnight-stay and trip-count products, retaining dates,
hours, selected categories and internal flows. Source days are validated
before the geographic transformation. Version 1 has no overnight-stay product.
Zones lacking a unique province are explicitly excluded: returned DataFrame
``attrs``, acquisition manifests and adjacent ``*.parquet.provenance.json``
files report excluded rows and additive measures. Files are labelled
``provinces_derived`` and remain compatible with the existing network builders.

``Zones(zones="provinces").get_zone_geodataframe()`` dissolves mapped district
geometries and records excluded zones and repairs in ``attrs``. These derived
geometries exclude unmappable territories and do not represent official
provincial boundaries. Lower-level province mappings retain strict validation
unless ``unmapped="exclude"`` is explicitly supplied.

Community detection
-------------------

The optional Infomap adapter consumes the CSR network directly. It records
the seed, algorithm version, options, node index, and a fingerprint of the
matrix supplied to Infomap.

.. code-block:: python

   from pyspainmobility.network.integrations import run_infomap

   partition = run_infomap(network, seed=123, num_trials=10)
   print(partition.communities())

Install ``pyspainmobility[infomap]`` for this example. For NetworkX algorithms
or visualization, install ``pyspainmobility[network]`` and use
:func:`~pyspainmobility.network.integrations.networkx.to_networkx`. Geographic
node attributes are not attached to that graph automatically; join the zone
geometries from :class:`~pyspainmobility.zones.zones.Zones` when needed.
