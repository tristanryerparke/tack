import importlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "glue"))

import Rhino
import System
from Rhino.Commands import Result

import glue_frame_picker
import glue_link

importlib.reload(glue_frame_picker)
importlib.reload(glue_link)


def _same_id(left, right):
    return str(left).lower() == str(right).lower()


def RunCommand(is_interactive):
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return Result.Cancel

    glue_link.stop_runtime()
    glue_link.stop_coincident_runtime()
    for child in doc.Objects:
        if child is None:
            continue
        coincident_link = glue_link.read_coincident_link(child)
        if coincident_link is not None:
            try:
                parent_id = System.Guid.Parse(str(coincident_link["parent_id"]))
            except Exception:
                parent_id = None
            parent = doc.Objects.Find(parent_id) if parent_id is not None else None
            if parent is not None:
                try:
                    stored_child_id = parent.Attributes.UserDictionary[
                        glue_link.COINCIDENT_CHILD_KEY
                    ]
                except Exception:
                    stored_child_id = None
                if _same_id(stored_child_id, child.Id):
                    if glue_link.start_coincident_runtime(parent.Id, child.Id):
                        print("Coincident vertex relationship restored.")
                        return Result.Success

        link = glue_link.read_link(child)
        if link is None:
            continue
        try:
            parent_id = System.Guid.Parse(str(link["parent_id"]))
        except Exception:
            continue

        parent = doc.Objects.Find(parent_id)
        if parent is None:
            print("Saved parent {} no longer exists.".format(parent_id))
            continue

        try:
            stored_child_id = parent.Attributes.UserDictionary[glue_link.CHILD_KEY]
        except Exception:
            print("Parent {} has no saved child GUID.".format(parent.Id))
            continue
        if not _same_id(stored_child_id, child.Id):
            print("Parent/child metadata mismatch; relationship skipped.")
            continue

        glue_link.start_runtime(parent.Id, child.Id)
        print("Plane relationship restored.")
        print("Parent GUID: {}".format(parent.Id))
        print("Child GUID: {}".format(child.Id))
        return Result.Success

    print("No saved Tack relationship found.")
    return Result.Cancel


if __name__ == "__main__":
    RunCommand(True)
