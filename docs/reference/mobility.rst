Mobility
========

Download and process the daily mobility observations published by MITMA:

- Origin-destination trips and their total trip-kilometres.
- Overnight stays (version 2).
- People grouped by number of trips.
- Selected activity or demographic dimensions and acquisition manifests.

Use :doc:`Zones <zones>` to obtain the geography associated with the zone IDs.

.. autoclass:: pyspainmobility.mobility.mobility.Mobility
   :members:
   :undoc-members:
   :inherited-members:

Selecting processed OD data
---------------------------

.. autofunction:: pyspainmobility.mobility.selection.select_od

Derived provincial products
---------------------------

Use ``zones="provinces"`` to sum district-source OD, overnight-stay and
trip-count products by province. Dates, hours, selected categories and internal
flows are retained. Version 1 has no overnight-stay product.

.. code-block:: python

   from pyspainmobility import Mobility

   mobility = Mobility(version=2, zones="provinces", start_date="2024-01-01")
   od = mobility.get_od_data(return_df=True, dimensions=["age", "gender"])
   print(od.attrs["spatial"])
   print(mobility.get_acquisition_manifest("Viajes"))

- Province IDs are two-digit INE codes, including Ceuta (``51``) and Melilla (``52``).
- Zones lacking a unique province are explicitly excluded. DataFrame ``attrs``,
  per-day acquisition manifests and ``*.parquet.provenance.json`` files report
  excluded processed rows, trips, trip-kilometres or people.
- Trip-kilometres are summed from the source; distances are not recalculated
  from province centroids. Trip-count categories retain their original meaning.
- Files contain ``provinces_derived`` in their names. Raw downloads remain
  district sources and can be reused for district-level analyses.
- :doc:`Zones <zones>` provides the corresponding derived province geometries.

Ordinary provenance publication errors restore the previous Parquet output;
overwriting requires hard-link support in the output filesystem. An abrupt
process or system interruption between the two atomic file replacements can
leave a mismatched pair; rerun the request to regenerate both together.
If rollback itself fails, a hidden ``*.previous`` file retains the old data.
