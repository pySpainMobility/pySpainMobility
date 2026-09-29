Network API
===========

These helpers analyse OD data obtained through :doc:`Mobility <mobility>`.
Use :doc:`Zones <zones>` for geographic context and territorial mappings.
For runnable examples, start with :doc:`../network`.

- ``build_network()`` constructs a directed network from processed OD rows.
- ``NetworkSpec`` selects the weight column and self-loop policy.
- ``SparseMobilityNetwork`` holds the sparse matrix, zone IDs and flow audit.
- ``NodeIndex`` preserves node order across independently built networks.
- ``symmetrize_network()`` combines directions using an explicit weight rule.

.. toctree::
   :maxdepth: 1

   network_metrics
   network_temporal
   network_spatial
   network_adapters

Build a network
---------------

.. autofunction:: pyspainmobility.network.builder.build_network

Construction options
--------------------

.. autoclass:: pyspainmobility.network.model.NetworkSpec
   :no-members:
   :exclude-members: __init__, __post_init__

Network result
--------------

.. autoclass:: pyspainmobility.network.model.SparseMobilityNetwork
   :members: number_of_nodes, number_of_edges, total_weight, to_edge_table, audit, node_positions, align_to
   :no-undoc-members:
   :exclude-members: __init__, __post_init__

Shared node order
-----------------

.. autoclass:: pyspainmobility.network.model.NodeIndex
   :members: positions, assert_compatible, permutation_to, describe
   :no-undoc-members:
   :exclude-members: __init__, __post_init__

Combine flow directions
-----------------------

.. autofunction:: pyspainmobility.network.transforms.symmetrize_network
