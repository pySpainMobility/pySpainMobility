# Paper use case: income layers and inter-province mobility

The three notebooks reproduce the paper's use case and supplementary analyses with **pySpainMobility 2.1.2**. They include outputs from a verified run, brief explanations, intermediate summaries, and numerical checks. The public workflow downloads and prepares its own inputs; raw data, caches, environments, and generated files are excluded from Git.

| Notebook | Contents |
| --- | --- |
| [00_download_and_build_graphs.ipynb](00_download_and_build_graphs.ipynb) | Daily acquisition, demographic selection, sample inspection, sparse district networks, and graph audit |
| [01_prepare_analysis_inputs.ipynb](01_prepare_analysis_inputs.ipynb) | Validated district-to-province mapping, representative distance points, derived province geometries, and geographic filtering audit |
| [02_main_paper_analysis.ipynb](02_main_paper_analysis.ipynb) | Concentration and destination rankings, spatial reach, arrival composition, geographic benchmark, geographic overlap, and district–province sensitivity |

## Run in JupyterLab or VS Code

From the repository root:

```bash
cd examples/paper
bash setup_env.sh
source .venv-paper/bin/activate
jupyter lab
```

Select **Python (pySpainMobility paper final)** and run **00 → 01 → 02**, each from a fresh kernel. In VS Code, open this folder and select `.venv-paper/bin/python` through **Select Kernel → Python Environments**. The setup script also works when invoked from another directory; start the notebooks from this folder.

Python 3.11 is the tested runtime. `requirements.txt` installs the pinned package release and the required notebook/data dependencies. `requirements.lock.macos-py311.txt` records the exact full environment used for validation on macOS with Python 3.11.14; it includes optional adapters and platform-specific packages. To recreate that environment on the matching platform:

```bash
PYSPAIN_REQUIREMENTS_FILE="$PWD/requirements.lock.macos-py311.txt" bash setup_env.sh
```

## Data and outputs

The study windows are 16–22 January, 8–14 May, 17–23 July, and 9–15 October 2023. The sample retains positive expanded trip weights with nonmissing income, age, and gender and one of the three income bands. Income describes residential socioeconomic context. The main analysis retains missing residence; the benchmark uses known residence. All 52 province-level units enter the numerical analysis.

The first run requires access to the Ministry's mobility/geography servers and processes 28 district-level daily files. This is the full paper workflow, rather than a small synthetic example. Subsequent runs reuse validated daily caches after checksum and package/source fingerprint checks. Set `PYSPAIN_FORCE_REPARSE=1` to repeat acquisition and processing through Mobility.

Generated files stay inside this folder:

- `raw_data/`: optional existing source files; notebook 00 also downloads into its acquisition folder when needed.
- `outputs/paper_inputs/`: daily caches, sparse district graphs, geography/reference products, and provenance.
- `outputs/paper_revision/`: result tables, figures, network audits, and rebuilt working OD tables.

For another layout, set `PYSPAIN_PAPER_DIR`, `PYSPAIN_RAW_DATA_DIR`, `PYSPAIN_PIPELINE_OUTPUT`, or `PYSPAIN_NOTEBOOK_OUTPUT` before starting the kernel. `PYSPAIN_CACHE_REUSE_DIR` can point to an existing validated input folder; it is optional, and imported caches are copied into this workflow's own cache directory.

`reference_tables/` contains frozen numerical checks, not analysis inputs. Notebook 02 recomputes every result from the prepared daily data and geography. The complete workflow was validated in fresh Jupyter kernels against the existing 28 daily caches, 16 sparse network matrices, geographic products, and all 16 numerical result tables. A separate uncached acquisition check reproduced the validated 16 January input. A cold download of all 28 days was not repeated for publication.

## Reading the analysis

Notebook 02 follows the paper: sample and networks → concentration and hierarchy → spatial reach → arrival composition → geographic benchmark and overlap → spatial aggregation. Each section shows its own calculations, tables/plots, and checks. The concentration figures retain all three income layers and every cutoff; low income is orange, middle income blue, and high income green. District overrepresentation is exported as PNG.

Distances are Euclidean separations between district representative points in EPSG:25830, not route lengths. The geographic benchmark preserves income-layer volumes within departure-district × recorded-residence-province combinations and assigns their pooled destination proportions to all layers. It is a descriptive standardization. District/province sensitivity holds the selected inter-province trip population fixed.

Code is covered by the repository's [BSD 3-Clause licence](../../LICENSE). Mobility/geography data remain subject to their provider's terms. For the paper citation, see the repository [citation section](../../README.md#citation).
