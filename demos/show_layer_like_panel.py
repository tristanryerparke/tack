"""Run inside Rhino to open the floating layer-panel mock."""

import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import layer_like_panel.panel as panel_module
importlib.reload(panel_module)
import layer_like_panel.runtime as runtime_module
importlib.reload(runtime_module)
from layer_like_panel.runtime import open_panel
from run_in_rhino.rhino_env.parasite import OutputParasite

try:
    from run_in_rhino.rhino_env.client import SocketConnection

    connection = SocketConnection()
except Exception:
    connection = None


if __name__ == "__main__":
    with OutputParasite(connection, done_msg=True):
        open_panel()
