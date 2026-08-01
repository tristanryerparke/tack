import Rhino
import System


DEBUG = True
RUNTIME_KEY = "Tack.CoincidentLink.Runtime"
CONDUIT_KEY = "Tack.CoincidentLink.Conduit"


def same_id(left, right):
    return str(left).lower() == str(right).lower()


def usable_object_id(object_id):
    return not same_id(object_id, System.Guid.Empty)


def undo_or_redo(doc):
    return doc is not None and (
        bool(getattr(doc, "UndoActive", False))
        or bool(getattr(doc, "RedoActive", False))
    )


def brep_geometry(obj):
    """Return Brep geometry for a Rhino object or Brep-form geometry."""
    geometry = getattr(obj, "Geometry", obj)
    if hasattr(geometry, "Vertices"):
        return geometry
    return geometry.ToBrep()


def vertices_as_points(obj):
    """Return the Brep vertices as Point3d values."""
    return [
        Rhino.Geometry.Point3d(vertex.Location)
        for vertex in brep_geometry(obj).Vertices
    ]


def get_vertex_from_brep(obj, vertex_index):
    """Return one Brep vertex as a Point3d."""
    return Rhino.Geometry.Point3d(
        brep_geometry(obj).Vertices[int(vertex_index)].Location
    )


def coincident_vertices(first_obj, second_obj, tolerance):
    """Return vertex pairs within tolerance on two breps"""
    first_points = vertices_as_points(first_obj)
    second_points = vertices_as_points(second_obj)
    matches = []
    for first_index, first_point in enumerate(first_points):
        for second_index, second_point in enumerate(second_points):
            if first_point.DistanceTo(second_point) <= tolerance:
                matches.append(
                    (
                        "BrepVertex",
                        first_index,
                        "BrepVertex",
                        second_index,
                        first_point,
                        second_point,
                    )
                )
    return matches


def vertex_index_map(old_points, new_points, tolerance):
    """Map uniquely matching old vertex indexes to new indexes."""
    # ponytail: O(n²) scan; use a spatial index if very large Breps need this.
    remaining = set(range(len(new_points)))
    mapping = {}
    for old_index, old_point in enumerate(old_points):
        candidates = [
            new_index
            for new_index in remaining
            if old_point.DistanceTo(new_points[new_index]) <= tolerance
        ]
        if len(candidates) == 1:
            mapping[old_index] = candidates[0]
            remaining.remove(candidates[0])
    return mapping


def event_object_ids(event):
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


def event_object(doc, event, object_ids=None):
    if event is None:
        return None
    for name in ("TheObject", "Object", "NewObject"):
        candidate = getattr(event, name, None)
        if candidate is not None and hasattr(candidate, "Geometry"):
            return candidate
    for object_id in object_ids or event_object_ids(event):
        candidate = doc.Objects.Find(object_id)
        if candidate is not None:
            return candidate
    return None


def debug_point(point):
    if point is None:
        return "None"
    return "({:.6f}, {:.6f}, {:.6f})".format(point.X, point.Y, point.Z)


def debug_event(label, event, state):
    if DEBUG:
        print(
            "[Tack coincident] {} event={} ids={} parent={} child={} busy={}".format(
                label,
                type(event).__name__,
                [str(value) for value in event_object_ids(event)],
                state.get("parent_id"),
                state.get("child_id"),
                state.get("busy"),
            )
        )
