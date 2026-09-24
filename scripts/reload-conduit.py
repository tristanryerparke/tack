#! python 3
"""Reload Tack's display conduit inside an already-running Rhino instance."""

import importlib

import Rhino
from TackRhinoPlugin import PluginBridge

from run_in_rhino.rhino_env.client import SocketConnection
from run_in_rhino.rhino_env.parasite import OutputParasite
from tack.display import drawing, link_conduit
from tack.links import runtime, state


def reload_conduit():
    """Rebuild the live conduit from the development checkout."""
    if not PluginBridge.IsDevelopmentMode:
        raise RuntimeError("Conduit reload is only available in development mode")

    runtime.remove_conduit()
    importlib.reload(drawing)
    importlib.reload(runtime)
    importlib.reload(link_conduit)

    restored = 0
    for document in Rhino.RhinoDoc.OpenDocuments(False):
        if state.states(document, create=False):
            runtime.ensure_conduit(document, runtime.display_enabled(document))
            restored += 1
        document.Views.Redraw()

    Rhino.RhinoApp.WriteLine(
        f"Reloaded Tack display conduit for {restored} document(s)."
    )


if __name__ == "__main__":
    document = Rhino.RhinoDoc.ActiveDoc
    if document is None:
        raise RuntimeError("Open a Rhino document before reloading the conduit")
    try:
        connection = SocketConnection()
    except Exception:  # noqa: BLE001 - output server is optional
        connection = None
    with OutputParasite(connection, done_msg=True):
        reload_conduit()
