#!/usr/bin/env python3
"""
Fail if package versions are not aligned across packaging metadata files.
"""

from pathlib import Path
import re
import sys


def _extract(pattern: str, text: str, source: Path) -> str:
    match = re.search(pattern, text, flags=re.MULTILINE)
    if not match:
        raise ValueError(f"Could not extract version from {source}")
    return match.group(1)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    setup_py = root / "setup.py"
    init_py = root / "pyspainmobility" / "__init__.py"
    conda_meta = root / "conda-recipes" / "pyspainmobility" / "meta.yaml"

    versions = {
        "setup.py": _extract(r'version\s*=\s*"([^"]+)"', setup_py.read_text(encoding="utf-8"), setup_py),
        "pyspainmobility/__init__.py": _extract(
            r'__version__\s*=\s*"([^"]+)"', init_py.read_text(encoding="utf-8"), init_py
        ),
        "conda-recipes/pyspainmobility/meta.yaml": _extract(
            r'{%\s*set\s+version\s*=\s*"([^"]+)"\s*%}',
            conda_meta.read_text(encoding="utf-8"),
            conda_meta,
        ),
    }

    unique_versions = set(versions.values())
    if len(unique_versions) != 1:
        print("Version mismatch detected:")
        for file_name, version in versions.items():
            print(f"- {file_name}: {version}")
        return 1

    version = unique_versions.pop()
    print(f"Version sync OK: {version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
