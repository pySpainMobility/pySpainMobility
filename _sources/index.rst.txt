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

Welcome to the documentation for pySpainMobility - an open-source Python package developed by the research community to access, download, and standardize mobility data published by the `Spanish Ministry of Transportation and Sustainable Mobility <https://www.transportes.gob.es>`_.

.. note::
   This is a **FIRST release** (both library and documentation). 
   Please report any issues or suggestions via our `GitHub repository <https://github.com/pySpainMobility/pySpainMobility/issues>`_.

********************
Key Features
********************

- 🔍 Access daily mobility datasets (versions 1 & 2) covering:
   - Municipalities and districts
   - Greater urban areas
   - Time periods from February 2020 to 2021 and from 2022 to present
- 📦 Standardized data structures for consistent analysis
- 🌐 Built-in spatial tessellation handling
- 📈 Designed for research reproducibility and policy applications

********************
Getting Started
********************

Installation
==========================
.. code-block:: bash

   # Using conda 
   conda install -c conda-forge pyspainmobility

   # pip installation
   pip install pyspainmobility

********************
Citing pySpainMobility
********************
If you use this package in your research, please cite:

.. code-block:: text

   Beneduce, C., et al. (2025). pySpainMobility: A Python Package to Access and 
   Manage Spanish Open Mobility Data.

BibTeX entry:

.. code-block:: bibtex

   @article{beneduce2025pyspainmobility,
     title={pySpainMobility: a Python Package to Access and Manage Spanish Open Mobility Data},
     author={Beneduce, Ciro and Gullón Muñoz-Repiso, Tania and Lepri, Bruno and Luca, Massimiliano},
     year={2025}
   }

********************
Documentation Contents
********************

.. toctree::
   :caption: User Guide
   :maxdepth: 2
   
   installation
   examples
   data_overview
   contributing

.. toctree::
   :caption: API Reference
   :maxdepth: 2

   reference/mobility
   reference/zones
