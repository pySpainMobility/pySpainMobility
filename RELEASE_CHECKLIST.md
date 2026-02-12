# Release Checklist

Use this checklist for every release so pip and conda stay aligned.

1. Ensure all version files match:
   - `setup.py`
   - `pyspainmobility/__init__.py`
   - `conda-recipes/pyspainmobility/meta.yaml`
2. Run version sync check:
   - `python scripts/check_version_sync.py`
3. Run tests:
   - `pytest -q`
4. Build and validate PyPI artifacts:
   - `python -m build`
   - `python -m twine check dist/*`
5. Build conda artifact:
   - `conda build conda-recipes/pyspainmobility`
6. Push code and tag:
   - `git push origin main`
   - `git push origin vX.Y.Z`
7. Publish PyPI:
   - `python -m twine upload dist/*`
8. Publish conda:
   - `anaconda upload /home/ciro/miniconda3/conda-bld/noarch/pyspainmobility-X.Y.Z-py_0.conda`
9. Verify published versions:
   - `python -c "import json,urllib.request as u;print(json.load(u.urlopen('https://pypi.org/pypi/pyspainmobility/json'))['info']['version'])"`
   - `conda search -c pyspainmobility pyspainmobility`
