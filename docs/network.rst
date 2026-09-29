Network examples
================

Use :doc:`Mobility <reference/mobility>` to obtain processed flows and
:doc:`Zones <reference/zones>` to understand their geographic IDs. The network
helpers then let you:

- Build a directed, weighted network from origin-destination (OD) rows.
- Measure how much flow each zone sends and receives.
- Compare observed days and calculate averages with explicit source coverage.
- Aggregate zones using a verified territorial mapping.

The examples below use a small table and require no downloads. Run them in
order; later examples reuse ``od`` and ``network``. They work with the base
installation. The :doc:`network API reference <reference/network>` documents
parameters and results for each function.

Build a network
---------------

Repeated observations for the same origin-destination pair are summed.
Here A sends 3 + 2 = 5 trips to B, and B sends 4 trips to A.

.. testcode:: network-examples

   import polars as pl
   from pyspainmobility import build_network

   od = pl.DataFrame({
       "date": ["2024-01-01", "2024-01-01", "2024-01-03"],
       "hour": [0, 1, 0],
       "id_origin": ["A", "A", "B"],
       "id_destination": ["B", "B", "A"],
       "n_trips": [3.0, 2.0, 4.0],
       "trips_total_length_km": [30.0, 20.0, 40.0],
   })
   network = build_network(od)
   print(network.node_ids.tolist())
   print(network.number_of_edges)
   print(network.total_weight)

.. testoutput:: network-examples

   ['A', 'B']
   2
   9.0

- ``network.adjacency`` is a SciPy sparse matrix: rows are origins and columns
  are destinations. ``network.node_ids`` identifies their order.
- ``network.to_edge_table()`` returns origin, destination and weight columns
  as a Polars DataFrame.
- The default weight is ``n_trips`` and self-loops (flows within one zone) are
  retained. ``network.audit()`` reports construction rules and flow totals.
- A static network sums all supplied dates, hours and categories. Select the
  observations you need before building it.

For example, retain only hour 0 on 1 January:

.. testcode:: network-examples

   from pyspainmobility import select_od

   selected = select_od(od, filters={"date": "2024-01-01", "hour": [0]})
   morning = build_network(selected)
   print(morning.total_weight)

.. testoutput:: network-examples

   3.0

With downloaded data, pass the DataFrame returned by
``mobility.get_od_data(return_df=True)`` or the path to its processed Parquet
file directly to ``build_network()``.

Measure flow by zone
--------------------

Strength is the sum of incident edge weights. Because this example uses
``n_trips``, the values below count trips.

.. testcode:: network-examples

   from pyspainmobility import node_strengths

   strengths = node_strengths(network)
   print(strengths.select("node_id", "out_strength", "in_strength").rows())

.. testoutput:: network-examples

   [('A', 5.0, 4.0), ('B', 4.0, 5.0)]

.. list-table:: Columns returned by ``node_strengths()``
   :header-rows: 1
   :widths: 25 75

   * - Column
     - Meaning for a directed trip network
   * - ``node_id``
     - Zone identifier.
   * - ``out_strength``
     - Sum of trips departing from the zone.
   * - ``in_strength``
     - Sum of trips arriving in the zone.
   * - ``total_strength``
     - Out-strength plus in-strength. An internal flow contributes to both.

These are weighted flow totals. If you build a network with
``NetworkSpec(weight="trips_total_length_km")``, the strengths are total
trip-kilometres. For an undirected network, ``total_strength`` is the incident
weight, counting each self-loop once.

Compare observed days
---------------------

An observed day with no retained flows and a missing source day have different
meanings. Specify which days were observed when constructing temporal networks.
Here, 1 and 3 January were observed; 2 January was missing.

.. testcode:: network-examples

   from pyspainmobility import build_temporal_network

   temporal = build_temporal_network(
       od,
       requested_dates=["2024-01-01", "2024-01-02", "2024-01-03"],
       observed_dates=["2024-01-01", "2024-01-03"],
   )
   first = temporal.snapshot("2024-01-01")
   last = temporal.snapshot("2024-01-03")
   print(temporal.coverage.missing_source_dates)
   print(temporal.sum_network().total_weight)
   print(temporal.mean_per_observed_day().total_weight)

.. testoutput:: network-examples

   ('2024-01-02',)
   9.0
   4.5

The mean is 9 trips divided by two observed days. A genuinely observed empty
day would count in the denominator; the missing day does not.

For downloaded OD data, use the source manifest from Mobility:

.. code-block:: python

   from pyspainmobility import Mobility, build_temporal_network

   mobility = Mobility(version=2, zones="municipalities", start_date="2024-01-01")
   downloaded_od = mobility.get_od_data(return_df=True)
   downloaded_temporal = build_temporal_network(
       downloaded_od, acquisition_manifest=mobility.get_acquisition_manifest("Viajes")
   )

Here ``downloaded_od`` is the DataFrame returned by that same Mobility
request. For version 1, the OD manifest name is ``"maestra1"``. Without a
manifest or ``observed_dates``, coverage is inferred from data rows.

To inspect changes between the two example days:

.. testcode:: network-examples

   from pyspainmobility import compare_networks, edge_changes

   comparison = compare_networks(first, last)
   print(comparison.added_edge_count, comparison.removed_edge_count)
   print(edge_changes(first, last).select(
       "id_origin", "id_destination", "delta_weight", "change"
   ).rows())

.. testoutput:: network-examples

   1 1
   [('A', 'B', -5.0, 'removed'), ('B', 'A', 4.0, 'added')]

- ``compare_networks()`` summarises shared, added and removed connections,
  similarity and changes in total flow.
- ``edge_changes()`` reports individual OD pairs, including unchanged pairs.
  Its delta is the second network's weight minus the first network's weight.
- ``destination_similarity()`` measures the similarity of each origin's
  destination profile. See :doc:`reference/network_metrics` for definitions,
  output columns and empty-network conventions.
- Comparisons require the same node universe, direction, weight field and
  normalization. Temporal snapshots already share one node index.

Aggregate zones
---------------

A mapping must assign each source zone to exactly one target area. Mapping
both A and B to P makes all nine trips internal to P:

.. testcode:: network-examples

   from pyspainmobility import aggregate_od_network

   grouped = aggregate_od_network(od, {"A": "P", "B": "P"})
   print(grouped.to_edge_table().rows())
   print(grouped.total_weight)

.. testoutput:: network-examples

   [('P', 'P', 9.0)]
   9.0

- Internal flows are kept as self-loops. ``self_loops="drop"`` removes them
  and records the excluded weight in ``grouped.audit()``.
- Use ``aggregate_od_network()`` when the OD table is available, or
  ``aggregate_network()`` when you already have a sparse network.
- :meth:`~pyspainmobility.zones.zones.Zones.get_network_mapping` and
  :meth:`~pyspainmobility.zones.zones.Zones.get_province_mapping` provide checked
  territorial correspondences. Ambiguous or incomplete strict mappings raise.
- For province-level data and geometries, start with
  ``Mobility(zones="provinces")`` and ``Zones(zones="provinces")``. Their
  :doc:`Mobility <reference/mobility>` and :doc:`Zones <reference/zones>` pages
  explain derived provinces and excluded territories.

Choose node order and direction
-------------------------------

For independently built networks, provide the same node index to preserve
matrix order and include zones with no observed flows:

.. testcode:: network-examples

   from pyspainmobility import NodeIndex, NetworkSpec, symmetrize_network

   nodes = NodeIndex(["A", "B", "C"], zoning_id="example", zoning_version="v1")
   ordered = build_network(od, node_index=nodes)
   print(ordered.node_ids.tolist())
   print(node_strengths(ordered).filter(pl.col("node_id") == "C").rows())

.. testoutput:: network-examples

   ['A', 'B', 'C']
   [('C', 0.0, 0.0, 0.0)]

- ``NetworkSpec(self_loops="drop")`` excludes internal flows during construction.
- ``symmetrize_network(network, method="sum")`` combines both directions into
  one undirected connection. Other rules are ``mean``, ``max`` and ``mutual``;
  their definitions are in :doc:`reference/network`.
- :doc:`External algorithm adapters <reference/network_adapters>` connect these
  results to NetworkX and Infomap. The graph algorithms and community detection
  are supplied by those projects.
