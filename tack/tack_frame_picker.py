import Rhino


def _point(value):
    return Rhino.Geometry.Point3d(value)


def _geometry(obj):
    geometry = obj.Geometry
    if hasattr(geometry, "Vertices"):
        return geometry
    return geometry.ToBrep(True)


def vertex_point(obj, vertex_type, vertex_index):
    geometry = _geometry(obj)
    if vertex_type == "BrepVertex":
        return _point(geometry.Vertices[int(vertex_index)].Location)
    if vertex_type == "MeshVertex":
        return _point(geometry.Vertices[int(vertex_index)])
    return None


def vertex_locations(obj):
    geometry = _geometry(obj)
    vertex_type = (
        "MeshVertex"
        if isinstance(geometry, Rhino.Geometry.Mesh)
        else "BrepVertex"
    )
    return vertex_type, [
        vertex_point(obj, vertex_type, index)
        for index in range(geometry.Vertices.Count)
    ]


def vertex_index_map(old_points, new_points, tolerance):
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


def coincident_vertices(first_obj, second_obj, tolerance):
    first_type, first_points = vertex_locations(first_obj)
    second_type, second_points = vertex_locations(second_obj)
    matches = []
    for first_index, first_point in enumerate(first_points):
        for second_index, second_point in enumerate(second_points):
            if first_point.DistanceTo(second_point) <= tolerance:
                matches.append(
                    (
                        first_type,
                        first_index,
                        second_type,
                        second_index,
                        first_point,
                        second_point,
                    )
                )
    return matches
