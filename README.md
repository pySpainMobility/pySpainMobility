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
`pySpainMobility` can be installed with `pip` or `conda`. Version 2.1.0 requires
Python >= 3.10 and includes the patched GeoPandas dependency.

<a id='installation_pip'></a>
### installation with pip (Python >= 3.10)

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
Tests are grouped by domain: mobility/zones, networks, provincial products and
utilities. Parametrization checks the same contract across backends and source
versions. CI runs the core suite on Python 3.10–3.12, optional adapters once on
Python 3.11, and base-install checks in an environment without optional extras.
Use `python -m pytest -q -m network_adapter` or
`python -m pytest -q -m minimal_install` to select those groups locally.
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

### Selecting OD dimensions and flows

Pass `dimensions` to retain only the optional categories needed for an
analysis. Supported names are `activity_origin`, `activity_destination`,
`residence_province_ine_code`, `distance`, `income`, `age`, and `gender`.
Requested categories become aggregation keys; missing category values keep
their flows. `distance` is the source's distance category, not kilometres.
The existing `keep_activity` and `social_agg` flags remain valid,
but cannot be combined with `dimensions`.
If a requested column is absent from a source file, processing raises a
`ValueError` naming the exact day and dimension, even with `allow_partial=True`.
Adjust the requested dates or dimensions before retrying.

```python
od = mobility.get_od_data(
    dimensions=["income", "residence_province_ine_code"], return_df=True
)

from pyspainmobility import select_od

flows = select_od(
    od,
    filters={"income": "10-15", "hour": [8, 9]},
    group_by=["id_origin", "id_destination"],
).collect()
```

`select_od()` accepts the saved Parquet path directly for lazy, memory-efficient
scanning. Filters match exact values; `None` selects a missing category.
`group_by` sums both `n_trips` and `trips_total_length_km`. With no `group_by`,
the selected rows remain at their original granularity. Filtering happens
after source validation, so an empty subset does not turn a valid source day
into a reported download failure.

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
representation remains the canonical format; the Infomap adapter consumes
it directly without a NetworkX conversion.

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

To derive a validated province mapping from official MITMA relations, use
`Zones`. Province geometries are not a native zoning level: the
helper derives the two-digit INE province code from the five-digit INE
municipality code and rejects ambiguous territorial relations rather than
arbitrarily choosing one.
`get_province_mapping()` selects the source IDs for the object's zoning level
and supports versions 1 and 2. A zone containing several municipalities is
accepted when all belong to the same province. Missing or invalid municipality
codes and zones spanning multiple provinces raise an error identifying the
affected source IDs. Pass `source_ids` to validate only the zones in your data.
Code validation checks the five-digit format and the
[INE province prefixes 01–52](https://www.ine.es/daco/daco42/codmun/cod_ccaa_provincia.htm),
including Ceuta and Melilla; it does not check historical municipality registries.

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


### Derived provincial products

Use `zones="provinces"` with `Mobility` to derive province-level OD,
overnight-stay and trip-count products from MITMA district sources:

```python
mobility = Mobility(version=2, zones="provinces", start_date="2024-01-01")
od = mobility.get_od_data(return_df=True, dimensions=["age", "gender"])
print(mobility.get_acquisition_manifest("Viajes"))
print(od.attrs["spatial"])
```

Province IDs are two-digit INE codes, including `51` (Ceuta) and `52` (Melilla).
Hours, dates, selected dimensions, missing category values and intra-province
flows are retained. Trips and original trip-kilometres are summed; distances
are not recalculated from province centroids. Trip-count distributions retain
each `number_of_trips` category and sum its people counts across districts.
Version 1 supports OD and trip counts; overnight stays remain unavailable.

Zones without a unique province, including foreign zones and incomplete
territorial relations, are **explicitly excluded**. An OD/overnight row is
excluded when either geographic endpoint is unmappable. A warning is emitted;
the returned DataFrame `attrs`, per-day acquisition manifest and adjacent
`*.parquet.provenance.json` report excluded rows and trips/kilometres or people.
The row counts describe processed source rows, after the existing OD grouping.
Failed source days remain governed separately by `allow_partial`.

Output filenames contain `provinces_derived`. Raw downloads retain district
filenames and can be reused by district-level analyses. The transformation
uses existing dependencies and tabular mapping/aggregation without a graph
or fine-resolution matrix intermediate.

`Zones(zones="provinces", version=2).get_zone_geodataframe()` dissolves mapped
district geometries. Its string `id` index contains province codes, its CRS is
preserved, and population is summed when available (missing population stays
unknown). Unmapped zones and geometry repairs are reported in `attrs`.
These derived boundaries exclude unmappable territories and are **not an
official province-boundary dataset**. The dissolved result is cached on the
`Zones` instance.

The lower-level `get_province_mapping()` remains strict by default. Pass
`unmapped="exclude"` to obtain only exact mappings and inspect
`mapping.attrs["unmapped_source_ids"]` for excluded source IDs.

### Working with R?

If you prefer R, check out the [spanishoddata](https://github.com/rOpenSpain/spanishoddata) package by Egor Kotov et al.
