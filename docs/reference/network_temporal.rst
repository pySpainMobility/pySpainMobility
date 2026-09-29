Temporal networks
=================

Build snapshots from the dates in a processed OD table, with a shared node
order. For downloaded data, provide the acquisition manifest from
:meth:`~pyspainmobility.mobility.mobility.Mobility.get_acquisition_manifest`.
The :doc:`examples <../network>` show how source coverage changes the mean.

- ``snapshot()`` builds a network for one observed day.
- ``sum_network()`` sums selected observed days.
- ``mean_per_observed_day()`` divides by the number of selected observed days,
  including genuinely observed days with no retained flows.
- ``coverage`` identifies observed, missing and unresolved dates.
- Snapshot comparison methods use the same measures as :doc:`network_metrics`.

Build temporal networks
-----------------------

.. autofunction:: pyspainmobility.network.temporal.build_temporal_network

Snapshots and aggregates
------------------------

Create this result with ``build_temporal_network()``.

.. autoclass:: pyspainmobility.network.temporal.TemporalMobilityNetwork
   :members: number_of_observed_days, snapshot, snapshots, sum_network, mean_per_observed_day, snapshot_strengths, compare_snapshots, snapshot_edge_changes, destination_stability, audit, clear_cache
   :no-undoc-members:
   :exclude-members: __init__

Source coverage
---------------

.. autoclass:: pyspainmobility.network.temporal.TemporalCoverage
   :members: missing_source_dates, empty_observed_dates, unresolved_requested_dates, audit
   :no-undoc-members:
   :exclude-members: __init__, __post_init__
