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
