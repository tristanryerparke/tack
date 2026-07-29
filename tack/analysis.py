import Rhino

import metadata
import utils
from tack_frame_picker import vertex_index_map, vertex_locations, vertex_point


def inspect_link(doc, state, parent_obj=None, child_obj=None):
    parent = parent_obj or doc.Objects.Find(state["parent_id"])
    child = child_obj or doc.Objects.Find(state["child_id"])
    link = metadata.read_link(child) if child is not None else None
    link = link or state.get("link")
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


def event_object(doc, event):
    if event is None:
        return None
    for name in ("TheObject", "Object", "NewObject"):
        candidate = getattr(event, name, None)
        if candidate is not None and hasattr(candidate, "Geometry"):
            return candidate
    for object_id in utils.event_object_ids(event):
        candidate = doc.Objects.Find(object_id)
        if candidate is not None:
            return candidate
    return None


def matching_vertex_index(points, point_data, tolerance):
    point = Rhino.Geometry.Point3d(*point_data)
    matches = [
        index
        for index, candidate in enumerate(points)
        if point.DistanceTo(candidate) <= tolerance
    ]
    return matches[0] if len(matches) == 1 else None


def replacement_vertex(candidate, link, role, tolerance):
    vertex_type, points = vertex_locations(candidate)
    index = matching_vertex_index(
        points,
        link[role + "_vertex"]["point"],
        tolerance,
    )
    return vertex_type, points, index


def remap_vertex(old_points, new_obj, old_vertex, tolerance):
    new_type, new_points = vertex_locations(new_obj)
    old_index = int(old_vertex["index"])
    if len(old_points) == len(new_points):
        new_index = old_index if old_index < len(new_points) else None
    else:
        new_index = vertex_index_map(old_points, new_points, tolerance).get(old_index)
        if new_index is None:
            new_index = matching_vertex_index(
                new_points,
                old_vertex["point"],
                tolerance,
            )
    return new_type, new_points, new_index
