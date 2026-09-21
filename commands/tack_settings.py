#! python 3
"""Rhino command entry point for Tack settings."""

import importlib
import sys

from TackRhinoPlugin import PluginBridge

python_root = str(PluginBridge.PythonRoot)
if python_root in sys.path:
    sys.path.remove(python_root)
sys.path.insert(0, python_root)

from tack.core import command_dispatch

if PluginBridge.IsDevelopmentMode:
    command_dispatch = importlib.reload(command_dispatch)
result = command_dispatch.run(
    "settings",
    __rhino_doc__,
    reload_modules=PluginBridge.IsDevelopmentMode,
)
