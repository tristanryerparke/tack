import json

import Rhino
import System
import System.Drawing
import System.Windows.Forms
import scriptcontext as sc

from glue_frame_picker import (
    frame_from_spec,
    vertex_index_map,
    vertex_locations,
    vertex_point,
)


LINK_KEY = "Tack.PlaneLink.v1"
CHILD_KEY = "Tack.ChildId.v1"
RUNTIME_KEY = "Tack.PlaneLink.Runtime"
HANDLER_KEY = "Tack.PlaneLink.Handler"
OBJECT_HANDLER_KEY = "Tack.PlaneLink.ObjectHandler"
DOCUMENT_HANDLER_KEY = "Tack.PlaneLink.DocumentHandler"
REPLACE_HANDLER_KEY = "Tack.PlaneLink.ReplaceHandler"  # legacy runtime key
CONDUIT_KEY = "Tack.PlaneLink.Conduit"
COINCIDENT_LINK_KEY = "Tack.CoincidentLink.v1"
COINCIDENT_CHILD_KEY = "Tack.CoincidentChildId.v1"
COINCIDENT_RUNTIME_KEY = "Tack.CoincidentLink.Runtime"
COINCIDENT_HANDLER_KEY = "Tack.CoincidentLink.ReplaceHandler"
COINCIDENT_OBJECT_HANDLER_KEY = "Tack.CoincidentLink.ObjectHandler"
COINCIDENT_CONDUIT_KEY = "Tack.CoincidentLink.Conduit"
# Set True to restore callback and geometry diagnostics.
COINCIDENT_DEBUG = False


def _unsubscribe(event, handler):
    try:
        event -= handler
    except Exception:
        pass


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


class CoincidentLinkConduit(Rhino.Display.DisplayConduit):
    def DrawForeground(self, event):
        doc = Rhino.RhinoDoc.ActiveDoc
        state = sc.sticky.get(COINCIDENT_RUNTIME_KEY)
        if doc is None or state is None:
            return
        result = inspect_coincident_link(doc, state)
        if result is None:
            return
        parent_point = result["parent_point"]
        child_point = result["child_point"]
        event.Display.DrawPoint(
            parent_point,
            Rhino.Display.PointStyle.RoundSimple,
            10,
            System.Drawing.Color.OrangeRed,
        )
        event.Display.DrawPoint(
            child_point,
            Rhino.Display.PointStyle.RoundSimple,
            10,
            System.Drawing.Color.DodgerBlue,
        )
        if parent_point.DistanceTo(child_point) > 1e-7:
            event.Display.DrawDottedLine(
                parent_point,
                child_point,
                System.Drawing.Color.Gold,
            )


def _debug_point(point):
    if point is None:
        return "None"
    return "({:.6f}, {:.6f}, {:.6f})".format(point.X, point.Y, point.Z)


def _debug_event(label, event, state):
    if not COINCIDENT_DEBUG:
        return
    print(
        "[Tack coincident] {} event={} ids={} parent={} child={} busy={}".format(
            label,
            type(event).__name__,
            [str(value) for value in _event_object_ids(event)],
            state.get("parent_id"),
            state.get("child_id"),
            state.get("busy"),
        )
    )


def _debug_object(label, obj, vertex_type=None, vertex_index=None):
    if not COINCIDENT_DEBUG:
        return
    try:
        actual_type, points = vertex_locations(obj)
        index = vertex_index if vertex_index is not None else -1
        point = points[index] if 0 <= index < len(points) else None
        print(
            "[Tack coincident] {} id={} type={} vertices={} selected={} point={}".format(
                label,
                obj.Id,
                vertex_type or actual_type,
                len(points),
                index,
                _debug_point(point),
            )
        )
    except Exception as error:
        print("[Tack coincident] {} geometry error: {}".format(label, error))


def _break_coincident_link(state, reason):
    if _undo_or_redo(Rhino.RhinoDoc.ActiveDoc):
        if COINCIDENT_DEBUG:
            print("[Tack coincident] suppressing break during undo/redo")
        return
    if state.get("broken"):
        return
    state["broken"] = True
    conduit = sc.sticky.get(COINCIDENT_CONDUIT_KEY)
    if conduit is not None:
        conduit.Enabled = False
    message = (
        "The coincident link between objects\n"
        "{} (parent) --> {} (child)\n"
        "was broken.\n\n{}"
    ).format(state.get("parent_id"), state.get("child_id"), reason)
    System.Windows.Forms.MessageBox.Show(
        message,
        "Tack: coincident link broken",
        System.Windows.Forms.MessageBoxButtons.OK,
        System.Windows.Forms.MessageBoxIcon.Warning,
    )


def _restore_coincident_link(state):
    state["broken"] = False
    conduit = sc.sticky.get(COINCIDENT_CONDUIT_KEY)
    if conduit is not None:
        conduit.Enabled = True


def _point_data(point):
    return [point.X, point.Y, point.Z]


def write_coincident_link(doc, parent_id, child_id, parent_vertex,
                          child_vertex, parent_point, child_point):
    data = {
        "version": 1,
        "parent_id": str(parent_id),
        "child_id": str(child_id),
        "parent_vertex": {
            "type": parent_vertex[0],
            "index": int(parent_vertex[1]),
            "point": _point_data(parent_point),
        },
        "child_vertex": {
            "type": child_vertex[0],
            "index": int(child_vertex[1]),
            "point": _point_data(child_point),
        },
    }
    if not _set_user_value(doc, child_id, COINCIDENT_LINK_KEY, json.dumps(data)):
        return False
    return _set_user_value(doc, parent_id, COINCIDENT_CHILD_KEY, str(child_id))


def read_coincident_link(obj):
    try:
        value = obj.Attributes.UserDictionary[COINCIDENT_LINK_KEY]
        return json.loads(str(value))
    except Exception:
        return None


def _coincident_objects(doc, state, parent_obj=None, child_obj=None):
    parent = parent_obj or doc.Objects.Find(state["parent_id"])
    child = child_obj or doc.Objects.Find(state["child_id"])
    if parent is None or child is None:
        return None, None, None
    return parent, child, read_coincident_link(child) or state.get("link")


def inspect_coincident_link(doc, state, parent_obj=None, child_obj=None):
    parent, child, link = _coincident_objects(
        doc, state, parent_obj=parent_obj, child_obj=child_obj
    )
    if parent is None or child is None or link is None:
        return None
    parent_vertex = link["parent_vertex"]
    child_vertex = link["child_vertex"]
    try:
        parent_point = vertex_point(
            parent, parent_vertex["type"], parent_vertex["index"]
        )
        child_point = vertex_point(
            child, child_vertex["type"], child_vertex["index"]
        )
    except Exception:
        return None
    if parent_point is None or child_point is None:
        return None
    return {
        "parent": parent,
        "child": child,
        "link": link,
        "parent_point": parent_point,
        "child_point": child_point,
        "correction": Rhino.Geometry.Transform.Translation(
            parent_point - child_point
        ),
    }


def _same_id(left, right):
    return str(left).lower() == str(right).lower()


def _usable_object_id(object_id):
    return str(object_id).lower() != str(System.Guid.Empty).lower()


def _replace_event_objects(event):
    old_obj = getattr(event, "OldRhinoObject", None)
    new_obj = getattr(event, "NewRhinoObject", None)
    if old_obj is None or new_obj is None:
        return None, None
    return old_obj, new_obj


def _event_object(doc, event):
    if event is None:
        return None
    for name in ("TheObject", "Object", "NewObject"):
        candidate = getattr(event, name, None)
        if candidate is not None and hasattr(candidate, "Geometry"):
            return candidate
    for object_id in _event_object_ids(event):
        candidate = doc.Objects.Find(object_id)
        if candidate is not None:
            return candidate
    return None


def _candidate_role(state, candidate):
    try:
        child_id = candidate.Attributes.UserDictionary[COINCIDENT_CHILD_KEY]
        if _same_id(child_id, state["child_id"]):
            return "parent"
    except Exception:
        pass
    link = read_coincident_link(candidate)
    if link is not None and _same_id(link.get("parent_id"), state["parent_id"]):
        return "child"
    return None


def _metadata_candidates(doc, state):
    for candidate in doc.Objects:
        if candidate is not None and _candidate_role(state, candidate) is not None:
            yield candidate


def _matching_vertex_index(points, point_data, tolerance):
    point = Rhino.Geometry.Point3d(*point_data)
    matches = [
        index
        for index, candidate in enumerate(points)
        if point.DistanceTo(candidate) <= tolerance
    ]
    return matches[0] if len(matches) == 1 else None


def _try_adopt_replacement(doc, state, role, candidate):
    if candidate is None:
        return False
    child = doc.Objects.Find(state["child_id"])
    link = read_coincident_link(child) if child is not None else None
    link = link or state.get("link")
    old_state = state.get(role + "_vertices")
    if link is None or old_state is None:
        return False
    old_points = old_state[1]
    new_type, new_points = vertex_locations(candidate)
    old_index = int(link[role + "_vertex"]["index"])
    new_index = _matching_vertex_index(
        new_points,
        link[role + "_vertex"]["point"],
        max(doc.ModelAbsoluteTolerance, 1e-7),
    )
    # A replacement/split must retain the linked point itself. Matching some
    # other vertex is not enough to adopt that result.
    if new_index is None:
        if COINCIDENT_DEBUG:
            print(
                "[Tack coincident] replacement candidate rejected role={} id={} old_index={} old_count={} new_count={}".format(
                    role,
                    candidate.Id,
                    old_index,
                    len(old_points),
                    len(new_points),
                )
            )
        return False
    was_busy = state.get("busy", False)
    state["busy"] = True
    try:
        if role == "parent":
            state["parent_id"] = candidate.Id
        else:
            state["child_id"] = candidate.Id
        _update_coincident_link(
            doc,
            state,
            link,
            role,
            new_type,
            new_index,
            new_points[new_index],
        )
        state[role + "_vertices"] = (new_type, new_points)
        _restore_coincident_link(state)
    finally:
        state["busy"] = was_busy
    if COINCIDENT_DEBUG:
        print(
            "[Tack coincident] adopted replacement role={} id={}".format(
                role, candidate.Id
            )
        )
    return True


def _update_coincident_link(doc, state, link, role,
                            vertex_type, vertex_index, point):
    link["parent_id"] = str(state["parent_id"])
    link["child_id"] = str(state["child_id"])
    vertex = link[role + "_vertex"]
    vertex["type"] = vertex_type
    vertex["index"] = int(vertex_index)
    vertex["point"] = _point_data(point)
    state["link"] = link
    # ReplaceRhinoObject can fire before the new object is queryable. Keep the
    # live relationship in state and persist it whenever Rhino exposes both objects.
    child_saved = _set_user_value(
        doc,
        state["child_id"],
        COINCIDENT_LINK_KEY,
        json.dumps(link),
    )
    parent_saved = _set_user_value(
        doc,
        state["parent_id"],
        COINCIDENT_CHILD_KEY,
        str(state["child_id"]),
    )
    if COINCIDENT_DEBUG:
        print(
            "[Tack coincident] metadata update role={} index={} point={} child_saved={} parent_saved={}".format(
                role,
                vertex_index,
                _debug_point(point),
                child_saved,
                parent_saved,
            )
        )
    return True


def _remap_coincident_vertex(doc, state, link, role, old_points,
                             new_obj, tolerance):
    new_type, new_points = vertex_locations(new_obj)
    old_vertex = link[role + "_vertex"]
    old_index = int(old_vertex["index"])
    topology_changed = len(old_points) != len(new_points)
    if not topology_changed:
        # A moved vertex keeps its index; only topology changes need remapping.
        new_index = old_index if old_index < len(new_points) else None
    else:
        mapping = vertex_index_map(old_points, new_points, tolerance)
        new_index = mapping.get(old_index)
        if new_index is None:
            new_index = _matching_vertex_index(
                new_points, old_vertex["point"], tolerance
            )
    if COINCIDENT_DEBUG:
        print(
            "[Tack coincident] remap role={} topology_changed={} old_count={} new_count={} old_index={} new_index={} old_point={} new_point={}".format(
                role,
                topology_changed,
                len(old_points),
                len(new_points),
                old_index,
                new_index,
                _debug_point(old_points[old_index]) if old_index < len(old_points) else "None",
                _debug_point(new_points[new_index]) if new_index is not None else "None",
            )
        )
    if new_index is None:
        _break_coincident_link(
            state,
            "The {} vertex could not be matched after the topology change.".format(
                role
            ),
        )
        return False
    updated = _update_coincident_link(
        doc,
        state,
        link,
        role,
        new_type,
        new_index,
        new_points[new_index],
    )
    _restore_coincident_link(state)
    return updated


def coincident_reconcile(
    doc, state, quiet=False, parent_obj=None, child_obj=None
):
    if state is None or state.get("busy"):
        return None
    result = inspect_coincident_link(
        doc, state, parent_obj=parent_obj, child_obj=child_obj
    )
    if COINCIDENT_DEBUG:
        print("[Tack coincident] reconcile quiet={} resolved={}".format(quiet, result is not None))
    if result is None:
        if not quiet:
            print("Coincident vertex link could not be resolved.")
        return None
    if COINCIDENT_DEBUG:
        print(
            "[Tack coincident] reconcile parent={} child={}".format(
                _debug_point(result["parent_point"]),
                _debug_point(result["child_point"]),
            )
        )
    if result["parent_point"].DistanceTo(result["child_point"]) <= max(
        doc.ModelAbsoluteTolerance, 1e-7
    ):
        return result

    # Keep callback metadata current during undo, but never mutate/commit a
    # child while Rhino is replaying the undo record.
    if _undo_or_redo(doc):
        return result

    state["busy"] = True
    try:
        if not result["child"].Geometry.Transform(result["correction"]):
            print("Child geometry translation failed.")
            return result
        if not result["child"].CommitChanges():
            print("Child changes could not be committed.")
            return result
        print(
            "[Tack coincident] child updated parent={} child={}".format(
                result["parent"].Id,
                result["child"].Id,
            )
        )
    finally:
        state["busy"] = False
    return result


def coincident_check_update(
    doc,
    state,
    object_ids=None,
    event=None,
    quiet=True,
    parent_obj=None,
    child_obj=None,
):
    """Resolve the saved pair from callback IDs or metadata, then align it."""
    if doc is None or state is None or state.get("busy"):
        return None

    object_ids = list(object_ids or [])
    candidate = _event_object(doc, event)
    if candidate is None:
        for object_id in object_ids:
            candidate = doc.Objects.Find(object_id)
            if candidate is not None:
                break
    role = _candidate_role(state, candidate) if candidate is not None else None
    if role is not None and (
        state.get("broken")
        or not _same_id(candidate.Id, state[role + "_id"])
    ):
        _try_adopt_replacement(doc, state, role, candidate)
    elif candidate is None:
        for saved_candidate in _metadata_candidates(doc, state):
            saved_role = _candidate_role(state, saved_candidate)
            if saved_role is not None and (
                state.get("broken")
                or not _same_id(
                    saved_candidate.Id, state[saved_role + "_id"]
                )
            ):
                if _try_adopt_replacement(
                    doc, state, saved_role, saved_candidate
                ):
                    break

    parent = doc.Objects.Find(state["parent_id"])
    child = doc.Objects.Find(state["child_id"])
    if parent is None or child is None:
        missing_role = "parent" if parent is None else "child"
        if (
            candidate is not None
            and role in (None, missing_role)
            and (
                state.get("broken")
                or not _same_id(
                    candidate.Id, state[missing_role + "_id"]
                )
            )
        ):
            _try_adopt_replacement(doc, state, missing_role, candidate)
        parent = doc.Objects.Find(state["parent_id"])
        child = doc.Objects.Find(state["child_id"])

    if parent is None or child is None:
        for candidate in _metadata_candidates(doc, state):
            candidate_role = _candidate_role(state, candidate)
            if candidate_role is not None and (
                state.get("broken")
                or not _same_id(
                    candidate.Id, state[candidate_role + "_id"]
                )
            ):
                _try_adopt_replacement(
                    doc, state, candidate_role, candidate
                )
            parent = doc.Objects.Find(state["parent_id"])
            child = doc.Objects.Find(state["child_id"])
            if parent is not None and child is not None:
                break

    if parent is None or child is None:
        if (
            not _undo_or_redo(doc)
            and any(
                _same_id(object_id, state["parent_id"])
                or _same_id(object_id, state["child_id"])
                for object_id in object_ids
            )
        ):
            _break_coincident_link(
                state, "A linked object could not be recovered from callback data or saved metadata."
            )
        return None

    result = coincident_reconcile(
        doc,
        state,
        quiet=quiet,
        parent_obj=parent_obj,
        child_obj=child_obj,
    )
    if result is not None:
        _restore_coincident_link(state)
    elif role is not None:
        _break_coincident_link(
            state, "The linked objects no longer expose usable vertex data."
        )
    return result


def coincident_replace_object(sender, event):
    state = sc.sticky.get(COINCIDENT_RUNTIME_KEY)
    if state is None or state.get("busy"):
        return
    _debug_event("ReplaceRhinoObject", event, state)
    old_obj, new_obj = _replace_event_objects(event)
    if old_obj is None or new_obj is None:
        _break_coincident_link(
            state, "ReplaceRhinoObject did not expose complete old/new objects."
        )
        return
    _debug_object("replace old", old_obj)
    _debug_object("replace new", new_obj)

    role = None
    if _same_id(old_obj.Id, state["parent_id"]):
        role = "parent"
    elif _same_id(old_obj.Id, state["child_id"]):
        role = "child"
    if role is None:
        if COINCIDENT_DEBUG:
            print("[Tack coincident] replacement is not the linked parent or child")
        return
    if COINCIDENT_DEBUG:
        print("[Tack coincident] replacement role={}".format(role))
    # Rhino may emit Delete/Add for the old object after this replacement.
    # Keep that transient delete from looking like permanent removal.
    state["replacement_pending_ids"] = [
        str(old_obj.Id),
        str(new_obj.Id),
    ]

    doc = getattr(event, "Document", None) or Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return
    state["busy"] = True
    try:
        old_child = doc.Objects.Find(state["child_id"])
        link = read_coincident_link(old_child) if old_child is not None else None
        if role == "child":
            link = read_coincident_link(old_obj) or link
        link = link or state.get("link")
        if link is None:
            _break_coincident_link(
                state, "ReplaceRhinoObject did not preserve Tack metadata."
            )
            return
        old_type, old_points = vertex_locations(old_obj)
        state[role + "_vertices"] = (old_type, old_points)
        replacement_id = (
            new_obj.Id if _usable_object_id(new_obj.Id) else old_obj.Id
        )
        if not _usable_object_id(new_obj.Id) and COINCIDENT_DEBUG:
            print(
                "[Tack coincident] replacement NewRhinoObject has Guid.Empty; keeping {}".format(
                    replacement_id
                )
            )
        if role == "parent":
            state["parent_id"] = replacement_id
        else:
            state["child_id"] = replacement_id
        if not _remap_coincident_vertex(
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
    coincident_check_update(
        doc,
        state,
        object_ids=_event_object_ids(event),
        quiet=True,
        parent_obj=new_obj if role == "parent" else None,
    )
    doc.Views.Redraw()


def _coincident_object_event(label, event):
    state = sc.sticky.get(COINCIDENT_RUNTIME_KEY)
    if state is None or state.get("busy"):
        return
    _debug_event(label, event, state)
    doc = getattr(event, "Document", None) or Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return
    coincident_check_update(
        doc,
        state,
        object_ids=_event_object_ids(event),
        event=event,
        quiet=True,
    )
    doc.Views.Redraw()


def coincident_add_object(sender, event):
    _coincident_object_event("AddRhinoObject", event)
    state = sc.sticky.get(COINCIDENT_RUNTIME_KEY)
    if state is not None:
        pending = state.get("replacement_pending_ids", [])
        if any(str(object_id) in pending for object_id in _event_object_ids(event)):
            state.pop("replacement_pending_ids", None)


def coincident_delete_object(sender, event):
    state = sc.sticky.get(COINCIDENT_RUNTIME_KEY)
    pending = state.get("replacement_pending_ids", []) if state else []
    if pending and any(str(object_id) in pending for object_id in _event_object_ids(event)):
        _debug_event("DeleteRhinoObject (replacement; ignored)", event, state)
        return
    _coincident_object_event("DeleteRhinoObject", event)


def coincident_undelete_object(sender, event):
    _coincident_object_event("UndeleteRhinoObject", event)


def stop_coincident_runtime():
    # Remove callbacks left by the previous polling implementation.
    handler = sc.sticky.pop("Tack.CoincidentLink.IdleHandler", None)
    if handler is not None:
        _unsubscribe(Rhino.RhinoApp.Idle, handler)
    handler = sc.sticky.pop(COINCIDENT_HANDLER_KEY, None)
    if handler is not None:
        _unsubscribe(Rhino.RhinoDoc.ReplaceRhinoObject, handler)
    handlers = sc.sticky.pop(COINCIDENT_OBJECT_HANDLER_KEY, None)
    if handlers is not None:
        if callable(handlers):
            handlers = (handlers,)
        elif isinstance(handlers, dict):
            handlers = tuple(handlers.values())
        for handler in handlers:
            for rhino_event in (
                Rhino.RhinoDoc.AddRhinoObject,
                Rhino.RhinoDoc.DeleteRhinoObject,
                Rhino.RhinoDoc.UndeleteRhinoObject,
                Rhino.RhinoDoc.PurgeRhinoObject,
                Rhino.RhinoDoc.ModifyObjectAttributes,
                Rhino.RhinoDoc.UserStringChanged,
                Rhino.RhinoDoc.AfterTransformObjects,
            ):
                _unsubscribe(rhino_event, handler)
    conduit = sc.sticky.pop(COINCIDENT_CONDUIT_KEY, None)
    if conduit is not None:
        conduit.Enabled = False
    sc.sticky.pop(COINCIDENT_RUNTIME_KEY, None)


def start_coincident_runtime(parent_id, child_id):
    stop_runtime()
    stop_coincident_runtime()
    doc = Rhino.RhinoDoc.ActiveDoc
    parent = doc.Objects.Find(parent_id)
    child = doc.Objects.Find(child_id)
    if parent is None or child is None:
        return False
    state = {
        "parent_id": parent_id,
        "child_id": child_id,
        "busy": False,
        "broken": False,
        "replacement_pending_ids": [],
    }
    link = read_coincident_link(child)
    if link is None:
        return False
    state["link"] = link
    for role, obj in (("parent", parent), ("child", child)):
        state[role + "_vertices"] = vertex_locations(obj)
    sc.sticky[COINCIDENT_RUNTIME_KEY] = state

    sc.sticky[COINCIDENT_HANDLER_KEY] = coincident_replace_object
    Rhino.RhinoDoc.ReplaceRhinoObject += coincident_replace_object
    object_handlers = (
        coincident_add_object,
        coincident_delete_object,
        coincident_undelete_object,
    )
    sc.sticky[COINCIDENT_OBJECT_HANDLER_KEY] = object_handlers
    Rhino.RhinoDoc.AddRhinoObject += coincident_add_object
    Rhino.RhinoDoc.DeleteRhinoObject += coincident_delete_object
    Rhino.RhinoDoc.UndeleteRhinoObject += coincident_undelete_object
    if COINCIDENT_DEBUG:
        print(
            "[Tack coincident] runtime started parent={} child={} debug={}".format(
                parent_id, child_id, COINCIDENT_DEBUG
            )
        )
    conduit = CoincidentLinkConduit()
    conduit.Enabled = True
    sc.sticky[COINCIDENT_CONDUIT_KEY] = conduit
    doc.Views.Redraw()
    return True


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

    # Remove runtimes created by previous implementations.
    handler = sc.sticky.pop(REPLACE_HANDLER_KEY, None)
    if handler is not None:
        Rhino.RhinoDoc.ReplaceRhinoObject -= handler
    handler = sc.sticky.pop("Tack.PlaneLink.IdleHandler", None)
    if handler is not None:
        Rhino.RhinoApp.Idle -= handler

    conduit = sc.sticky.pop(CONDUIT_KEY, None)
    if conduit is not None:
        conduit.Enabled = False
    coincident_conduit = sc.sticky.pop(COINCIDENT_CONDUIT_KEY, None)
    if coincident_conduit is not None:
        coincident_conduit.Enabled = False
    sc.sticky.pop(RUNTIME_KEY, None)


def start_runtime(parent_id, child_id):
    stop_runtime()
    stop_coincident_runtime()
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

    conduit = PlaneLinkConduit(parent_id, child_id)
    conduit.Enabled = True
    sc.sticky[CONDUIT_KEY] = conduit
    Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
