Zones
=====

Obtain the geographic context for mobility observations:

- Zone geometries as a GeoDataFrame indexed by zone ID.
- Zone names and populations where supplied by MITMA.
- Official territorial relation tables.
- Verified mappings for aggregation and derived provincial geometries.

Use :doc:`Mobility <mobility>` to download flows using the same zoning level
and source version.

.. autoclass:: pyspainmobility.zones.zones.Zones
   :members:
   :undoc-members:
   :inherited-members:

Derived province geometries
---------------------------

.. code-block:: python

   from pyspainmobility import Zones

   zones = Zones(zones="provinces", version=2)
   provinces = zones.get_zone_geodataframe()
   print(provinces.index)
   print(provinces.attrs["unmapped_source_ids"])

- Province geometries are dissolved from mapped district geometries. They
  represent derived MITMA territories rather than official province boundaries.
- The string ``id`` index contains two-digit INE province codes. CRS is preserved.
- Result ``attrs`` report excluded source zones and repaired source geometries.
- ``get_province_mapping()`` checks that every municipality in a source zone
  belongs to one province. Missing or cross-province relations raise by default;
  ``unmapped="exclude"`` omits entire unmappable zones and reports their IDs.
- Municipality code validation checks the five-digit format and province prefix
  01–52, without checking historical municipality registry membership.
