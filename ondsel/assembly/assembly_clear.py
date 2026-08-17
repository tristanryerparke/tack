import importlib
import os
import sys

import Rhino
from Rhino.Commands import Result

TACK_ROOT = "/Users/tristanryerparke/projects-local/tack"
if TACK_ROOT not in sys.path:
    sys.path.insert(0, TACK_ROOT)

from ondsel.assembly import assembly_model

assembly_model = importlib.reload(assembly_model)


def RunCommand(is_interactive):
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return Result.Cancel
    assembly_model.unsubscribe()
    assembly_model.clear(doc)
    print("[Ondsel assembly] Cleared metadata and handlers.")
    doc.Views.Redraw()
    return Result.Success


if __name__ == "__main__":
    from tack.watcher import run_entrypoint

    run_entrypoint(lambda: RunCommand(True), True)
