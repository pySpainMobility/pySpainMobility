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
11. Publish a GitHub Release from the existing version tag:
    - Use the changelog for release notes and attach the verified PyPI artifacts.

## Release 2.1.2: published

The pandas-input, empty-date-selection, CSR-validation and incomplete
zone-metadata fixes are included in the artifacts in `dist/2.1.2/`.

### Verification

- Development suite: 326 passed; two opt-in live tests skipped in this run.
- Installed wheel with current and minimum dependencies: 323 core tests
  passed in each environment; optional adapters excluded from those runs.
- Base installation without Arrow, Dask, NetworkX or Infomap: 14 new regression
  cases, four base-feature tests and 11 API examples passed; `pip check` passed
  in all three installed-wheel environments.
- Documentation: strict HTML build and seven guide examples passed.
- All 18 package modules in both archives match the release source; the wheel
  excludes tests, documentation, examples and downloaded data. Twine checks passed.
- Source SHA-256: `46bf02218a019f2415494ae4276d9b5d27fbcf615aca4f1ab8412655a3392b83`.
- Wheel SHA-256: `5df8bf4375ee52b1d2ec093f9d3bfc7bd9758db4fdd8663dceca35351999dc4f`.
- Conda-forge update: [PR #8](https://github.com/conda-forge/pyspainmobility-feedstock/pull/8).

### Publication status

Verified on 2026-10-02:

- [PyPI 2.1.2](https://pypi.org/project/pyspainmobility/2.1.2/): wheel and source
  archive published with the SHA-256 hashes recorded above.
- [Conda-forge 2.1.2](https://anaconda.org/conda-forge/pyspainmobility): the
  `noarch` package is published; feedstock PR #8 was merged on 2026-09-29.
- [Documentation](https://pyspainmobility.github.io/pySpainMobility/): version 2.1.2.
- [GitHub Release v2.1.2](https://github.com/pySpainMobility/pySpainMobility/releases/tag/v2.1.2):
  release notes and the verified PyPI artifacts accompany the existing tag.

### Superseded artifacts

The artifacts in `dist/2.1.0-pre-audit/` and `dist/2.1.1-pre-review/` omit later
audit fixes; **do not upload them**. Preserve the existing `v2.1.0` and
`v2.1.1` Git tags.
