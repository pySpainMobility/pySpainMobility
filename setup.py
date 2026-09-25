from setuptools import setup, find_packages
import io

# Readme TODO
try:
    with io.open("README.md", encoding="utf-8") as f:
        long_description = f.read()
except FileNotFoundError:
    long_description = ""

setup(
    name="pyspainmobility",
    version="2.0.0",
    author="Massimiliano Luca",
    author_email="mluca@fbk.eu",
    description="Library for downloading and processing Spanish mobility data from MITMA",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/pySpainMobility/pySpainMobility",
    license="BSD 3-Clause License",
    package_dir={"": "."},
    packages=find_packages(include=["pyspainmobility", "pyspainmobility.*"]),
    python_requires=">=3.9",
    install_requires=[
        "geopandas~=1.0.1",
        "pandas>=1.5",
        "tqdm>=4.0.0",
        "polars>=1.25,<2",
        "scipy>=1.11",
    ],
    extras_require={
        "arrow": ["pyarrow>=8.0.0"],
        "dask": ["dask[dataframe]>=2024.0"],
        # for building the Sphinx docs
        "docs": [
            "Sphinx>=4.0.0",
            "furo",
            "sphinx-autodoc-typehints",
            "sphinxcontrib-napoleon",
        ],
        # for running tests
        "dev": [
            "pytest>=6.0",
            "flake8",
            "networkx>=3.0",
            "infomap>=2.15,<3",
            "pyarrow>=8.0.0",
            "dask[dataframe]>=2024.0",
        ],
        # adapters for users who need NetworkX algorithms or visualisation
        "network": [
            "networkx>=3.0",
        ],
        # community detection adapter; deliberately optional and CSR-native
        "infomap": [
            "infomap>=2.15,<3",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: BSD License",
        "Operating System :: OS Independent",
    ],
)
