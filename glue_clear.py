import importlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "glue"))

import Rhino
from Rhino.Commands import Result

import glue_link

importlib.reload(glue_link)


def _clear_object_metadata(doc, object_id):
    obj = doc.Objects.Find(object_id)
    if obj is None:
        return

    attrs = obj.Attributes.Duplicate()
    changed = False
    for key in (glue_link.LINK_KEY, glue_link.CHILD_KEY):
        try:
            if attrs.UserDictionary.ContainsKey(key):
                attrs.UserDictionary.Remove(key)
                changed = True
        except Exception:
            pass
    if changed:
        doc.Objects.ModifyAttributes(object_id, attrs, True)


def RunCommand(is_interactive):
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return Result.Cancel

    glue_link.stop_runtime()
    for obj in doc.Objects:
        if obj is not None:
            _clear_object_metadata(doc, obj.Id)

    doc.Views.Redraw()
    print("Glue cleared. Save the file to keep the cleanup.")
    return Result.Success


if __name__ == "__main__":
    RunCommand(True)
