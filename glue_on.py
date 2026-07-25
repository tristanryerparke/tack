import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "glue"))

import Rhino
import scriptcontext as sc
from Rhino.Commands import Result

from glue_constants import AFTER_HANDLER_KEY, CONDUIT_KEY, HANDLER_KEY, REPLACE_HANDLER_KEY
from glue_debug import log
from glue_display import GlueConduit
from glue_events import after_transform, before_transform, replace_rhino_object, reset_runtime_objects
from glue_metadata import META_PEER, META_RELATION, META_ROLE, relationship_data, user_value
from glue_state import get_state


def _load_relationships(doc):
    objects_by_id = {
        str(obj.Id).lower(): obj
        for obj in doc.Objects
        if obj is not None
    }
    relationships = {}
    for child in objects_by_id.values():
        relation_id = user_value(child, META_RELATION)
        role = user_value(child, META_ROLE)
        peer_id = user_value(child, META_PEER)
        data = relationship_data(child)
        if relation_id is None or role is None or peer_id is None or data is None:
            continue
        if str(role).lower() != "follower":
            continue

        parent = objects_by_id.get(str(peer_id).lower())
        if parent is None:
            log("Parent {} not found for Child {}".format(peer_id, child.Id))
            continue
        try:
            parent_spec = data["parent_spec"]
            child_spec = data["child_spec"]
            parent_plane = GlueConduit.plane_from_data(data["parent_plane"])
            child_plane = GlueConduit.plane_from_data(data["child_plane"])
            parent_to_child = GlueConduit.transform_from_data(
                data["parent_to_child"]
            )
        except Exception as error:
            log("invalid plane relationship {}: {}".format(relation_id, error))
            continue

        relationships[str(relation_id)] = {
            "document_serial": doc.RuntimeSerialNumber,
            "follower_id": child.Id,
            "driver_id": parent.Id,
            "parent_spec": parent_spec,
            "child_spec": child_spec,
            "parent_to_child": parent_to_child,
            "parent_initial_plane": parent_plane,
            "child_initial_plane": child_plane,
            "current_parent_plane": GlueConduit.reference_plane(
                parent,
                parent_spec,
            ),
            "current_child_plane": GlueConduit.reference_plane(
                child,
                child_spec,
            ),
        }

    return relationships


def RunCommand(is_interactive):
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return Result.Cancel

    reset_runtime_objects()
    state = get_state()
    state["relationships"] = _load_relationships(doc)
    state["busy"] = False
    if not state["relationships"]:
        print("No saved plane glue relationships found.")
        return Result.Cancel

    sc.sticky[HANDLER_KEY] = before_transform
    Rhino.RhinoDoc.BeforeTransformObjects += before_transform
    sc.sticky[AFTER_HANDLER_KEY] = after_transform
    Rhino.RhinoDoc.AfterTransformObjects += after_transform
    sc.sticky[REPLACE_HANDLER_KEY] = replace_rhino_object
    Rhino.RhinoDoc.ReplaceRhinoObject += replace_rhino_object

    conduit = GlueConduit(state)
    conduit.Enabled = True
    sc.sticky[CONDUIT_KEY] = conduit
    doc.Views.Redraw()
    print("Glue restored: {} plane relationship(s).".format(len(state["relationships"])))
    return Result.Success


if __name__ == "__main__":
    RunCommand(True)
