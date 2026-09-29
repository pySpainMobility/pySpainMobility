.. pySpainMobility documentation master file
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

.. meta::
   :description: Python package for accessing and standardizing Spanish mobility data from official sources
   :keywords: mobility data, Spain, transportation, python, GIS, urban planning

##################################
pySpainMobility Documentation
##################################

**Standardized access to Spain's official mobility datasets**

Welcome to the documentation for pySpainMobility, an open-source Python package for accessing and analysing mobility data published by the `Spanish Ministry of Transportation and Sustainable Mobility <https://www.transportes.gob.es>`_.

.. note::
   Please report issues or suggestions via our `GitHub repository <https://github.com/pySpainMobility/pySpainMobility/issues>`_.

********************
What you can do
********************

- :doc:`Mobility <reference/mobility>` downloads and processes origin-destination
  trips, overnight stays and trip-count distributions from MITMA.
- :doc:`Zones <reference/zones>` provides zone geometries, names, populations
  and territorial correspondences for interpreting those observations.
- Both classes support districts and municipalities, plus large urban areas
  in version 2. Derived provincial products are also available.
- :doc:`Network analysis <network>` uses the processed flows to build sparse
  matrices, calculate flow measures and compare periods or spatial groupings.

Start with Mobility and Zones to obtain the data and its geographic context.
The network helpers support subsequent analysis of those data.

.. note::
   This site follows the repository's ``main`` branch. Source changes made after
   a package release may appear here before they are available through pip or
   conda. Check the `release history <https://pypi.org/project/pyspainmobility/#history>`_
   for the version you have installed.

********************
Getting Started
********************

Installation
==========================
.. code-block:: bash

   pip install pyspainmobility

For a conda environment, create an environment with Python and pip first, then
use the same pip command. Check the package metadata for the Python version
required by the release you install.

Download mobility data and zones
================================

This example downloads one day of municipality-level trips and loads the
corresponding geometries. It requires access to the MITMA server.

.. code-block:: python

   from pathlib import Path
   from pyspainmobility import Mobility, Zones

   output = str(Path("mobility_data").resolve())
   mobility = Mobility(
       version=2, zones="municipalities", start_date="2024-01-01",
       output_directory=output,
   )
   od = mobility.get_od_data(return_df=True)
   zones = Zones(version=2, zones="municipalities", output_directory=output)
   geometries = zones.get_zone_geodataframe()

   print(od.head())
   print(geometries.head())

- ``od`` is a pandas DataFrame with dates, hours, origin/destination IDs,
  trip counts and total trip-kilometres. A processed Parquet file is also saved.
- ``geometries`` is a GeoDataFrame indexed by the zone IDs used in ``od``.
- For other products and territorial levels, see :doc:`reference/mobility`
  and :doc:`reference/zones`.
- When ready to analyse flows as a network, follow the small, runnable examples
  in :doc:`network`. External algorithm adapters have their own
  :doc:`installation instructions <reference/network_adapters>`.

**********************
Citing pySpainMobility
**********************
If you use this package in your research, please cite:

.. code-block:: text

   Beneduce, C., et al. (2025). pySpainMobility: A Python Package to Access and 
   Manage Spanish Open Mobility Data.

BibTeX entry:

.. code-block:: bibtex

   @misc{beneduce2025pyspainmobility,
      title={pySpainMobility: a Python Package to Access and Manage Spanish Open Mobility Data}, 
      author={Ciro Beneduce and Tania Gullón Muñoz-Repiso and Bruno Lepri and Massimiliano Luca},
      year={2025},
      eprint={2506.13385},
      archivePrefix={arXiv},
      primaryClass={cs.CY},
      url={https://arxiv.org/abs/2506.13385}, 
   }

************************
Documentation Contents
************************

.. toctree::
   :caption: Core API
   :maxdepth: 1

   reference/mobility
   reference/zones

.. toctree::
   :caption: Network analysis
   :maxdepth: 1

   network
   reference/network
