#! python 3
"""Reload Tack's development panel inside an already-running Rhino instance."""

import importlib
import sys

import Rhino
import System

from run_in_rhino.rhino_env.client import SocketConnection
from run_in_rhino.rhino_env.parasite import OutputParasite
from TackRhinoPlugin import PluginBridge


PACKAGE_NAME = "tack"
PANEL_MODULE_NAME = PACKAGE_NAME + ".panel"
PANEL_ID = System.Guid("F793A6F1-E37C-4F3C-A39A-65D4F720E8D2")


def reload_panel():
    """Rebuild panel content from the checkout for the active document."""
    if not PluginBridge.IsDevelopmentMode:
        raise RuntimeError("Panel reload is only available in development mode")

    document = Rhino.RhinoDoc.ActiveDoc
    if document is None:
        raise RuntimeError("Open a Rhino document before reloading the panel")

    importlib.import_module(PACKAGE_NAME)
    module_names = sorted(
        (
            name
            for name in tuple(sys.modules)
            if name.startswith(PACKAGE_NAME + ".")
        ),
        key=lambda name: name.count("."),
        reverse=True,
    )
    for module_name in module_names:
        module = sys.modules.get(module_name)
        parent_name, _, child_name = module_name.rpartition(".")
        parent = sys.modules.get(parent_name)
        if parent is not None and getattr(parent, child_name, None) is module:
            delattr(parent, child_name)
        sys.modules.pop(module_name, None)

    importlib.invalidate_caches()
    panel_module = importlib.import_module(PANEL_MODULE_NAME)
    Rhino.UI.Panels.OpenPanel(PANEL_ID)
    panel_module.install(document.RuntimeSerialNumber)
    Rhino.RhinoApp.WriteLine(
        "Reloaded Tack panel from source with {} module(s).".format(
            len(module_names)
        )
    )


if __name__ == "__main__":
    try:
        connection = SocketConnection()
    except Exception:
        connection = None
    with OutputParasite(connection, done_msg=True):
        reload_panel()
