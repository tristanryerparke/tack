import Rhino
import scriptcontext as sc

from glue_constants import (
    CONDUIT_KEY,
    HANDLER_KEY,
    IDLE_HANDLER_KEY,
    PENDING_REPLACEMENTS_KEY,
    REPLACE_HANDLER_KEY,
    STATE_KEY,
)
from glue_debug import log
from glue_display import GlueConduit
from glue_transforms import transform_allowed

def reset_runtime_objects():
    handler = sc.sticky.pop(HANDLER_KEY, None)
    if handler is not None:
        Rhino.RhinoDoc.BeforeTransformObjects -= handler

    handler = sc.sticky.pop(REPLACE_HANDLER_KEY, None)
    if handler is not None:
        Rhino.RhinoDoc.ReplaceRhinoObject -= handler

    idle_handler = sc.sticky.pop(IDLE_HANDLER_KEY, None)
    if idle_handler is not None:
        Rhino.RhinoApp.Idle -= idle_handler
    sc.sticky.pop(PENDING_REPLACEMENTS_KEY, None)

    conduit = sc.sticky.pop(CONDUIT_KEY, None)
    if conduit is not None:
        conduit.Enabled = False


def _transform_child(doc, relationship, xform):
    child_id = relationship["follower_id"]
    child = doc.Objects.Find(child_id)
    if child is None:
        log("Child {} no longer exists".format(child_id))
        return

    try:
        if not child.Geometry.Transform(xform):
            log("Child {} geometry transform failed".format(child_id))
            return
        if not child.CommitChanges():
            log("Child {} CommitChanges failed".format(child_id))
            return
        log("transformed Child {} in place".format(child_id))
    except Exception as error:
        log("Child {} transform error: {}".format(child_id, error))


def _transformed_frame(frame, xform):
    origin = Rhino.Geometry.Point3d(frame.Origin)
    origin.Transform(xform)
    x_axis = Rhino.Geometry.Vector3d(frame.XAxis)
    x_axis.Transform(xform)
    y_axis = Rhino.Geometry.Vector3d(frame.YAxis)
    y_axis.Transform(xform)
    return Rhino.Geometry.Plane(origin, x_axis, y_axis)


def _vertex_delta_to_target(doc, relationship, parent_point, parent_frame=None):
    child = doc.Objects.Find(relationship["follower_id"])
    if child is None:
        return None

    child_centroid = GlueConduit.centroid(child)
    offset = relationship.get("offset")
    if offset is None:
        offset = child_centroid - parent_point
        relationship["offset"] = offset
        log("reconstructed missing vertex offset: {}".format(offset))

    if relationship.get("rotation") and relationship.get("initial_frame") and parent_frame:
        offset = Rhino.Geometry.Vector3d(offset)
        offset.Transform(
            Rhino.Geometry.Transform.PlaneToPlane(
                relationship["initial_frame"],
                parent_frame,
            )
        )

    target = parent_point + offset
    return target - child_centroid


def _apply_pending_replacements(sender, event):
    pending = sc.sticky.pop(PENDING_REPLACEMENTS_KEY, [])
    idle_handler = sc.sticky.pop(IDLE_HANDLER_KEY, None)
    if idle_handler is not None:
        try:
            Rhino.RhinoApp.Idle -= idle_handler
        except Exception:
            pass

    state = sc.sticky.get(STATE_KEY)
    if state is None or state["busy"]:
        return

    log("applying {} queued vertex movement(s) on Idle".format(len(pending)))
    for doc, relation_id, parent_point, parent_frame in pending:
        relationship = state["relationships"].get(relation_id)
        if relationship is None:
            log("queued relationship {} no longer exists".format(relation_id))
            continue
        if doc is None or doc.Objects.Find(relationship["follower_id"]) is None:
            log("queued Child no longer exists for relationship {}".format(relation_id))
            continue

        delta = _vertex_delta_to_target(
            doc,
            relationship,
            parent_point,
            parent_frame,
        )
        if delta is None or delta.Length <= 1e-9:
            log("Child {} is already at the vertex target".format(relationship["follower_id"]))
            continue

        state["busy"] = True
        try:
            log("applying queued target correction to Child {}".format(relationship["follower_id"]))
            _transform_child(
                doc,
                relationship,
                Rhino.Geometry.Transform.Translation(delta),
            )
        finally:
            state["busy"] = False
        doc.Views.Redraw()


def _queue_vertex_target(doc, relation_id, parent_point, parent_frame):
    pending = sc.sticky.get(PENDING_REPLACEMENTS_KEY)
    if pending is None:
        pending = []
        sc.sticky[PENDING_REPLACEMENTS_KEY] = pending
    pending.append((doc, relation_id, parent_point, parent_frame))

    if sc.sticky.get(IDLE_HANDLER_KEY) is None:
        sc.sticky[IDLE_HANDLER_KEY] = _apply_pending_replacements
        Rhino.RhinoApp.Idle += _apply_pending_replacements
        log("queued vertex movement and registered Idle handler")


def replace_rhino_object(sender, event):
    state = sc.sticky.get(STATE_KEY)
    if state is None or state["busy"]:
        return

    doc = getattr(event, "Document", None) or Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return

    parent_id = event.ObjectId
    old_parent = event.OldRhinoObject
    new_parent = event.NewRhinoObject
    log(
        "ReplaceRhinoObject: object={}, old={}, new={}".format(
            parent_id,
            old_parent,
            new_parent,
        )
    )

    for relation_id, relationship in list(state["relationships"].items()):
        if relationship["document_serial"] != doc.RuntimeSerialNumber:
            continue
        if relationship["driver_id"] != parent_id:
            continue
        if relationship.get("reference") != "vertex":
            continue
        if not relationship.get("translation", True):
            log("vertex relationship skipped: translation is disabled")
            continue
        if old_parent is None or new_parent is None:
            log("vertex relationship skipped: replacement object is missing")
            continue

        new_point = GlueConduit.reference_point(
            new_parent,
            relationship,
            fallback=False,
        )
        if new_point is None:
            log(
                "vertex relationship skipped: could not resolve vertex type={}, index={}".format(
                    relationship.get("vertex_type", ""),
                    relationship.get("vertex_index", -1),
                )
            )
            continue

        parent_frame = (
            GlueConduit.reference_frame(new_parent, relationship)
            if relationship.get("rotation")
            else None
        )
        delta = _vertex_delta_to_target(
            doc,
            relationship,
            new_point,
            parent_frame,
        )
        if delta is None:
            log("vertex relationship skipped: Child no longer exists")
            continue
        log("vertex target delta: {}".format(delta))
        if delta.Length <= 1e-9:
            log("vertex relationship skipped: vertex did not move")
            continue

        _queue_vertex_target(doc, relation_id, new_point, parent_frame)

    doc.Views.Redraw()


def before_transform(sender, event):
    state = sc.sticky.get(STATE_KEY)
    if state is None or state["busy"]:
        return
    doc = sender if isinstance(sender, Rhino.RhinoDoc) else Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return

    transformed_ids = {obj.Id for obj in event.Objects if obj is not None}
    if not transformed_ids:
        return

    log(
        "BeforeTransformObjects: ids={}, relationships={}, transform={}".format(
            list(transformed_ids),
            len(state["relationships"]),
            event.Transform,
        )
    )

    for relationship in list(state["relationships"].values()):
        if relationship["document_serial"] != doc.RuntimeSerialNumber:
            continue
        if relationship["driver_id"] not in transformed_ids:
            continue

        log(
            "matched Parent {} for Child {}: reference={}, vertex_type={}, vertex_index={}".format(
                relationship["driver_id"],
                relationship["follower_id"],
                relationship.get("reference", "centroid"),
                relationship.get("vertex_type", ""),
                relationship.get("vertex_index", -1),
            )
        )
        if relationship["follower_id"] in transformed_ids:
            log("skipping because Child was transformed in the same event")
            continue

        if relationship.get("reference") == "vertex":
            if not relationship.get("translation", True):
                log("vertex relationship skipped: translation is disabled")
                continue
            parent = doc.Objects.Find(relationship["driver_id"])
            old_point = GlueConduit.reference_point(
                parent,
                relationship,
                fallback=False,
            ) if parent is not None else None
            if old_point is None:
                log("vertex relationship skipped: current vertex could not be resolved")
                continue
            new_point = Rhino.Geometry.Point3d(old_point)
            new_point.Transform(event.Transform)
            parent_frame = None
            if relationship.get("rotation"):
                old_frame = GlueConduit.reference_frame(parent, relationship)
                if old_frame is not None:
                    parent_frame = _transformed_frame(old_frame, event.Transform)
            delta = _vertex_delta_to_target(
                doc,
                relationship,
                new_point,
                parent_frame,
            )
            if delta is None:
                log("vertex relationship skipped: Child no longer exists")
                continue
            log("transformed vertex target delta: {}".format(delta))
            if delta.Length <= 1e-9:
                continue
            state["busy"] = True
            try:
                _transform_child(
                    doc,
                    relationship,
                    Rhino.Geometry.Transform.Translation(delta),
                )
            finally:
                state["busy"] = False
            continue

        if not transform_allowed(event.Transform, relationship):
            log("skipping because transform type is disabled")
            continue

        state["busy"] = True
        try:
            log("transforming Child {}".format(relationship["follower_id"]))
            _transform_child(doc, relationship, event.Transform)
        finally:
            state["busy"] = False

    doc.Views.Redraw()
