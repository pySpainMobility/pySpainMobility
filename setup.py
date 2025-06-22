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
    version="1.0.4",
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
        "tqdm>=4.0.0",
        "matplotlib>=3.0.0",
        "pyarrow>=8.0.0",
        "dask[dataframe] >=2024.0"

    ],
    extras_require={
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
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: BSD License",
        "Operating System :: OS Independent",
    ],
)
