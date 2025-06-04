# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import sys
import os
from pathlib import Path

# -- Path setup --------------------------------------------------------------

sys.path.insert(0, os.path.abspath(".."))
#sys.path.insert(0, os.path.abspath("../pyspainmobility"))

# -- Project information -----------------------------------------------------
project = 'pySpainMobility'
copyright = ''
author = 'Ciro Beneduce, Tania Gullón Muñoz-Repiso, Bruno Lepri, Massimiliano Luca'
release = '0.1.0'
version = '0.1.0'

# -- General configuration ---------------------------------------------------
extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.autosummary',
    'sphinx.ext.napoleon',
    'sphinx.ext.viewcode',
    'sphinx.ext.intersphinx',
    'sphinx.ext.duration',
    'sphinx.ext.doctest',
]

# Napoleon settings for NumPy/Google style docstrings
napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = False
napoleon_include_private_with_doc = False
napoleon_include_special_with_doc = True
napoleon_use_admonition_for_examples = False
napoleon_use_admonition_for_notes = False
napoleon_use_admonition_for_references = False
napoleon_use_ivar = True
napoleon_use_param = True
napoleon_use_rtype = True
napoleon_preprocess_types = False
napoleon_type_aliases = None
napoleon_attr_annotations = True

# Autodoc settings
autodoc_default_options = {
    'members': True,
    'member-order': 'bysource',
    'special-members': '__init__',
    'undoc-members': True,
    'exclude-members': '__weakref__'
}

# Autosummary settings
autosummary_generate = True
autosummary_imported_members = True

templates_path = ['_templates']

exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

# The suffix(es) of source filenames.
source_suffix = '.rst'

# The master toctree document.
master_doc = 'index'

language = 'en'

# --HTML output -------------------------------------------------
html_theme = "furo"
html_logo = "../logo.jpeg"
html_theme_options = {
    "canonical_url": "",
    "analytics_id": "UA-XXXXXXX-1",
    "logo_only": False,
    "display_version": True,
    "prev_next_buttons_location": "bottom",
    "style_external_links": False,
    "vcs_pageview_mode": "",
    "style_nav_header_background": "white",
    # Toc options
    "collapse_navigation": True,
    "sticky_navigation": True,
    "navigation_depth": 4,
    "includehidden": True,
    "titles_only": False,
}

html_theme_path = [
    "_themes",
]

html_favicon = None 

# -- Extension configuration -------------------------------------------------

# Intersphinx mapping
intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
    'pandas': ('https://pandas.pydata.org/docs/', None),
    'numpy': ('https://numpy.org/doc/stable/', None),
    'geopandas': ('https://geopandas.org/en/stable/', None),
    'matplotlib': ('https://matplotlib.org/stable/', None),
}

# --LaTeX output ------------------------------------------------
latex_elements = {
    # The paper size
    'papersize': 'letterpaper',
    
    # The font size 
    'pointsize': '10pt',
    
    # Additional stuff for the LaTeX preamble.
    'preamble': '',
    
    # Latex figure (float) alignment
    'figure_align': 'htbp',
}

# Grouping the document tree into LaTeX files. List of tuples
# (source start file, target name, title, author, documentclass [howto, manual, or own class]).
latex_documents = [
    (master_doc, 'pySpainMobility.tex', 'pySpainMobility Documentation',
     'Massimiliano Luca', 'manual'),
]

# --manual page output ------------------------------------------
man_pages = [
    (master_doc, 'pyspainmobility', 'pySpainMobility Documentation',
     [author], 1)
]

# --Texinfo output ----------------------------------------------
texinfo_documents = [
    (master_doc, 'pySpainMobility', 'pySpainMobility Documentation',
     author, 'pySpainMobility', 'A Python library for Spanish mobility data analysis.',
     'Miscellaneous'),
]
