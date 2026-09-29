# Release Checklist

Use this checklist for every release so pip and conda stay aligned.

1. Ensure all version files match:
   - `setup.py`
   - `pyspainmobility/__init__.py`
   - `conda-recipes/pyspainmobility/meta.yaml`
   - Sync conda runtime dependencies with the base pip dependencies; optional
     pip extras must not remain mandatory in the conda recipe.
2. Run version sync check:
   - `python scripts/check_version_sync.py`
3. Run tests:
   - `pytest -q`
   - Optional live smoke test (real MITMA download/parsing pipeline): `PYSPAINMOBILITY_RUN_LIVE_TESTS=1 pytest -q tests/test_live_pipeline_smoke.py`
4. Build and validate PyPI artifacts in a version-specific directory:
   - `python -m build --outdir dist/X.Y.Z`
   - `python -m twine check dist/X.Y.Z/*`
5. Record the SHA-256 of the exact source archive to upload and set it in `conda-recipes/pyspainmobility/meta.yaml`:
   - `shasum -a 256 dist/X.Y.Z/pyspainmobility-X.Y.Z.tar.gz`
6. Push code and tag:
   - `git push origin main`
   - `git push origin vX.Y.Z`
7. Publish PyPI:
   - `python -m twine upload --username __token__ dist/X.Y.Z/*`
8. Update conda-forge only after PyPI exposes that exact sdist:
   - Update `recipe/meta.yaml` in a fork of
     `conda-forge/pyspainmobility-feedstock`, matching the local recipe's
     version, SHA-256, Python minimum and base dependencies.
   - Reset the build number to zero for a new version.
   - Open a pull request to the feedstock and rerender its CI configuration
     if required. Check for an existing update PR before creating a duplicate.
   - After the feedstock checks pass, merge the update. Its CI builds and
     publishes the package to conda-forge automatically.
9. Verify published versions:
   - `python -c "import json,urllib.request as u;print(json.load(u.urlopen('https://pypi.org/pypi/pyspainmobility/json'))['info']['version'])"`
   - `conda search -c conda-forge pyspainmobility`
10. Verify docs website:
    - Ensure repository Settings > Pages is configured to "GitHub Actions"
    - Confirm latest `documentation` workflow finished with deploy success
    - Open `https://pyspainmobility.github.io/pySpainMobility/`

## Release 2.1.1: manual PyPI publication

The corrected artifacts are in `dist/2.1.1/`. The source archive and wheel
match the audited code; their metadata passed `twine check`.

- Development suite: 312 passed; two opt-in live tests skipped in this run.
- Installed wheel with current and minimum dependencies: 309 core tests
  passed in each environment; optional adapters excluded from those runs.
- Clean base installation: four tests and 11 API examples passed without
  Arrow, Dask, NetworkX or Infomap; `pip check` passed.
- Documentation: strict HTML build, 11 API examples and seven guide examples
  passed. The README's offline network example also ran successfully.
- Source SHA-256: `b6d59af5be397a1016839e87afad5eb278a9c551d6e7f431083115132099cae8`.
- Wheel SHA-256: `467e00aae97568119425c82bd71b5e5e7afdc5e299a5d0995113cf518b0cb4d4`.
- Conda-forge update: [PR #8](https://github.com/conda-forge/pyspainmobility-feedstock/pull/8).

From the repository directory, upload the verified artifacts:

```bash
.venv/bin/python -m twine upload --username __token__ \
  dist/2.1.1/pyspainmobility-2.1.1-py3-none-any.whl \
  dist/2.1.1/pyspainmobility-2.1.1.tar.gz
```

Enter your PyPI token at the password prompt. Confirm the release exists:

```bash
.venv/bin/python -c "import json,urllib.request as u;print(json.load(u.urlopen('https://pypi.org/pypi/pyspainmobility/2.1.1/json'))['info']['version'])"
```

Keep the conda PR in draft until PyPI serves this exact source archive. Then
mark it ready, rerun failed source-download checks and merge after checks pass.
Feedstock CI publishes the conda package automatically. If the source archive
is rebuilt, update its SHA-256 in both recipes before proceeding.

### Superseded 2.1.0 artifacts

The original artifacts in `dist/2.1.0-pre-audit/` omit the later audit fixes;
**do not upload them**. The existing `v2.1.0` Git tag is preserved.
