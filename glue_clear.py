import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "glue"))

import glue_events
import glue_metadata

import Rhino
import scriptcontext as sc
from Rhino.Commands import Result

from glue_constants import STATE_KEY
from glue_events import reset_runtime_objects
from glue_metadata import clear_metadata


def RunCommand(is_interactive):
    reset_runtime_objects()
    sc.sticky.pop(STATE_KEY, None)

    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return Result.Cancel

    for obj in doc.Objects:
        if obj is not None:
            clear_metadata(doc, obj.Id)

    doc.Views.Redraw()
    print("Glue cleared. Save the file to keep the cleanup.")
    return Result.Success


if __name__ == "__main__":
    RunCommand(True)
