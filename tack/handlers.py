import Rhino
import scriptcontext as sc

import metadata
import runtime
import utils
from tack_frame_picker import vertex_locations


REPLACE_HANDLER_KEY = "Tack.CoincidentLink.ReplaceHandler"
OBJECT_HANDLER_KEY = "Tack.CoincidentLink.ObjectHandler"


def _debug_object(label, obj):
    if not utils.DEBUG:
        return
    try:
        geometry_type, points = vertex_locations(obj)
        print(
            "[Tack coincident] {} id={} type={} vertices={}".format(
                label,
                obj.Id,
                geometry_type,
                len(points),
            )
        )
    except Exception as error:
        print("[Tack coincident] {} geometry error: {}".format(label, error))


def replace_object(sender, event):
    state = sc.sticky.get(utils.RUNTIME_KEY)
    if state is None or state.get("busy"):
        return
    utils.debug_event("ReplaceRhinoObject", event, state)
    old_obj = getattr(event, "OldRhinoObject", None)
    new_obj = getattr(event, "NewRhinoObject", None)
    if old_obj is None or new_obj is None:
        runtime.break_link(
            state,
            "ReplaceRhinoObject did not expose complete old/new objects.",
        )
        return
    _debug_object("replace old", old_obj)
    _debug_object("replace new", new_obj)

    role = None
    if utils.same_id(old_obj.Id, state["parent_id"]):
        role = "parent"
    elif utils.same_id(old_obj.Id, state["child_id"]):
        role = "child"
    if role is None:
        if utils.DEBUG:
            print("[Tack coincident] replacement is not the linked parent or child")
        return
    if utils.DEBUG:
        print("[Tack coincident] replacement role={}".format(role))
    state["replacement_pending_ids"] = [str(old_obj.Id), str(new_obj.Id)]

    doc = getattr(event, "Document", None) or Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return
    state["busy"] = True
    try:
        old_child = doc.Objects.Find(state["child_id"])
        link = metadata.read_link(old_child) if old_child is not None else None
        if role == "child":
            link = metadata.read_link(old_obj) or link
        link = link or state.get("link")
        if link is None:
            runtime.break_link(
                state,
                "ReplaceRhinoObject did not preserve Tack metadata.",
            )
            return
        old_type, old_points = vertex_locations(old_obj)
        state[role + "_vertices"] = (old_type, old_points)
        replacement_id = (
            new_obj.Id if utils.usable_object_id(new_obj.Id) else old_obj.Id
        )
        if not utils.usable_object_id(new_obj.Id) and utils.DEBUG:
            print(
                "[Tack coincident] replacement NewRhinoObject has Guid.Empty; keeping {}".format(
                    replacement_id
                )
            )
        state[role + "_id"] = replacement_id
        if not runtime.remap_vertex(
            doc,
            state,
            link,
            role,
            old_points,
            new_obj,
            max(doc.ModelAbsoluteTolerance, 1e-7),
        ):
            return
        new_type, new_points = vertex_locations(new_obj)
        state[role + "_vertices"] = (new_type, new_points)
    finally:
        state["busy"] = False
    runtime.check_update(
        doc,
        state,
        object_ids=utils.event_object_ids(event),
        quiet=True,
        parent_obj=new_obj if role == "parent" else None,
    )
    doc.Views.Redraw()


def _object_event(label, event):
    state = sc.sticky.get(utils.RUNTIME_KEY)
    if state is None or state.get("busy"):
        return
    utils.debug_event(label, event, state)
    doc = getattr(event, "Document", None) or Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return
    runtime.check_update(
        doc,
        state,
        object_ids=utils.event_object_ids(event),
        event=event,
        quiet=True,
    )
    doc.Views.Redraw()


def add_object(sender, event):
    _object_event("AddRhinoObject", event)
    state = sc.sticky.get(utils.RUNTIME_KEY)
    if state is not None:
        pending = state.get("replacement_pending_ids", [])
        if any(
            str(object_id) in pending
            for object_id in utils.event_object_ids(event)
        ):
            state.pop("replacement_pending_ids", None)


def delete_object(sender, event):
    state = sc.sticky.get(utils.RUNTIME_KEY)
    pending = state.get("replacement_pending_ids", []) if state else []
    if pending and any(
        str(object_id) in pending
        for object_id in utils.event_object_ids(event)
    ):
        utils.debug_event("DeleteRhinoObject (replacement; ignored)", event, state)
        return
    _object_event("DeleteRhinoObject", event)


def undelete_object(sender, event):
    _object_event("UndeleteRhinoObject", event)


def _unsubscribe(event, handler):
    try:
        event -= handler
    except Exception:
        pass


def subscribe():
    sc.sticky[REPLACE_HANDLER_KEY] = replace_object
    Rhino.RhinoDoc.ReplaceRhinoObject += replace_object

    object_handlers = (add_object, delete_object, undelete_object)
    sc.sticky[OBJECT_HANDLER_KEY] = object_handlers
    Rhino.RhinoDoc.AddRhinoObject += add_object
    Rhino.RhinoDoc.DeleteRhinoObject += delete_object
    Rhino.RhinoDoc.UndeleteRhinoObject += undelete_object


def unsubscribe():
    handler = sc.sticky.pop(REPLACE_HANDLER_KEY, None)
    if handler is not None:
        _unsubscribe(Rhino.RhinoDoc.ReplaceRhinoObject, handler)

    stored_handlers = sc.sticky.pop(OBJECT_HANDLER_KEY, ())
    for handler, event in zip(
        stored_handlers,
        (
            Rhino.RhinoDoc.AddRhinoObject,
            Rhino.RhinoDoc.DeleteRhinoObject,
            Rhino.RhinoDoc.UndeleteRhinoObject,
        ),
    ):
        _unsubscribe(event, handler)
