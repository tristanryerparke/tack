import Rhino
import scriptcontext as sc

import link
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


def _HandleRhinoObjectEvent(label, event, old_obj=None, new_obj=None):
    object_ids = utils.event_object_ids(event)
    state = sc.sticky.get(utils.RUNTIME_KEY)
    if state is None or state.get("busy"):
        return object_ids
    utils.debug_event(label, event, state)
    _debug_object("replace old", old_obj)
    _debug_object("replace new", new_obj)
    doc = getattr(event, "Document", None) or Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return object_ids
    link.maintain_link(
        doc,
        state,
        event=event,
        event_name=label,
        old_obj=old_obj,
        new_obj=new_obj,
        object_ids=object_ids,
        quiet=True,
    )
    doc.Views.Redraw()
    return object_ids


def ReplaceRhinoObjectHandler(sender, event):
    old_obj = getattr(event, "OldRhinoObject", None)
    new_obj = getattr(event, "NewRhinoObject", None)
    _HandleRhinoObjectEvent(
        "ReplaceRhinoObject",
        event,
        old_obj=old_obj,
        new_obj=new_obj,
    )


def AddRhinoObjectHandler(sender, event):
    object_ids = _HandleRhinoObjectEvent("AddRhinoObject", event)
    state = sc.sticky.get(utils.RUNTIME_KEY)
    if state is not None:
        pending = state.get("replacement_pending_ids", [])
        if any(
            str(object_id) in pending
            for object_id in object_ids
        ):
            state.pop("replacement_pending_ids", None)


def DeleteRhinoObjectHandler(sender, event):
    _HandleRhinoObjectEvent("DeleteRhinoObject", event)


def UndeleteRhinoObjectHandler(sender, event):
    _HandleRhinoObjectEvent("UndeleteRhinoObject", event)


def _unsubscribe(event, handler):
    try:
        event -= handler
    except Exception:
        pass


def subscribe():
    sc.sticky[REPLACE_HANDLER_KEY] = ReplaceRhinoObjectHandler
    Rhino.RhinoDoc.ReplaceRhinoObject += ReplaceRhinoObjectHandler

    object_handlers = (
        AddRhinoObjectHandler,
        DeleteRhinoObjectHandler,
        UndeleteRhinoObjectHandler,
    )
    sc.sticky[OBJECT_HANDLER_KEY] = object_handlers
    Rhino.RhinoDoc.AddRhinoObject += AddRhinoObjectHandler
    Rhino.RhinoDoc.DeleteRhinoObject += DeleteRhinoObjectHandler
    Rhino.RhinoDoc.UndeleteRhinoObject += UndeleteRhinoObjectHandler


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
