import json

import Rhino
import System
import System.Drawing
import scriptcontext as sc

from glue_frame_picker import frame_from_spec


LINK_KEY = "Tack.PlaneLink.v1"
CHILD_KEY = "Tack.ChildId.v1"
RUNTIME_KEY = "Tack.PlaneLink.Runtime"
HANDLER_KEY = "Tack.PlaneLink.Handler"
OBJECT_HANDLER_KEY = "Tack.PlaneLink.ObjectHandler"
DOCUMENT_HANDLER_KEY = "Tack.PlaneLink.DocumentHandler"
REPLACE_HANDLER_KEY = "Tack.PlaneLink.ReplaceHandler"  # legacy runtime key
IDLE_HANDLER_KEY = "Tack.PlaneLink.IdleHandler"
CONDUIT_KEY = "Tack.PlaneLink.Conduit"

# Set True when silent undo/redo recovery is more important than zero polling.
ENABLE_IDLE_WATCHER = False


def plane_data(plane):
    return {
        "origin": [plane.Origin.X, plane.Origin.Y, plane.Origin.Z],
        "x_axis": [plane.XAxis.X, plane.XAxis.Y, plane.XAxis.Z],
        "y_axis": [plane.YAxis.X, plane.YAxis.Y, plane.YAxis.Z],
    }


def plane_from_data(data):
    return Rhino.Geometry.Plane(
        Rhino.Geometry.Point3d(*data["origin"]),
        Rhino.Geometry.Vector3d(*data["x_axis"]),
        Rhino.Geometry.Vector3d(*data["y_axis"]),
    )


def transform_data(xform):
    return [
        xform.M00, xform.M01, xform.M02, xform.M03,
        xform.M10, xform.M11, xform.M12, xform.M13,
        xform.M20, xform.M21, xform.M22, xform.M23,
        xform.M30, xform.M31, xform.M32, xform.M33,
    ]

class PlaneLinkConduit(Rhino.Display.DisplayConduit):
    def __init__(self, parent_id, child_id):
        super(PlaneLinkConduit, self).__init__()
        self.parent_id = parent_id
        self.child_id = child_id

    def DrawForeground(self, event):
        doc = Rhino.RhinoDoc.ActiveDoc
        if doc is None:
            return
        result = inspect_link(doc, self.parent_id)
        if result is None:
            return
        parent = doc.Objects.Find(self.parent_id)
        child = doc.Objects.Find(self.child_id)
        if parent is None or child is None:
            return

        parent_plane = result["parent_plane"]
        child_plane = result["child_plane"]
        event.Display.DrawPoint(
            parent_plane.Origin,
            Rhino.Display.PointStyle.RoundSimple,
            10,
            System.Drawing.Color.OrangeRed,
        )
        event.Display.DrawPoint(
            child_plane.Origin,
            Rhino.Display.PointStyle.RoundSimple,
            10,
            System.Drawing.Color.DodgerBlue,
        )
        if parent_plane.Origin.DistanceTo(child_plane.Origin) > 1e-7:
            event.Display.DrawDottedLine(
                parent_plane.Origin,
                child_plane.Origin,
                System.Drawing.Color.Gold,
            )


def _set_user_value(doc, object_id, key, value):
    obj = doc.Objects.Find(object_id)
    if obj is None:
        return False
    attrs = obj.Attributes.Duplicate()
    attrs.UserDictionary.Set(key, value)
    return doc.Objects.ModifyAttributes(object_id, attrs, True)


def write_link(doc, parent_id, child_id, parent_frame, child_frame,
               parent_plane, child_plane, parent_to_child):
    data = {
        "version": 1,
        "parent_id": str(parent_id),
        "parent_frame": parent_frame,
        "child_frame": child_frame,
        "parent_plane": plane_data(parent_plane),
        "child_plane": plane_data(child_plane),
        "parent_to_child": transform_data(parent_to_child),
    }
    if not _set_user_value(doc, child_id, LINK_KEY, json.dumps(data)):
        return False
    return _set_user_value(doc, parent_id, CHILD_KEY, str(child_id))


def read_link(obj):
    try:
        value = obj.Attributes.UserDictionary[LINK_KEY]
        return json.loads(str(value))
    except Exception:
        return None


def _transform_plane(plane, xform):
    origin = Rhino.Geometry.Point3d(plane.Origin)
    origin.Transform(xform)
    x_axis = Rhino.Geometry.Vector3d(plane.XAxis)
    x_axis.Transform(xform)
    y_axis = Rhino.Geometry.Vector3d(plane.YAxis)
    y_axis.Transform(xform)
    if not x_axis.Unitize():
        return None
    y_axis = y_axis - x_axis * (x_axis * y_axis)
    if not y_axis.Unitize():
        return None
    return Rhino.Geometry.Plane(origin, x_axis, y_axis)


def _identity(xform, tolerance=1e-7):
    values = (
        (xform.M00, xform.M01, xform.M02, xform.M03),
        (xform.M10, xform.M11, xform.M12, xform.M13),
        (xform.M20, xform.M21, xform.M22, xform.M23),
        (xform.M30, xform.M31, xform.M32, xform.M33),
    )
    return all(
        abs(values[row][column] - (1.0 if row == column else 0.0)) <= tolerance
        for row in range(4)
        for column in range(4)
    )


def _objects_for_link(doc, parent_id):
    parent = doc.Objects.Find(parent_id)
    if parent is None:
        return None, None, None
    try:
        child_id = parent.Attributes.UserDictionary[CHILD_KEY]
        child = doc.Objects.Find(System.Guid.Parse(str(child_id)))
    except Exception:
        return parent, None, None
    if child is None:
        return parent, None, None
    return parent, child, read_link(child)


def inspect_link(doc, parent_id):
    parent, child, link = _objects_for_link(doc, parent_id)
    if parent is None or child is None or link is None:
        return None

    parent_plane = frame_from_spec(parent, link["parent_frame"])
    child_plane = frame_from_spec(child, link["child_frame"])
    if parent_plane is None or child_plane is None:
        return None

    initial_parent = plane_from_data(link["parent_plane"])
    initial_child = plane_from_data(link["child_plane"])
    parent_delta = Rhino.Geometry.Transform.PlaneToPlane(
        initial_parent,
        parent_plane,
    )
    target_child = _transform_plane(initial_child, parent_delta)
    correction = Rhino.Geometry.Transform.PlaneToPlane(
        child_plane,
        target_child,
    ) if target_child is not None else None
    return {
        "parent_id": parent.Id,
        "child_id": child.Id,
        "parent_plane": parent_plane,
        "child_plane": child_plane,
        "target_child_plane": target_child,
        "correction": correction,
        "link": link,
    }


def _undo_or_redo(doc):
    return doc is not None and (
        bool(getattr(doc, "UndoActive", False))
        or bool(getattr(doc, "RedoActive", False))
    )


def reconcile(doc, parent_id, quiet=False):
    state = sc.sticky.get(RUNTIME_KEY)
    if state is None or state.get("busy") or _undo_or_redo(doc):
        return None

    result = inspect_link(doc, parent_id)
    if result is None or result["correction"] is None:
        if not quiet:
            print("Plane link could not be resolved.")
        return None

    correction = result["correction"]
    if _identity(correction):
        if not quiet:
            print("Plane link already aligned.")
        return result

    child = doc.Objects.Find(result["child_id"])
    state["busy"] = True
    try:
        if not child.Geometry.Transform(correction):
            print("Child geometry transform failed.")
            return result
        if not child.CommitChanges():
            print("Child changes could not be committed.")
            return result
        print(
            "Child updated: parent={}, child={}, correction={}".format(
                result["parent_id"],
                result["child_id"],
                transform_data(correction),
            )
        )
    finally:
        state["busy"] = False
    return result


def _event_object_ids(event):
    ids = []

    def add(value):
        if value is None:
            return
        try:
            value = value.Id
        except Exception:
            pass
        try:
            value = System.Guid.Parse(str(value))
        except Exception:
            return
        if value not in ids:
            ids.append(value)

    for name in ("ObjectId", "NewObjectId", "TheObject", "Object", "NewObject"):
        try:
            add(getattr(event, name))
        except Exception:
            pass
    for name in ("ObjectIds", "NewObjectIds"):
        try:
            for value in getattr(event, name):
                add(value)
        except Exception:
            pass
    return ids


def _event_matches_link(event, state):
    ids = _event_object_ids(event)
    return not ids or state["parent_id"] in ids or state["child_id"] in ids


def after_transform(sender, event):
    state = sc.sticky.get(RUNTIME_KEY)
    doc = Rhino.RhinoDoc.ActiveDoc
    if (
        state is None
        or doc is None
        or state.get("busy")
        or _undo_or_redo(doc)
        or not _event_matches_link(event, state)
    ):
        return
    reconcile(doc, state["parent_id"])
    doc.Views.Redraw()


def object_changed(sender, event):
    state = sc.sticky.get(RUNTIME_KEY)
    if state is None or state.get("busy"):
        return
    doc = getattr(event, "Document", None) or Rhino.RhinoDoc.ActiveDoc
    if doc is None or _undo_or_redo(doc) or not _event_matches_link(event, state):
        return
    reconcile(doc, state["parent_id"], quiet=True)
    doc.Views.Redraw()


def idle_reconcile(sender, event):
    state = sc.sticky.get(RUNTIME_KEY)
    if state is None or state.get("busy"):
        return
    reconcile(Rhino.RhinoDoc.ActiveDoc, state["parent_id"], quiet=True)


def stop_runtime():
    handler = sc.sticky.pop(HANDLER_KEY, None)
    if handler is not None:
        Rhino.RhinoDoc.AfterTransformObjects -= handler

    handler = sc.sticky.pop(OBJECT_HANDLER_KEY, None)
    if handler is not None:
        Rhino.RhinoDoc.AddRhinoObject -= handler
        Rhino.RhinoDoc.DeleteRhinoObject -= handler
        Rhino.RhinoDoc.UndeleteRhinoObject -= handler
        Rhino.RhinoDoc.PurgeRhinoObject -= handler
        Rhino.RhinoDoc.ReplaceRhinoObject -= handler
        Rhino.RhinoDoc.ModifyObjectAttributes -= handler
        Rhino.RhinoDoc.UserStringChanged -= handler

    handler = sc.sticky.pop(DOCUMENT_HANDLER_KEY, None)
    if handler is not None:
        Rhino.RhinoDoc.DocumentPropertiesChanged -= handler
        Rhino.RhinoDoc.UnitsChangedWithScaling -= handler

    # Remove runtimes created by the previous implementation.
    handler = sc.sticky.pop(REPLACE_HANDLER_KEY, None)
    if handler is not None:
        Rhino.RhinoDoc.ReplaceRhinoObject -= handler

    handler = sc.sticky.pop(IDLE_HANDLER_KEY, None)
    if handler is not None:
        Rhino.RhinoApp.Idle -= handler
    conduit = sc.sticky.pop(CONDUIT_KEY, None)
    if conduit is not None:
        conduit.Enabled = False
    sc.sticky.pop(RUNTIME_KEY, None)


def start_runtime(parent_id, child_id):
    stop_runtime()
    state = {
        "parent_id": parent_id,
        "child_id": child_id,
        "busy": False,
    }
    sc.sticky[RUNTIME_KEY] = state

    sc.sticky[HANDLER_KEY] = after_transform
    Rhino.RhinoDoc.AfterTransformObjects += after_transform

    sc.sticky[OBJECT_HANDLER_KEY] = object_changed
    Rhino.RhinoDoc.AddRhinoObject += object_changed
    Rhino.RhinoDoc.DeleteRhinoObject += object_changed
    Rhino.RhinoDoc.UndeleteRhinoObject += object_changed
    Rhino.RhinoDoc.PurgeRhinoObject += object_changed
    Rhino.RhinoDoc.ReplaceRhinoObject += object_changed
    Rhino.RhinoDoc.ModifyObjectAttributes += object_changed
    Rhino.RhinoDoc.UserStringChanged += object_changed

    sc.sticky[DOCUMENT_HANDLER_KEY] = object_changed
    Rhino.RhinoDoc.DocumentPropertiesChanged += object_changed
    Rhino.RhinoDoc.UnitsChangedWithScaling += object_changed

    if ENABLE_IDLE_WATCHER:
        sc.sticky[IDLE_HANDLER_KEY] = idle_reconcile
        Rhino.RhinoApp.Idle += idle_reconcile

    conduit = PlaneLinkConduit(parent_id, child_id)
    conduit.Enabled = True
    sc.sticky[CONDUIT_KEY] = conduit
    Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
