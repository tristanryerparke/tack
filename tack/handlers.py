from contextlib import nullcontext
import traceback

import Rhino
import scriptcontext as sc

from tack import link
from tack import utils


REPLACE_HANDLER_KEY = "Tack.CoincidentLink.ReplaceHandler"
OBJECT_HANDLER_KEY = "Tack.CoincidentLink.ObjectHandler"


def _debug_object(label, obj):
    if not utils.DEBUG or obj is None:
        return
    points = utils.vertices_as_points(obj)
    print(
        "[Tack coincident] {} id={} vertices={}".format(
            label,
            obj.Id,
            len(points),
        )
    )


def _websocket_output():
    try:
        from rhino_watcher import websocket_output_if_available_sync
    except ImportError:
        return nullcontext()
    return websocket_output_if_available_sync()


def _quit_watcher():
    try:
        from rhino_watcher import try_send_quit_sync
    except ImportError:
        return
    try_send_quit_sync()


def _report_handler_error():
    try:
        with _websocket_output():
            traceback.print_exc()
    finally:
        _quit_watcher()


def _HandleRhinoObjectEvent(label, event, old_obj=None, new_obj=None):
    object_ids = []
    try:
        object_ids = utils.event_object_ids(event)
        state = sc.sticky.get(utils.RUNTIME_KEY)
        if state is None or state.get("busy"):
            return object_ids
        if link.ignore_replacement_followup(state, label, object_ids):
            return object_ids
        doc = getattr(event, "Document", None) or Rhino.RhinoDoc.ActiveDoc
        if doc is None or not link.event_may_affect_link(
            doc,
            state,
            event,
            label,
            object_ids,
            old_obj=old_obj,
            new_obj=new_obj,
        ):
            return object_ids

        was_broken = state.get("broken")
        with _websocket_output():
            utils.debug_event(label, event, state)
            _debug_object("replace old", old_obj)
            _debug_object("replace new", new_obj)
            result = link.maintain_link(
                doc,
                state,
                event=event,
                event_name=label,
                old_obj=old_obj,
                new_obj=new_obj,
                object_ids=object_ids,
                quiet=True,
            )
            if result is not None or state.get("broken") != was_broken:
                doc.Views.Redraw()
    except Exception:
        _report_handler_error()
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
    _HandleRhinoObjectEvent("AddRhinoObject", event)


def DeleteRhinoObjectHandler(sender, event):
    _HandleRhinoObjectEvent("DeleteRhinoObject", event)


def UndeleteRhinoObjectHandler(sender, event):
    _HandleRhinoObjectEvent("UndeleteRhinoObject", event)


def _unsubscribe(event, handler):
    try:
        event -= handler
    except Exception:
        _report_handler_error()


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
