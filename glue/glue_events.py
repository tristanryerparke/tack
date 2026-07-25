import Rhino
import scriptcontext as sc

from glue_constants import (
    AFTER_HANDLER_KEY,
    CONDUIT_KEY,
    HANDLER_KEY,
    IDLE_HANDLER_KEY,
    PENDING_REPLACEMENTS_KEY,
    REPLACE_HANDLER_KEY,
    STATE_KEY,
)
from glue_debug import log
from glue_display import GlueConduit


def reset_runtime_objects():
    handler = sc.sticky.pop(HANDLER_KEY, None)
    if handler is not None:
        Rhino.RhinoDoc.BeforeTransformObjects -= handler

    handler = sc.sticky.pop(AFTER_HANDLER_KEY, None)
    if handler is not None:
        Rhino.RhinoDoc.AfterTransformObjects -= handler

    handler = sc.sticky.pop(REPLACE_HANDLER_KEY, None)
    if handler is not None:
        Rhino.RhinoDoc.ReplaceRhinoObject -= handler

    idle_handler = sc.sticky.pop(IDLE_HANDLER_KEY, None)
    if idle_handler is not None:
        Rhino.RhinoApp.Idle -= idle_handler
    sc.sticky.pop(PENDING_REPLACEMENTS_KEY, None)
    state = sc.sticky.get(STATE_KEY)
    if state is not None:
        state.setdefault("handled_parent_ids", set()).clear()
        state.setdefault("pending_replacement_parent_ids", set()).clear()

    conduit = sc.sticky.pop(CONDUIT_KEY, None)
    if conduit is not None:
        conduit.Enabled = False


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


def _inverse_transform(xform):
    try:
        result = xform.TryGetInverse()
        if isinstance(result, tuple):
            return result[1] if result[0] else None
    except Exception:
        return None
    return None


def _matrix_text(xform):
    return "[{}; {}; {}; {}]".format(
        ",".join("{:.9g}".format(value) for value in (xform.M00, xform.M01, xform.M02, xform.M03)),
        ",".join("{:.9g}".format(value) for value in (xform.M10, xform.M11, xform.M12, xform.M13)),
        ",".join("{:.9g}".format(value) for value in (xform.M20, xform.M21, xform.M22, xform.M23)),
        ",".join("{:.9g}".format(value) for value in (xform.M30, xform.M31, xform.M32, xform.M33)),
    )


def _point_text(point):
    return "({:.9g}, {:.9g}, {:.9g})".format(point.X, point.Y, point.Z)


def _plane_text(plane):
    return "origin={}, x={}, y={}".format(
        _point_text(plane.Origin),
        _point_text(plane.XAxis),
        _point_text(plane.YAxis),
    )


def _plane_is_identity(xform):
    values = (
        (xform.M00, xform.M01, xform.M02, xform.M03),
        (xform.M10, xform.M11, xform.M12, xform.M13),
        (xform.M20, xform.M21, xform.M22, xform.M23),
        (xform.M30, xform.M31, xform.M32, xform.M33),
    )
    return all(
        abs(values[row][column] - (1.0 if row == column else 0.0)) <= 1e-6
        for row in range(4)
        for column in range(4)
    )


def _target_child_plane(relationship, parent_plane):
    parent_delta = Rhino.Geometry.Transform.PlaneToPlane(
        relationship["parent_initial_plane"],
        parent_plane,
    )
    return _transform_plane(
        relationship["child_initial_plane"],
        parent_delta,
    )


def _correction(doc, relationship, parent_plane):
    child = doc.Objects.Find(relationship["follower_id"])
    if child is None:
        return None
    current_child_plane = relationship.get("current_child_plane")
    if current_child_plane is None:
        current_child_plane = GlueConduit.reference_plane(
            child,
            relationship["child_spec"],
        )
    if current_child_plane is None:
        log("Child reference plane could not be resolved")
        return None
    target_child_plane = _target_child_plane(relationship, parent_plane)
    if target_child_plane is None:
        return None
    return Rhino.Geometry.Transform.PlaneToPlane(
        current_child_plane,
        target_child_plane,
    )


def _transform_child(doc, relationship, xform):
    child = doc.Objects.Find(relationship["follower_id"])
    if child is None:
        log("Child no longer exists")
        return
    if _plane_is_identity(xform):
        log("Child is already at its target plane")
        return
    try:
        if not child.Geometry.Transform(xform):
            log("Child geometry transform failed")
            return
        if not child.CommitChanges():
            log("Child CommitChanges failed")
            return
        current_child_plane = relationship.get("current_child_plane")
        if current_child_plane is not None:
            relationship["current_child_plane"] = _transform_plane(
                current_child_plane,
                xform,
            )
        log("transformed Child {}".format(relationship["follower_id"]))
    except Exception as error:
        log("Child transform error: {}".format(error))


def _reconcile(doc, relationship, parent_plane, parent_delta=None):
    child = doc.Objects.Find(relationship["follower_id"])
    if child is None:
        return
    before_point = GlueConduit.reference_point(
        child,
        relationship["child_spec"],
    )
    before_plane = relationship.get("current_child_plane")
    target_plane = _target_child_plane(relationship, parent_plane)
    if target_plane is None:
        return
    if before_point is not None and before_point.DistanceTo(target_plane.Origin) <= 1e-7:
        relationship["current_child_plane"] = target_plane
        log("Child geometry already matches the target reference point")
        return
    xform = (
        parent_delta
        if parent_delta is not None
        else _correction(doc, relationship, parent_plane)
    )
    if xform is None:
        return

    state = sc.sticky.get(STATE_KEY)
    if state is None:
        return
    state["busy"] = True
    try:
        _transform_child(doc, relationship, xform)
    finally:
        state["busy"] = False

    child = doc.Objects.Find(relationship["follower_id"])
    after_point = (
        GlueConduit.reference_point(child, relationship["child_spec"])
        if child is not None
        else None
    )
    actual_plane = relationship.get("current_child_plane")
    residual = (
        Rhino.Geometry.Transform.PlaneToPlane(actual_plane, target_plane)
        if actual_plane is not None and target_plane is not None
        else None
    )
    log("child transform matrix={}".format(_matrix_text(xform)))
    if before_point is not None and after_point is not None:
        expected_point = Rhino.Geometry.Point3d(before_point)
        expected_point.Transform(xform)
        error = after_point - expected_point
        log(
            "child reference check: before={}, expected={}, actual={}, error={}".format(
                _point_text(before_point),
                _point_text(expected_point),
                _point_text(after_point),
                _point_text(error),
            )
        )
    if before_plane is not None and actual_plane is not None:
        log("child plane before: {}".format(_plane_text(before_plane)))
    if actual_plane is not None and target_plane is not None:
        log("child plane actual: {}".format(_plane_text(actual_plane)))
        log("child plane target: {}".format(_plane_text(target_plane)))
    if residual is not None:
        log("child plane residual matrix={}".format(_matrix_text(residual)))

    inverse = _inverse_transform(xform)
    if inverse is not None:
        log("inverse transform matrix={}".format(_matrix_text(inverse)))
        if after_point is not None and before_point is not None:
            restored_point = Rhino.Geometry.Point3d(after_point)
            restored_point.Transform(inverse)
            log(
                "inverse reference check: restored={}, original={}, error={}".format(
                    _point_text(restored_point),
                    _point_text(before_point),
                    _point_text(restored_point - before_point),
                )
            )
        if actual_plane is not None and before_plane is not None:
            restored_plane = _transform_plane(actual_plane, inverse)
            if restored_plane is not None:
                restored_residual = Rhino.Geometry.Transform.PlaneToPlane(
                    before_plane,
                    restored_plane,
                )
                log(
                    "inverse plane residual matrix={}".format(
                        _matrix_text(restored_residual)
                    )
                )


def _apply_pending(sender, event):
    pending = sc.sticky.pop(PENDING_REPLACEMENTS_KEY, [])
    idle_handler = sc.sticky.pop(IDLE_HANDLER_KEY, None)
    if idle_handler is not None:
        Rhino.RhinoApp.Idle -= idle_handler

    state = sc.sticky.get(STATE_KEY)
    if state is None or state["busy"]:
        return

    for doc, relation_id, parent_id, parent_plane in pending:
        relationship = state["relationships"].get(relation_id)
        if relationship is not None:
            _reconcile(doc, relationship, parent_plane)
        state.setdefault("pending_replacement_parent_ids", set()).discard(parent_id)
        if doc is not None:
            doc.Views.Redraw()


def _queue_reconcile(doc, relation_id, parent_id, parent_plane):
    pending = sc.sticky.setdefault(PENDING_REPLACEMENTS_KEY, [])
    pending.append((doc, relation_id, parent_id, parent_plane))
    state = sc.sticky.get(STATE_KEY)
    if state is not None:
        state.setdefault("pending_replacement_parent_ids", set()).add(parent_id)
    if sc.sticky.get(IDLE_HANDLER_KEY) is None:
        sc.sticky[IDLE_HANDLER_KEY] = _apply_pending
        Rhino.RhinoApp.Idle += _apply_pending


def _parent_plane_after_transform(relationship, parent, event_transform):
    old_plane = relationship.get("current_parent_plane")
    if old_plane is None:
        old_plane = GlueConduit.reference_plane(
            parent,
            relationship["parent_spec"],
        )
    if old_plane is None:
        return None
    return _transform_plane(old_plane, event_transform)


def _geometry_plane(obj):
    geometry = obj.Geometry
    if not hasattr(geometry, "Vertices"):
        try:
            geometry = geometry.ToBrep(True)
        except Exception:
            return None
    points = []
    for index in range(geometry.Vertices.Count):
        vertex = geometry.Vertices[index]
        points.append(
            vertex.Location
            if hasattr(vertex, "Location")
            else Rhino.Geometry.Point3d(vertex)
        )
    if len(points) < 3:
        return None
    for first in range(len(points) - 2):
        for second in range(first + 1, len(points) - 1):
            axis_x = points[second] - points[first]
            if axis_x.Length <= 1e-9:
                continue
            for third in range(second + 1, len(points)):
                axis_y = points[third] - points[first]
                if Rhino.Geometry.Vector3d.CrossProduct(axis_x, axis_y).Length > 1e-9:
                    return Rhino.Geometry.Plane(points[first], axis_x, axis_y)
    return None


def _replacement_transform(old_parent, new_parent):
    old_plane = _geometry_plane(old_parent) if old_parent is not None else None
    new_plane = _geometry_plane(new_parent) if new_parent is not None else None
    if old_plane is None or new_plane is None:
        return None
    return Rhino.Geometry.Transform.PlaneToPlane(old_plane, new_plane)


def _parent_plane_after_replacement(relationship, old_parent, new_parent):
    current = relationship.get("current_parent_plane")
    if current is not None and relationship["parent_spec"]["orientation"] != "edges":
        xform = _replacement_transform(old_parent, new_parent)
        if xform is not None:
            log("replacement geometry transform={}".format(_matrix_text(xform)))
            return _transform_plane(current, xform)
        log("replacement geometry transform unavailable; using reference plane")

    return GlueConduit.reference_plane(
        new_parent,
        relationship["parent_spec"],
    )


def replace_rhino_object(sender, event):
    state = sc.sticky.get(STATE_KEY)
    if state is None or state["busy"]:
        return
    doc = getattr(event, "Document", None) or Rhino.RhinoDoc.ActiveDoc
    if doc is None or event.NewRhinoObject is None:
        return

    log(
        "ReplaceRhinoObject: object={}, old={}, new={}".format(
            event.ObjectId,
            event.OldRhinoObject,
            event.NewRhinoObject,
        )
    )
    handled_parent_ids = state.setdefault("handled_parent_ids", set())
    handled_by_transform = event.ObjectId in handled_parent_ids
    handled_parent_ids.discard(event.ObjectId)
    pending_parent_ids = state.setdefault("pending_replacement_parent_ids", set())

    for relation_id, relationship in list(state["relationships"].items()):
        if relationship["document_serial"] != doc.RuntimeSerialNumber:
            continue
        if relationship["driver_id"] != event.ObjectId:
            continue
        if handled_by_transform or event.ObjectId in pending_parent_ids:
            parent_plane = relationship.get("current_parent_plane")
        else:
            parent_plane = _parent_plane_after_replacement(
                relationship,
                event.OldRhinoObject,
                event.NewRhinoObject,
            )
        if parent_plane is not None:
            relationship["current_parent_plane"] = parent_plane
            _queue_reconcile(doc, relation_id, event.ObjectId, parent_plane)

    doc.Views.Redraw()


def before_transform(sender, event):
    state = sc.sticky.get(STATE_KEY)
    if state is None or state["busy"]:
        return
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return

    transformed_ids = {obj.Id for obj in event.Objects if obj is not None}
    for relationship in list(state["relationships"].values()):
        if relationship["document_serial"] != doc.RuntimeSerialNumber:
            continue
        if relationship["driver_id"] not in transformed_ids:
            continue
        if relationship["follower_id"] in transformed_ids:
            continue

        parent = doc.Objects.Find(relationship["driver_id"])
        if parent is None:
            continue
        old_parent_plane = relationship.get("current_parent_plane")
        parent_plane = _parent_plane_after_transform(
            relationship,
            parent,
            event.Transform,
        )
        if parent_plane is not None:
            log("Parent transform matrix={}".format(_matrix_text(event.Transform)))
            if old_parent_plane is not None:
                log("Parent plane before: {}".format(_plane_text(old_parent_plane)))
            log("Parent plane after: {}".format(_plane_text(parent_plane)))
            relationship["current_parent_plane"] = parent_plane
            state.setdefault("handled_parent_ids", set()).add(
                relationship["driver_id"]
            )
            log("applying Parent transform directly to Child")
            _reconcile(doc, relationship, parent_plane, event.Transform)

    doc.Views.Redraw()


def after_transform(sender, event):
    state = sc.sticky.get(STATE_KEY)
    if state is not None:
        state.setdefault("handled_parent_ids", set()).clear()
