import Rhino


ANCHOR_TYPE = "BrepVertex"


def brep_geometry(obj):
    geometry = getattr(obj, "Geometry", obj)
    if isinstance(geometry, Rhino.Geometry.Brep):
        return geometry
    if isinstance(geometry, Rhino.Geometry.Extrusion):
        return geometry.ToBrep()
    return None


def supports_vertex_anchors(obj):
    return brep_geometry(obj) is not None


def anchors(obj):
    brep = brep_geometry(obj)
    if brep is None:
        return []
    return [
        (index, Rhino.Geometry.Point3d(vertex.Location))
        for index, vertex in enumerate(brep.Vertices)
    ]


def resolve(obj, anchor):
    brep = brep_geometry(obj)
    if brep is None:
        return None
    index = int(anchor["index"])
    if index < 0 or index >= brep.Vertices.Count:
        return None
    return Rhino.Geometry.Point3d(brep.Vertices[index].Location)


def replacement_anchor(candidate, anchor, old_anchors, tolerance):
    candidate_anchors = anchors(candidate)
    old_point = dict(old_anchors).get(int(anchor["index"]))
    if old_point is None:
        return candidate_anchors, None
    matching_indexes = [
        index
        for index, point in candidate_anchors
        if old_point.DistanceTo(point) <= tolerance
    ]
    new_index = matching_indexes[0] if len(matching_indexes) == 1 else None
    return candidate_anchors, new_index
