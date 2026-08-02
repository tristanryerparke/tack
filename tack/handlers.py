from contextlib import nullcontext
import traceback

import Rhino

from tack import link
from tack import metadata
from tack import runtime
from tack import utils


REPLACE_HANDLER_KEY = "Tack.AnchorLink.ReplaceHandler"
OBJECT_HANDLER_KEY = "Tack.AnchorLink.ObjectHandler"


def _debug_object(label, obj):
    if not utils.DEBUG or obj is None:
        return
    geometry = obj.Geometry
    bounding_box = geometry.GetBoundingBox(True)
    print(
        "[Tack anchor] {} id={} geometry={} bbox_valid={}".format(
            label,
            obj.Id,
            type(geometry).__name__,
            bounding_box.IsValid,
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


def _event_objects(doc, event, object_ids, old_obj, new_obj):
    objects = []

    def add(candidate):
        if candidate is not None and candidate not in objects:
            objects.append(candidate)

    add(old_obj)
    add(new_obj)
    add(utils.event_object(doc, event, object_ids))
    for object_id in object_ids:
        add(utils.find_object(doc, object_id))
    return objects


def _event_links(doc, event, object_ids, old_obj, new_obj):
    saved_links = {}
    objects = _event_objects(doc, event, object_ids, old_obj, new_obj)
    for obj in objects:
        for saved_link in metadata.links_for_object(doc, obj):
            saved_links[saved_link["link_id"]] = saved_link

    if not saved_links:
        for saved_link in metadata.all_links(doc):
            if not object_ids or any(
                utils.same_id(object_id, saved_link[role + "_id"])
                for object_id in object_ids
                for role in ("parent", "child")
            ):
                saved_links[saved_link["link_id"]] = saved_link
    return list(saved_links.values())


def _HandleRhinoObjectEvent(label, event, old_obj=None, new_obj=None):
    object_ids = []
    try:
        object_ids = utils.event_object_ids(event)
        doc = getattr(event, "Document", None) or Rhino.RhinoDoc.ActiveDoc
        if doc is None:
            return object_ids

        for saved_link in _event_links(
            doc,
            event,
            object_ids,
            old_obj,
            new_obj,
        ):
            state = runtime.state_for_link(doc, saved_link)
            if state is None or state.get("busy"):
                continue
            if link.ignore_replacement_followup(state, label, object_ids):
                continue
            if not link.event_may_affect_link(
                doc,
                state,
                event,
                label,
                object_ids,
                old_obj=old_obj,
                new_obj=new_obj,
            ):
                continue

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
    unsubscribe()
    import scriptcontext as sc

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
    import scriptcontext as sc

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
