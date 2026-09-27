Network API
===========

Construction and representations
--------------------------------

.. autoclass:: pyspainmobility.network.model.NetworkSpec
   :members:

.. autoclass:: pyspainmobility.network.model.NodeIndex
   :members:

.. autoclass:: pyspainmobility.network.model.SparseMobilityNetwork
   :members:

.. autofunction:: pyspainmobility.network.builder.build_network

.. autofunction:: pyspainmobility.network.transforms.symmetrize_network

Temporal and spatial analysis
-----------------------------

.. autoclass:: pyspainmobility.network.temporal.TemporalCoverage
   :members:

.. autoclass:: pyspainmobility.network.temporal.TemporalMobilityNetwork
   :members:

.. autofunction:: pyspainmobility.network.temporal.build_temporal_network

.. autofunction:: pyspainmobility.network.spatial.aggregate_network

.. autofunction:: pyspainmobility.network.spatial.aggregate_od_network

Metrics and comparisons
-----------------------

.. autoclass:: pyspainmobility.network.metrics.NetworkComparison
   :members:

.. autofunction:: pyspainmobility.network.metrics.node_strengths

.. autofunction:: pyspainmobility.network.metrics.compare_networks

.. autofunction:: pyspainmobility.network.metrics.edge_changes

.. autofunction:: pyspainmobility.network.metrics.destination_similarity

Optional adapters
-----------------

.. autoclass:: pyspainmobility.network.model.CommunityPartition
   :members:

.. autofunction:: pyspainmobility.network.integrations.networkx.to_networkx

.. autofunction:: pyspainmobility.network.integrations.infomap.to_infomap

.. autofunction:: pyspainmobility.network.integrations.infomap.run_infomap
