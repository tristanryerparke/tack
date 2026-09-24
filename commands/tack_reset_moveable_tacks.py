#! python 3
"""Rhino command entry point for resetting child-movable Tacks."""

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
    "reset_moveable_tacks",
    __rhino_doc__,  # noqa: F821 - injected by Rhino's Script Editor
    reload_modules=PluginBridge.IsDevelopmentMode,
)
