# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import sys
import os
from pathlib import Path

# -- Path setup --------------------------------------------------------------

sys.path.insert(0, os.path.abspath(".."))
sys.path.insert(0, os.path.abspath("../pyspainmobility"))

# -- Project information -----------------------------------------------------
project = 'pySpainMobility'
copyright = '2025, Massimiliano Luca'
author = 'Massimiliano Luca'
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
#html_theme = 'furo'
#html_static_path = ['_static']

# Theme options are theme-specific 
# html_theme_options = {
#     "sidebar_hide_name": False,
#     "light_css_variables": {
#         "color-brand-primary": "#2E86AB",
#         "color-brand-content": "#2E86AB",
#     },
#     "dark_css_variables": {
#         "color-brand-primary": "#A23B72",
#         "color-brand-content": "#A23B72",
#     },
# }


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
