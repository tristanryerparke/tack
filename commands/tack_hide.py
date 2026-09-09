#! python 3
"""Rhino command entry point for hiding Tack display."""

import importlib
import sys

from TackRhinoPlugin import PluginBridge


python_root = str(PluginBridge.PythonRoot)
if python_root in sys.path:
    sys.path.remove(python_root)
sys.path.insert(0, python_root)

from tack import command_runtime

if PluginBridge.IsDevelopmentMode:
    command_runtime = importlib.reload(command_runtime)
result = command_runtime.run(
    "hide",
    __rhino_doc__,
    reload_modules=PluginBridge.IsDevelopmentMode,
)
