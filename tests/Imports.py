#!/usr/bin/env python3
"""
test_imports.py

A quick smoke‐test for the pyspainmobility package.
"""

import pyspainmobility
from pyspainmobility import Zones, Mobility
from pyspainmobility.utils import utils

def main():
    print("✅ pyspainmobility version:", pyspainmobility.__version__)
    print("✅ Zones class:", Zones)
    print("✅ Mobility class:", Mobility)
    # List publicly exposed members in utils
    util_funcs = [name for name in dir(utils) if not name.startswith("_")]
    print("✅ utils module contains:", util_funcs)

if __name__ == "__main__":
    main()
