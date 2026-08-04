import Rhino


ANCHOR_TYPE = "PolylineVertex"


def polyline_geometry(obj):
    geometry = getattr(obj, "Geometry", obj)
    if isinstance(geometry, Rhino.Geometry.PolylineCurve):
        return geometry
    return None


def supports_vertex_anchors(obj):
    return polyline_geometry(obj) is not None


def _vertex_count(polyline):
    count = polyline.PointCount
    if count > 1 and polyline.IsClosed:
        first = polyline.Point(0)
        last = polyline.Point(count - 1)
        if first.EpsilonEquals(last, Rhino.RhinoMath.ZeroTolerance):
            count -= 1
    return count


def anchors(obj):
    polyline = polyline_geometry(obj)
    if polyline is None:
        return []
    return [
        (index, Rhino.Geometry.Point3d(polyline.Point(index)))
        for index in range(_vertex_count(polyline))
    ]


def resolve(obj, anchor):
    polyline = polyline_geometry(obj)
    if polyline is None:
        return None
    index = int(anchor["index"])
    if index < 0 or index >= _vertex_count(polyline):
        return None
    return Rhino.Geometry.Point3d(polyline.Point(index))


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
    index = int(anchor["index"])
    if index not in dict(candidate_anchors):
        index = None
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
    return new_anchors, new_index
