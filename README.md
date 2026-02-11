# pySpainMobility

## A Python package to access, download and standardise 
![logo small](https://raw.githubusercontent.com/pySpainMobility/pySpainMobility/refs/heads/main/logo_small.png)

Mobility patterns play a critical role in a wide range of societal challenges, from epidemic modeling and emergency response to transportation planning and regional development. Yet, access to high-quality, timely, and openly available mobility data remains limited. In response, the [Spanish Ministry of Transportation and Sustainable Mobility](https://www.transportes.gob.es) has released daily [mobility datasets](https://www.transportes.gob.es/ministerio/proyectos-singulares/estudios-de-movilidad-con-big-data/metodologia-del-estudio-de-movilidad-con-bigdata) based on anonymized mobile phone data, covering districts, municipalities, and greater urban areas from February 2020 to June 2021 (`version 1`) and again from January 2022 onward (`version 2`). `pySpainMobility` is a Python package that simplifies access to these datasets and their associated spatial tessellations through a standardized, well-documented interface. By lowering the technical barrier to working with large-scale mobility data, the package enables reproducible analysis and supports applications across research, policy, and operational domains.

The full documentation of the library is available on the [`pySpainMobility` website](https://pyspainmobility.github.io/pySpainMobility) and a paper with some examples and further details is available on arXiv. If you are using the library or it content, please use this reference:

Beneduce, C., Gullón Muñoz-Repiso, T., Lepri, B., & Luca, M. (2025). pySpainMobility: a Python Package to Access and Manage Spanish Open Mobility Data

Bibtex:
```
@misc{beneduce2025pyspainmobility,
      title={pySpainMobility: a Python Package to Access and Manage Spanish Open Mobility Data}, 
      author={Ciro Beneduce and Tania Gullón Muñoz-Repiso and Bruno Lepri and Massimiliano Luca},
      year={2025},
      eprint={2506.13385},
      archivePrefix={arXiv},
      primaryClass={cs.CY},
      url={https://arxiv.org/abs/2506.13385}, 
}
```

## Table of Content

## Documentation
The documentation of `pySpainMobility` classes and functions is available at [pyspainmobility.github.io/pySpainMobility](https://pyspainmobility.github.io/pySpainMobility)

<a id='installation'></a>
## Installation
`pySpainMobility` supports Python >= 3.9 and can be installed with `pip` or `conda`.

<a id='installation_pip'></a>
### installation with pip (python >= 3.9 required)

1. Create an environment `venv`

        python3 -m venv venv

2. Activate the environment

        source venv/bin/activate

3. Install `pySpainMobility`

        pip install pyspainmobility

<a id='installation_conda'></a>
### installation with conda - miniconda

1. Create an environment `mobility` and install pip

        conda create -n mobility pip python=3.9

2. Activate

        conda activate mobility

3. Install `pySpainMobility`

        conda install -c pyspainmobility pyspainmobility

<a id='examples'></a>
## Examples

Examples can be found in the repository named [Examples](https://github.com/pySpainMobility/examples)

## What's New in 1.1.0

- Added `backend` selection in `Mobility` (`backend="arrow"` by default, `backend="pandas"` supported).
- Added automatic fallback from Arrow to pandas with a warning when `pyarrow` is unavailable.
- Improved data preprocessing robustness and column normalization/translation.
- Improved loading behavior when using custom `output_directory` paths.
- Aligned download behavior between `Mobility` and `Zones` with lazy data fetching.

## Backend Selection

```python
from pyspainmobility import Mobility

mobility = Mobility(
    version=2,
    zones="municipalities",
    start_date="2022-01-01",
    end_date="2022-01-03",
    backend="arrow",  # default
)
```

If `backend="arrow"` is selected but `pyarrow` is not installed, `pySpainMobility` automatically falls back to `pandas` and emits a warning.


### Working with R?

If you prefer R, check out the [spanishoddata](https://github.com/rOpenSpain/spanishoddata) package by Egor Kotov et al.
