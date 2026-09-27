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
Key Features
********************

- 🔍 Access daily mobility datasets (versions 1 & 2) covering:
   - Municipalities and districts
   - Greater urban areas
   - Time periods from February 2020 to 2021 and from 2022 to present
- 📦 Standardized data structures for consistent analysis
- 🌐 Built-in spatial tessellation handling
- ⚡ Polars processing by default, with optional Arrow and pandas backends
- 🕸️ Sparse OD networks, temporal comparisons, spatial aggregation, and optional NetworkX and Infomap adapters
- 📈 Designed for research reproducibility and policy applications

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

The base package includes the SciPy sparse network representation. Install
optional adapters only when you need them:

.. code-block:: bash

   pip install 'pyspainmobility[network]'  # NetworkX
   pip install 'pyspainmobility[infomap]'  # community detection

For a conda environment, create an environment with Python and pip first, then
use the same pip command. Check the package metadata for the Python version
required by the release you install.

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
   :caption: Guides
   :maxdepth: 2

   network

.. toctree::
   :caption: API Reference
   :maxdepth: 2

   reference/mobility
   reference/zones
   reference/network
