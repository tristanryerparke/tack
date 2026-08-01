import Rhino


ANCHOR_TYPE = "BrepVertex"


def brep_geometry(obj):
    geometry = getattr(obj, "Geometry", obj)
    if isinstance(geometry, Rhino.Geometry.Brep):
        return geometry
    return None


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


def _matching_index(candidate_anchors, point_data, tolerance):
    point = Rhino.Geometry.Point3d(*point_data)
    matches = [
        index
        for index, candidate in candidate_anchors
        if point.DistanceTo(candidate) <= tolerance
    ]
    return matches[0] if len(matches) == 1 else None


def _index_map(old_anchors, new_anchors, tolerance):
    remaining = {index for index, _ in new_anchors}
    new_points = dict(new_anchors)
    mapping = {}
    for old_index, old_point in old_anchors:
        candidates = [
            new_index
            for new_index in remaining
            if old_point.DistanceTo(new_points[new_index]) <= tolerance
        ]
        if len(candidates) == 1:
            mapping[old_index] = candidates[0]
            remaining.remove(candidates[0])
    return mapping


def replacement_anchor(candidate, anchor, tolerance):
    candidate_anchors = anchors(candidate)
    index = _matching_index(candidate_anchors, anchor["point"], tolerance)
    return candidate_anchors, index


def remap_anchor(old_obj, new_obj, anchor, tolerance):
    old_anchors = anchors(old_obj)
    new_anchors = anchors(new_obj)
    old_index = int(anchor["index"])
    new_indexes = {index for index, _ in new_anchors}
    if len(old_anchors) == len(new_anchors):
        new_index = old_index if old_index in new_indexes else None
    else:
        new_index = _index_map(
            old_anchors,
            new_anchors,
            tolerance,
        ).get(old_index)
        if new_index is None:
            new_index = _matching_index(
                new_anchors,
                anchor["point"],
                tolerance,
            )
    return new_anchors, new_index
