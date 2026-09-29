External algorithm adapters
===========================

pySpainMobility prepares and validates mobility flows obtained through
:doc:`Mobility <mobility>` and geographic correspondences from
:doc:`Zones <zones>`. These adapters pass its network results to external
projects:

- `SciPy <https://docs.scipy.org/doc/scipy/reference/generated/scipy.sparse.csr_array.html>`_
  provides the sparse matrix representation used by the base package.
- `NetworkX <https://networkx.org/documentation/stable/>`_ provides graph
  algorithms and graph objects through an optional adapter.
- `Infomap <https://www.mapequation.org/infomap/>`_ provides the community
  detection algorithm through an optional adapter.

NetworkX and Infomap are installed separately when their algorithms are needed.
The small network used below is the one built in :doc:`../network`.

NetworkX
--------

.. code-block:: bash

   pip install 'pyspainmobility[network]'

.. code-block:: python

   from pyspainmobility.network.integrations import to_networkx

   graph = to_networkx(network)
   print(graph.number_of_nodes(), graph.number_of_edges())  # 2 2
   print(graph["A"]["B"]["weight"])  # 5.0

The graph preserves direction, weights and isolated nodes. Zone geometries are
not attached automatically; obtain them through ``Zones.get_zone_geodataframe()``.
Weights such as trip counts represent flow strength. Check the chosen NetworkX
algorithm's weight interpretation, especially when it expects path distances.

.. autofunction:: pyspainmobility.network.integrations.networkx.to_networkx

Infomap
-------

.. code-block:: bash

   pip install 'pyspainmobility[infomap]'

.. code-block:: python

   from pyspainmobility.network.integrations import run_infomap

   partition = run_infomap(network, seed=123, num_trials=10)
   print(partition.communities())

Infomap assigns nodes to flow-based communities, which can cross administrative
boundaries. The adapter records the seed, algorithm version, options and input
network fingerprint. Community labels identify modules in that run; matching
numeric labels across runs does not establish that the communities are the same.

.. autofunction:: pyspainmobility.network.integrations.infomap.run_infomap

For direct use of Infomap's Python network object:

.. autofunction:: pyspainmobility.network.integrations.infomap.to_infomap

.. autoclass:: pyspainmobility.network.model.CommunityPartition
   :members: communities, module_of, codelength, num_top_modules
   :no-undoc-members:
   :exclude-members: __init__, __post_init__
