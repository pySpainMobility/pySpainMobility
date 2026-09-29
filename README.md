# pySpainMobility

**Access, download and standardise Spain's official mobility data.**

![pySpainMobility logo](https://raw.githubusercontent.com/pySpainMobility/pySpainMobility/refs/heads/main/logo_small.png)

pySpainMobility provides a Python interface to mobility observations and
geographic zones published by the
[Spanish Ministry of Transportation and Sustainable Mobility](https://www.transportes.gob.es).
Its core classes are:

- **[Mobility](https://pyspainmobility.github.io/pySpainMobility/reference/mobility.html):**
  download and process origin-destination trips, overnight stays and trip-count
  distributions.
- **[Zones](https://pyspainmobility.github.io/pySpainMobility/reference/zones.html):**
  load geometries, names, populations and territorial correspondences.
- Both classes support districts and municipalities, plus large urban areas
  in version 2. Derived provincial products are also available.
- Network helpers use the processed flows for sparse matrices, flow measures,
  temporal comparisons and spatial aggregation.

See the [documentation](https://pyspainmobility.github.io/pySpainMobility/)
for parameters, outputs and runnable examples. The website follows `main`;
check the [release history](https://pypi.org/project/pyspainmobility/#history)
for features available in your installed version.

<a id="installation"></a>
## Installation

Version 2.1.1 requires **Python 3.10 or newer**.

<a id="installation_pip"></a>
### pip

```bash
python -m pip install pyspainmobility
```

The base installation includes Mobility, Zones, Polars and SciPy sparse
networks. Add optional dependencies when needed:

| Extra | Install command | Use |
| --- | --- | --- |
| Arrow | `pip install 'pyspainmobility[arrow]'` | Arrow processing or reading Parquet with pandas |
| Dask | `pip install 'pyspainmobility[dask]'` | Dask processing |
| NetworkX | `pip install 'pyspainmobility[network]'` | External graph algorithms |
| Infomap | `pip install 'pyspainmobility[infomap]'` | External community detection |

The default Polars path does not require these extras.

<a id="installation_conda"></a>
### conda

```bash
conda install -c conda-forge pyspainmobility
```

Conda-forge releases depend on its feedstock checks and may lag behind PyPI.
Check the version being installed. To use the PyPI release in a conda
environment:

```bash
conda create -n mobility python=3.11 pip
conda activate mobility
python -m pip install pyspainmobility
```

<a id="examples"></a>
## Quick start: mobility data and zones

This example downloads one day of municipality-level trips and loads its
geographic context. It requires access to the MITMA server.

```python
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
```

- `od` is a pandas DataFrame containing dates, hours, origin/destination IDs,
  trip counts and total trip-kilometres. A processed Parquet file is also saved.
- `geometries` is a GeoDataFrame indexed by the zone IDs used in the flows.
- `get_overnight_stays_data()` retrieves overnight stays in version 2;
  `get_number_of_trips_data()` retrieves trip-count distributions.
- Use the same source version and zoning level for Mobility and Zones.

### Select dimensions and flows

The following example reuses `mobility` from the quick start:

```python
from pyspainmobility import select_od

detailed_od = mobility.get_od_data(return_df=True, dimensions=["age", "gender"])
morning = select_od(
    detailed_od,
    filters={"hour": [8, 9]},
    group_by=["id_origin", "id_destination"],
).collect()
print(morning.head())
```

- Requested dimensions are retained as aggregation keys. Missing category
  values retain their flows.
- If a requested dimension is absent from a source file, the error names the
  exact day and dimension, including when `allow_partial=True`.
- `select_od()` accepts pandas/Polars data or a saved Parquet path. Grouping
  sums trip counts and total trip-kilometres.
- Missing or invalid source days raise by default. Explicit partial results
  exclude failed days, record them in acquisition manifests and use a
  `_partial` filename suffix.

See the [Mobility reference](https://pyspainmobility.github.io/pySpainMobility/reference/mobility.html)
for supported dimensions, product availability and acquisition reports.

### Derived provincial products

```python
from pyspainmobility import Mobility, Zones

mobility = Mobility(version=2, zones="provinces", start_date="2024-01-01")
provincial_od = mobility.get_od_data(return_df=True)
provinces = Zones(version=2, zones="provinces").get_zone_geodataframe()

print(provincial_od.attrs["spatial"])
print(provinces.index)
```

- Provincial products are computed from district sources using verified
  territorial relations. IDs are two-digit INE province codes, including
  Ceuta (`51`) and Melilla (`52`).
- Dates, hours, selected categories and internal flows are retained.
- Unmappable territories are explicitly excluded. Warnings, acquisition
  manifests and provenance report excluded trips, trip-kilometres or people.
- Province geometries are dissolved MITMA territories, **not official province
  boundaries**. See the [Zones reference](https://pyspainmobility.github.io/pySpainMobility/reference/zones.html)
  for mapping validation and geometry exclusions.

## Network analysis

Once flows are available, build a sparse network. This small example runs
with the base installation and requires no download:

```python
import polars as pl
from pyspainmobility import build_network, node_strengths

example_od = pl.DataFrame({
    "id_origin": ["A", "A", "B"],
    "id_destination": ["B", "B", "A"],
    "n_trips": [3.0, 2.0, 4.0],
})
network = build_network(example_od)

print(network.total_weight)  # 9.0
print(node_strengths(network).rows())
# [('A', 5.0, 4.0, 9.0), ('B', 4.0, 5.0, 9.0)]
```

- Repeated OD pairs are summed; the default weight is `n_trips`.
- `network.adjacency` is a SciPy CSR matrix. `network.node_ids` gives its order.
- `node_strengths()` reports outgoing, incoming and total flow by zone.
- `network.audit()` records construction rules and flow accounting.

Follow the [network examples](https://pyspainmobility.github.io/pySpainMobility/network.html)
for selection, observed-day means, comparisons, spatial aggregation and
isolated nodes. Each example explains its expected output.
[NetworkX and Infomap adapters](https://pyspainmobility.github.io/pySpainMobility/reference/network_adapters.html)
connect these results to algorithms supplied by those projects.

## Backend selection

The default `backend="auto"` uses Polars, with Arrow and pandas as runtime
fallbacks. Explicit `backend="polars"`, `"arrow"` and `"pandas"` are available.

- `return_df=True` returns pandas data with or without optional Arrow.
- `return_df=False` writes the processed output without materialising a pandas
  DataFrame.
- `use_dask=True` is ignored on the Polars path, which already processes
  multiple files through a parallel lazy pipeline.

## Repository and development

- `pyspainmobility/`: published library code.
- `tests/`: automated tests; live MITMA downloads are opt-in.
- `docs/`: Sphinx documentation sources.
- `examples/`: portable demonstrations; generated outputs stay local.
- `scripts/`: release checks and figure generators.

Downloads, analysis outputs, virtual environments and build artifacts are
ignored by Git and are not part of the pip package.

Run `python -m pytest -q` for the test suite. CI checks Python 3.10–3.12,
minimum supported dependencies, optional adapters and installation without
extras. API and guide examples are also checked.
Enable real-source tests with `PYSPAINMOBILITY_RUN_LIVE_TESTS=1`.
See [CHANGELOG.md](CHANGELOG.md) for release history.

## Citation

If you use this package in research, please cite the
[paper](https://arxiv.org/abs/2506.13385):

```bibtex
@misc{beneduce2025pyspainmobility,
    title={pySpainMobility: a Python Package to Access and Manage Spanish Open Mobility Data},
    author={Ciro Beneduce and Tania Gullón Muñoz-Repiso and Bruno Lepri and Massimiliano Luca},
    year={2025},
    eprint={2506.13385},
    archivePrefix={arXiv},
    primaryClass={cs.CY},
    url={https://arxiv.org/abs/2506.13385}
}
```

For R users, [spanishoddata](https://github.com/rOpenSpain/spanishoddata)
provides another interface to these datasets.
