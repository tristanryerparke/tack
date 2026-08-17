"""Load the newest versioned ondsel module.

The C++ wrapper is rebuilt as ondsel_v<timestamp> on each `build.sh` run.
A fresh module name always imports a fresh dylib image, dodging CPython's
per-interpreter extension cache inside Rhino (which cannot be reset without
restarting Rhino).
"""
import glob
import importlib
import os
import sys

MODULES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "rhino_modules",
)


def _candidates():
    pattern = os.path.join(MODULES_DIR, "ondsel_v*.so")
    return sorted(glob.glob(pattern), reverse=True)


def load():
    """Import the newest ondsel_v* module, preferring one not yet loaded."""
    if MODULES_DIR not in sys.path:
        sys.path.insert(0, MODULES_DIR)

    for path in _candidates():
        name = os.path.basename(path).split(".")[0]
        if name not in sys.modules:
            return importlib.import_module(name)

    # Every candidate is already imported this session; the newest import
    # matches the newest file, so reuse it.
    for path in _candidates():
        name = os.path.basename(path).split(".")[0]
        module = sys.modules.get(name)
        if module is not None:
            return module

    raise ImportError("No ondsel_v*.so found in " + MODULES_DIR)
