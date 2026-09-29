Flow measures and comparisons
=============================

These functions use the weights chosen when the network was built. With the
default ``weight="n_trips"``, strengths and flow changes are measured in trips.
For examples with expected results, see :doc:`../network`.

- ``node_strengths()``: flow sent and received by each zone.
- ``compare_networks()``: similarity, edge overlap and overall flow changes.
- ``edge_changes()``: weights and signed changes for individual OD pairs.
- ``destination_similarity()``: similarity of each origin's destination profile.

Flow by zone
------------

.. autofunction:: pyspainmobility.network.metrics.node_strengths

Whole-network comparison
------------------------

.. autofunction:: pyspainmobility.network.metrics.compare_networks

.. list-table:: Fields in the comparison result
   :header-rows: 1
   :widths: 35 65

   * - Field
     - Definition
   * - ``left_weight``, ``right_weight``
     - Total logical edge weight in the first and second networks.
   * - ``left_edge_count``, ``right_edge_count``
     - Number of non-zero connections in each network.
   * - ``shared_edge_count``
     - Connections present in both networks.
   * - ``added_edge_count``, ``removed_edge_count``
     - Connections appearing or disappearing in the second network.
   * - ``edge_jaccard``
     - Shared connection count divided by the union connection count.
   * - ``edge_turnover``
     - ``1 - edge_jaccard``; the fraction of union connections not shared.
   * - ``shared_weight``, ``union_weight``
     - Sum of pairwise minimum and maximum edge weights, respectively.
   * - ``weighted_jaccard``
     - ``shared_weight / union_weight``; accounts for both overlap and magnitude.
   * - ``cosine_similarity``
     - Cosine of the vectors of edge weights; compares their relative pattern.
   * - ``flow_increase``, ``flow_decrease``
     - Sums of positive and negative weight changes, reported as positive totals.

Both Jaccard measures and cosine similarity are 1 when both networks are
empty, and 0 when only one is empty. Undirected connections are counted once,
including each self-loop. Comparisons align node order and reject incompatible
node universes, zoning metadata, directions, weight fields or normalizations.

.. autoclass:: pyspainmobility.network.metrics.NetworkComparison
   :members: edge_turnover, audit
   :no-undoc-members:
   :exclude-members: __init__

Changes by connection
---------------------

.. autofunction:: pyspainmobility.network.metrics.edge_changes

Destination profiles by origin
------------------------------

.. autofunction:: pyspainmobility.network.metrics.destination_similarity
