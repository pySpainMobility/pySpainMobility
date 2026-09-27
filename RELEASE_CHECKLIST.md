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

## Prepared release 2.1.0

The local artifacts in `dist/2.1.0/` have passed `twine check`. From the
repository root, upload them with:

```sh
.venv/bin/python -m twine upload --username __token__ dist/2.1.0/pyspainmobility-2.1.0.tar.gz dist/2.1.0/pyspainmobility-2.1.0-py3-none-any.whl
```

Enter the PyPI token when Twine asks for the password; do not put it in the
command or commit it to the repository. Upload these exact artifacts without
rebuilding: the conda recipe uses their source archive's SHA-256.

- Source SHA-256: `2f08fce67698ba533598a89ba6953f1f7d234fb312ca6cf79eac12b09a207e68`.
- Wheel SHA-256: `b8ef762f43ed8ca1564427a86e2723f06c380ed5117a608e439f923f8ded587d`.
- Conda-forge update: [PR #8](https://github.com/conda-forge/pyspainmobility-feedstock/pull/8).

After PyPI exposes version 2.1.0, mark the conda PR ready, rerun any failed
source-download checks, and merge only after its checks pass. Feedstock CI
then publishes the conda package; a local `anaconda upload` is not needed.
