import importlib
import os
import sys

import Rhino
from Rhino.Commands import Result

TACK_ROOT = "/Users/tristanryerparke/projects-local/tack"
if TACK_ROOT not in sys.path:
    sys.path.insert(0, TACK_ROOT)

from ondsel.assembly import assembly_model
from ondsel.assembly import assembly_scheduler

assembly_model = importlib.reload(assembly_model)
assembly_scheduler = importlib.reload(assembly_scheduler)


def RunCommand(is_interactive):
    if Rhino.RhinoDoc.ActiveDoc is None:
        return Result.Cancel
    assembly_model.subscribe()
    print("[Ondsel assembly] EndCommand handler subscribed.")
    return Result.Success


if __name__ == "__main__":
    from tack.watcher import run_entrypoint

    run_entrypoint(lambda: RunCommand(True), True)
