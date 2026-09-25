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

## Documentation
The documentation of `pySpainMobility` classes and functions is available at [pyspainmobility.github.io/pySpainMobility](https://pyspainmobility.github.io/pySpainMobility)

<a id='installation'></a>
## Installation
`pySpainMobility` can be installed with `pip` or `conda`. The next release
will require Python >= 3.10. The published 2.0.0 package still uses the older
GeoPandas requirement; the security update needs a new package release.

<a id='installation_pip'></a>
### installation with pip (python >= 3.10 required for the next release)

1. Create an environment `venv`

        python3 -m venv venv

2. Activate the environment

        source venv/bin/activate

3. Install `pySpainMobility`

        pip install pyspainmobility

The base installation includes the Polars backend and the `Zones` class.
Optional Arrow and Dask backends can be installed when needed:

        pip install 'pyspainmobility[arrow]'
        pip install 'pyspainmobility[dask]'

These extras add sizeable dependencies; they are not needed for the default
Polars processing path. Install the `arrow` extra if you plan to read the
generated Parquet files with pandas. `matplotlib` is only needed for your own
plotting code.

<a id='installation_conda'></a>
### installation with conda - miniconda

1. Create an environment `mobility` and install pip

        conda create -n mobility pip python=3.10

2. Activate

        conda activate mobility

3. Install `pySpainMobility`

        conda install -c conda-forge pyspainmobility

<a id='examples'></a>
## Examples

Examples can be found in the repository named [Examples](https://github.com/pySpainMobility/examples)

## Repository layout

- `pyspainmobility/`: published library code.
- `tests/`: automated tests; live MITMA downloads are opt-in.
- `docs/`: Sphinx documentation sources.
- `examples/`: portable demonstrations; generated images and PDFs stay local.
- `scripts/`: release checks and reproducible figure generators.

Downloaded MITMA files, analysis outputs, virtual environments and build
artifacts are ignored by Git. They can make a local checkout much larger but
are not included in the pip package.

Run the local tests with `python -m pytest -q`. Live MITMA tests are disabled
by default and can be enabled with `PYSPAINMOBILITY_RUN_LIVE_TESTS=1`.
Release history is recorded in [CHANGELOG.md](CHANGELOG.md).

## Backend Selection

```python
from pyspainmobility import Mobility

mobility = Mobility(
    version=2,
    zones="municipalities",
    start_date="2022-01-01",
    end_date="2022-01-03",
    backend="auto",  # default: Polars, then Arrow, then pandas
)
```

The `auto` backend selects Polars by default, then Arrow and pandas only as
runtime fallbacks. Explicit backend selection remains available for
reproducible comparisons and backwards compatibility.

If `backend="arrow"` is selected but `pyarrow` is not installed,
`pySpainMobility` automatically falls back to `pandas` and emits a warning.

Polars is installed with the base package and can be selected explicitly when
needed:

```python
mobility = Mobility(
    version=2,
    zones="municipalities",
    start_date="2022-01-01",
    backend="polars",
)
```

The Polars backend keeps the public API compatible by returning a
`pandas.DataFrame` when `return_df=True`. With the `arrow` extra installed it
uses Arrow-backed pandas columns; without it, conversion uses Python values
and can be slower for large results. With `return_df=False`, the processed
result is written directly from Polars without materializing an intermediate
pandas DataFrame. `use_dask=True` is unnecessary and ignored when Polars is
selected because the lazy multi-file pipeline is already parallel.
Daily files are aligned by column name, even when their column order differs.
OD results are saved only after every requested daily download and source file
has been checked. A missing download or invalid OD day raises an error and is
recorded by `get_acquisition_manifest("Viajes")`. To work deliberately with
incomplete data, pass `allow_partial=True`: failed OD days are excluded, and
the saved filename ends in `_partial.parquet`. Overnight stays and trip counts
apply the same date-level source validation, including non-negative finite
people counts and agreement between each file's date and its requested day.

The default OD output retains its original filename. `keep_activity=True`
adds `_activity`, and `social_agg=True` adds `_social` before `.parquet`, so
running different analyses does not overwrite their files. For example,
`_v2_activity_social_partial.parquet` identifies an incomplete OD result with
both dimensions retained. Parquet output is written through a temporary file
and then moved into place, so an interrupted write does not leave a partly
written result at the final filename.

### Building sparse mobility networks

`pyspainmobility.network` turns a processed OD table into a directed, weighted
SciPy CSR matrix. Repeated OD rows are summed, `node_ids` is the explicit
row/column contract, and `audit()` records the represented flow and any
dropped self-loops.

```python
from pyspainmobility import NetworkSpec, build_network

network = build_network(
    "Viajes_municipalities_2022-01-01_2022-01-03_v2.parquet",
    spec=NetworkSpec(weight="n_trips", self_loops="keep"),
)

print(network.adjacency)       # SciPy CSR sparse matrix
print(network.node_ids)        # stable matrix-to-zone mapping
print(network.audit())         # flow accounting
```

The OD network is directed by construction. When an undirected representation
is scientifically appropriate, choose the transformation explicitly:

```python
from pyspainmobility import symmetrize_network

bilateral_flow = symmetrize_network(network, method="sum")
reciprocal_flow = symmetrize_network(network, method="mutual")
```

Available rules are `sum`, `mean`, `max`, and `mutual`. The resulting matrix
is symmetric, while `total_weight` and `to_edge_table()` count each logical
undirected edge once; the raw stored-matrix total remains in the audit trail.

For reproducible comparisons across periods or zoning editions, pass a named
node index instead of a bare list of IDs:

```python
from pyspainmobility import NodeIndex, build_network

municipal_v2 = NodeIndex(
    ["01001", "01002"],
    zoning_id="mitma_municipalities",
    zoning_version="v2",
)
network = build_network(od_dataframe, node_index=municipal_v2)
```

`network.align_to(other_index)` reorders a network only when the node universe
and zoning metadata are compatible. A different zoning identifier or version
is an error, not an implicit comparison.

For NetworkX algorithms or visualization, install `pyspainmobility[network]`
and use `pyspainmobility.network.integrations.to_networkx(network)`. The CSR
representation remains the canonical format, so future adapters such as
Infomap do not require a NetworkX conversion.

For community detection with Infomap, install `pyspainmobility[infomap]` and
run the adapter directly on that CSR matrix:

```python
from pyspainmobility.network.integrations import run_infomap

partition = run_infomap(network, seed=123, num_trials=10)
print(partition.communities())
```

The result retains the exact `NodeIndex`, Infomap version, options, and a
fingerprint of the matrix supplied to the algorithm. Mobility OD weights are
passed as directed edge weights to Infomap's random-walk model; they should not
be interpreted as the resulting random-walk flows.

### Sparse metrics and temporal comparisons

Metrics work directly on the canonical CSR representation and preserve the
`NodeIndex` contract when two networks use different valid node orderings.
Comparisons reject different weight fields or normalizations, such as raw
trip totals versus trips per observed day.

```python
from pyspainmobility import compare_networks, node_strengths

summary = compare_networks(network_before, network_after)
print(summary.edge_jaccard, summary.weighted_jaccard)
print(node_strengths(network_before))
```

`edge_changes(network_before, network_after)` returns only edges in the sparse
union, classified as added, removed, increased, decreased, or unchanged.
`destination_similarity(...)` returns a per-origin cosine similarity of the
destination-flow profile. For a temporal network, use
`compare_snapshots()`, `snapshot_edge_changes()`, and
`destination_stability()` with observed dates.

For an undirected network, `node_strengths()` counts a self-loop once as a
mobility flow. NetworkX's weighted degree counts an undirected self-loop twice.

### Temporal snapshots and data coverage

Build temporal networks from the same processed OD table with one shared node
index. Snapshots are evaluated only when requested and cached thereafter. To
compute per-day summaries correctly, pass both the requested study dates and
the dates whose source file was actually observed: this distinguishes a missing
file from an observed day with no OD rows.
Date, Datetime, and ISO timestamp string columns are normalized to calendar
days. Malformed dates are rejected rather than treated as empty observed days.

```python
from pyspainmobility import build_temporal_network

temporal = build_temporal_network(
    od_dataframe,
    requested_dates=["2024-01-01", "2024-01-02", "2024-01-03"],
    observed_dates=["2024-01-01", "2024-01-03"],
)

print(temporal.coverage.missing_source_dates)  # ("2024-01-02",)
network_on_jan_1 = temporal.snapshot("2024-01-01")
```

If `observed_dates` is omitted, availability is inferred from OD rows; the
library deliberately reports requested-but-absent dates as unresolved rather
than assuming that their flow is zero.

When the OD table was obtained with `Mobility`, prefer its acquisition record
over a manually assembled date list. The record distinguishes download status
(`available`, `failed`, `empty`) from `parse_status` (`valid`, `empty`, `failed`,
`not_processed`):

```python
od_dataframe = mobility.get_od_data(return_df=True)
temporal = build_temporal_network(
    od_dataframe,
    acquisition_manifest=mobility.get_acquisition_manifest("Viajes"),
)
```

With a `parse_status` column, only acquired files parsed as `valid` or genuinely
`empty` count as observed days. A downloaded file with invalid mandatory rows
does not enter the denominator as a zero-flow day. A manually supplied legacy
manifest without `parse_status` still treats `available` as observed; its
author must verify that parsing succeeded. The `coverage` field remains
`unverified` unless the upstream source provides a completeness guarantee.

If processed OD rows still exist for a manifest day marked `failed`, the
temporal builder raises by default. This prevents a partial day from entering
an observed-day average. After reviewing the data loss, callers may explicitly
remove all rows from such days with `failed_data_policy="exclude"`; the dates
and excluded flow weight remain in `temporal.audit()`. When excluded rows have
invalid weights, the weight total includes only finite, non-negative values;
`excluded_failed_invalid_row_count` reports how many excluded rows could not
be treated as valid OD observations.

Temporal aggregation uses that same definition of observation:

```python
total_network = temporal.sum_network()
daily_mean_network = temporal.mean_per_observed_day()
```

`mean_per_observed_day()` divides by all selected observed days, including
known empty days. It rejects dates with a failed or missing source file. This
is intentionally different from an active-day mean, which is not yet exposed
because it needs a separate per-edge observation contract.
The per-day normalization stays in network metadata through spatial
aggregation and directed-to-undirected conversion.

For long studies, pass a Hive-partitioned Parquet dataset directory, for
example `od/date=2024-01-01/part-0.parquet`. Polars can then prune partitions
when a snapshot is requested. Period sums and observed-day means aggregate OD
rows in one scan and do not populate the snapshot cache. Snapshots use an LRU
cache of 32 matrices by default; this bounds the number of cached days, not
their memory footprint. Set `max_cached_snapshots=0` to avoid retention or
`None` to retain all snapshots deliberately.
On a non-partitioned source, iterating every snapshot reads the source once
per date; partitioning is recommended when individual days will be queried.

### Spatial aggregation without losing flow

For a fine-resolution network already in memory, aggregation uses the sparse
projection `P.T @ A @ P`. If OD data are still available, use the data-first
function so that the zoning joins and group-by run in Polars before a CSR
matrix is created.

```python
from pyspainmobility import aggregate_od_network

mapping = {"01001": "province_04", "01002": "province_04"}
province_network = aggregate_od_network(od_dataframe, mapping)

print(province_network.audit()["provenance"]["spatial"])
```

Every fine node must have exactly one target zone. The audit reports flow that
becomes internal to an aggregated zone (`internalized_weight`), and any target
self-loops explicitly discarded with `self_loops="drop"`; neither is silently
lost. Provenance history also retains the accounting from initial network
construction, including source self-loops dropped before later transformations.

For an official, validated district-to-province correspondence, obtain the
mapping from `Zones`. Province geometries are not a native zoning level: the
helper derives the two-digit INE province code from the five-digit INE
municipality code and rejects ambiguous territorial relations rather than
arbitrarily choosing one.

```python
from pyspainmobility import Zones
from pyspainmobility.network import aggregate_network

zones = Zones(zones="districts", version=2, output_directory="data")
mapping = zones.get_province_mapping(source_ids=district_network.node_ids)
province_network = aggregate_network(
    district_network, mapping, self_loops="drop"
)
```

Use `self_loops="drop"` when the research question is explicitly
*inter-province* mobility: flows between distinct districts in the same
province become loops only after this aggregation.


### Working with R?

If you prefer R, check out the [spanishoddata](https://github.com/rOpenSpain/spanishoddata) package by Egor Kotov et al.
