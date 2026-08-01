import Rhino

from tack.utils import vertex_index_map, vertices_as_points


def matching_vertex_index(points, point_data, tolerance):
    point = Rhino.Geometry.Point3d(*point_data)
    matches = [
        index
        for index, candidate in enumerate(points)
        if point.DistanceTo(candidate) <= tolerance
    ]
    return matches[0] if len(matches) == 1 else None


def replacement_vertex(candidate, link, role, tolerance):
    points = vertices_as_points(candidate)
    index = matching_vertex_index(
        points,
        link[role + "_vertex"]["point"],
        tolerance,
    )
    return "BrepVertex", points, index


def remap_vertex(old_obj, new_obj, old_vertex, tolerance):
    old_points = vertices_as_points(old_obj)
    new_points = vertices_as_points(new_obj)
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
    return "BrepVertex", new_points, new_index
