Spatial network aggregation
===========================

Aggregate flows using a mapping that assigns every source zone to exactly
one target group. :doc:`Zones <zones>` provides validated territorial mappings;
:doc:`Mobility <mobility>` can produce derived provincial OD tables directly.
For a small example preserving internal flows, see :doc:`../network`.

- ``aggregate_od_network()`` groups an OD table before creating its sparse matrix.
- ``aggregate_network()`` groups an existing sparse network.
- Flows within the same target group become self-loops and are retained by default.
- The audit records internalized flow and any self-loop weight removed.
- Fractional zone splitting and automatic conversion between zoning versions
  are not supported.

Aggregate an OD table
---------------------

.. autofunction:: pyspainmobility.network.spatial.aggregate_od_network

Aggregate an existing network
-----------------------------

.. autofunction:: pyspainmobility.network.spatial.aggregate_network
