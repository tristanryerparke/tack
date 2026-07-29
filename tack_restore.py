import importlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "tack"))

import Rhino
import System
from Rhino.Commands import Result

import analysis
import conduit
import metadata
import link
import runtime
import handlers
import tack_frame_picker
import utils

importlib.reload(tack_frame_picker)
importlib.reload(utils)
importlib.reload(metadata)
importlib.reload(analysis)
importlib.reload(link)
importlib.reload(conduit)
importlib.reload(runtime)
importlib.reload(handlers)


def RunCommand(is_interactive):
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return Result.Cancel

    handlers.unsubscribe()
    runtime.stop_runtime()
    for child in doc.Objects:
        if child is None:
            continue
        coincident_link = metadata.read_link(child)
        if coincident_link is None:
            continue
        try:
            parent_id = System.Guid.Parse(str(coincident_link["parent_id"]))
        except Exception:
            continue

        parent = doc.Objects.Find(parent_id)
        if parent is None:
            print("Saved parent {} no longer exists.".format(parent_id))
            continue

        try:
            stored_child_id = parent.Attributes.UserDictionary[
                metadata.CHILD_KEY
            ]
        except Exception:
            print("Parent {} has no saved child GUID.".format(parent.Id))
            continue
        if not utils.same_id(stored_child_id, child.Id):
            print("Parent/child metadata mismatch; relationship skipped.")
            continue

        if runtime.start_runtime(parent.Id, child.Id):
            handlers.subscribe()
            print("Coincident vertex relationship restored.")
            return Result.Success

    print("No saved Tack relationship found.")
    return Result.Cancel


if __name__ == "__main__":
    RunCommand(True)
