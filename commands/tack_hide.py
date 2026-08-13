import importlib
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import Rhino
from Rhino.Commands import Result

import tack

importlib.reload(tack).reload()

from tack import runtime
from tack import utils


def RunCommand(is_interactive):
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return Result.Cancel

    if not runtime.hide_display(doc):
        print("No active Tack display to hide.")
        return Result.Cancel

    utils.set_document_display_enabled(doc, False)
    doc.Views.Redraw()
    print("Tack display hidden.")
    return Result.Success


if __name__ == "__main__":
    from tack.watcher import run_entrypoint

    run_entrypoint(lambda: RunCommand(True), utils.DEBUG)
