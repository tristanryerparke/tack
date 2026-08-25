import Rhino


ANCHOR_TYPE = "Smart"
BBOX_CENTER = "BoundingBoxCenter"
BREP_VERTEX = "BrepVertex"
POLYLINE_VERTEX = "PolylineVertex"
CURVE_END = "CurveEnd"
BREP_EDGE_MIDPOINT = "BrepEdgeMidpoint"
POLYLINE_SEGMENT_MIDPOINT = "PolylineSegmentMidpoint"
CURVE_MIDPOINT = "CurveMidpoint"
CIRCULAR_EDGE_CENTER = "CircularEdgeCenter"
CURVE_CENTER = "CurveCenter"
BREP_FACE_CENTER = "BrepFaceCenter"


def _geometry(obj):
    return getattr(obj, "Geometry", obj)


def _brep(obj):
    geometry = _geometry(obj)
    if isinstance(geometry, Rhino.Geometry.Brep):
        return geometry
    if isinstance(geometry, Rhino.Geometry.Extrusion):
        return geometry.ToBrep()
    return None


def _curve(obj):
    geometry = _geometry(obj)
    return geometry if isinstance(geometry, Rhino.Geometry.Curve) else None


def _bounding_box_center(obj):
    geometry = _geometry(obj)
    try:
        bounding_box = geometry.GetBoundingBox(True)
    except Exception:
        return None
    if not bounding_box.IsValid:
        return None
    return Rhino.Geometry.Point3d(bounding_box.Center)


def _polyline_vertex_count(polyline):
    count = polyline.PointCount
    if count > 1 and polyline.IsClosed:
        if polyline.Point(0).EpsilonEquals(
            polyline.Point(count - 1),
            Rhino.RhinoMath.ZeroTolerance,
        ):
            count -= 1
    return count


def _curve_midpoint(curve):
    if curve is None:
        return None
    try:
        success, parameter = curve.NormalizedLengthParameter(0.5)
    except Exception:
        success = False
    if success:
        return Rhino.Geometry.Point3d(curve.PointAt(parameter))
    return Rhino.Geometry.Point3d(curve.PointAt(curve.Domain.Mid))


def _circle(curve):
    if curve is None:
        return None
    try:
        result = curve.TryGetCircle()
    except TypeError:
        result = curve.TryGetCircle(1e-6)
    if isinstance(result, tuple):
        success, circle = result
        return circle if success else None
    return result if result else None


def _face_center(face):
    try:
        properties = Rhino.Geometry.AreaMassProperties.Compute(face)
    except Exception:
        properties = None
    if properties is None:
        return None
    return Rhino.Geometry.Point3d(properties.Centroid)


def anchors(obj, kind=None):
    if kind == BBOX_CENTER:
        center = _bounding_box_center(obj)
        return [] if center is None else [((kind, 0), center)]

    brep = _brep(obj)
    if kind == BREP_VERTEX:
        if brep is None:
            return []
        return [
            ((kind, index), Rhino.Geometry.Point3d(vertex.Location))
            for index, vertex in enumerate(brep.Vertices)
        ]

    curve = _curve(obj)
    if kind == POLYLINE_VERTEX:
        if not isinstance(curve, Rhino.Geometry.PolylineCurve):
            return []
        return [
            ((kind, index), Rhino.Geometry.Point3d(curve.Point(index)))
            for index in range(_polyline_vertex_count(curve))
        ]

    if kind == CURVE_END:
        if curve is None or curve.IsClosed:
            return []
        return [
            ((kind, 0), Rhino.Geometry.Point3d(curve.PointAtStart)),
            ((kind, 1), Rhino.Geometry.Point3d(curve.PointAtEnd)),
        ]

    if kind == BREP_EDGE_MIDPOINT:
        if brep is None:
            return []
        return [
            ((kind, index), midpoint)
            for index, edge in enumerate(brep.Edges)
            for midpoint in (_curve_midpoint(edge),)
            if midpoint is not None
        ]

    if kind == POLYLINE_SEGMENT_MIDPOINT:
        if not isinstance(curve, Rhino.Geometry.PolylineCurve):
            return []
        return [
            (
                (kind, index),
                Rhino.Geometry.Point3d(
                    Rhino.Geometry.Line(
                        curve.Point(index),
                        curve.Point(index + 1),
                    ).PointAt(0.5)
                ),
            )
            for index in range(curve.PointCount - 1)
        ]

    if kind == CURVE_MIDPOINT:
        if curve is None or isinstance(curve, Rhino.Geometry.PolylineCurve):
            return []
        midpoint = _curve_midpoint(curve)
        return [] if midpoint is None else [((kind, 0), midpoint)]

    if kind == CIRCULAR_EDGE_CENTER:
        if brep is None:
            return []
        result = []
        for index, edge in enumerate(brep.Edges):
            circle = _circle(edge.DuplicateCurve())
            if circle is not None:
                result.append(
                    ((kind, index), Rhino.Geometry.Point3d(circle.Center))
                )
        return result

    if kind == CURVE_CENTER:
        circle = _circle(curve)
        if circle is None:
            return []
        return [((kind, 0), Rhino.Geometry.Point3d(circle.Center))]

    if kind == BREP_FACE_CENTER:
        if brep is None:
            return []
        return [
            ((kind, index), center)
            for index, face in enumerate(brep.Faces)
            for center in (_face_center(face),)
            if center is not None
        ]

    return []


def anchors_for(obj, anchor):
    return anchors(obj, anchor.get("kind"))


def anchor_key(anchor):
    return anchor.get("kind"), int(anchor["index"])


def resolve(obj, anchor):
    return dict(anchors_for(obj, anchor)).get(anchor_key(anchor))


def replacement_anchor(candidate, anchor, old_anchors, tolerance):
    candidate_anchors = anchors_for(candidate, anchor)
    saved_key = anchor_key(anchor)
    if anchor.get("kind") == BBOX_CENTER:
        return candidate_anchors, (
            saved_key if saved_key in dict(candidate_anchors) else None
        )

    old_point = dict(old_anchors).get(saved_key)
    if old_point is None:
        return candidate_anchors, None
    matching_keys = [
        key
        for key, point in candidate_anchors
        if old_point.DistanceTo(point) <= tolerance
    ]
    new_key = matching_keys[0] if len(matching_keys) == 1 else None
    return candidate_anchors, new_key


def _component_index(obj_ref):
    component = getattr(obj_ref, "GeometryComponentIndex", None)
    if component is None:
        return None, None
    try:
        index = int(component.Index)
    except Exception:
        return None, None
    if index < 0:
        return None, None
    component_type = str(component.ComponentIndexType).split(".")[-1].lower()
    return component_type, index


def _matching(candidates, point, tolerance):
    matches = [
        candidate
        for candidate in candidates
        if candidate[1].DistanceTo(point) <= tolerance
    ]
    return matches[0] if len(matches) == 1 else None


def derive(obj_ref, picked_point, osnap_type, tolerance):
    if obj_ref is None:
        return None
    obj = obj_ref.Object()
    if obj is None:
        return None

    snap_name = str(osnap_type).split(".")[-1].lower()
    component_type, component_index = _component_index(obj_ref)
    brep = _brep(obj)
    curve = _curve(obj)

    candidates = []
    if snap_name in ("end", "vertex"):
        if brep is not None:
            candidates = anchors(obj, BREP_VERTEX)
        elif isinstance(curve, Rhino.Geometry.PolylineCurve):
            candidates = anchors(obj, POLYLINE_VERTEX)
        else:
            candidates = anchors(obj, CURVE_END)

    elif snap_name in ("mid", "midpoint"):
        if brep is not None:
            all_candidates = anchors(obj, BREP_EDGE_MIDPOINT)
            if component_type == "brepedge":
                candidates = [
                    candidate
                    for candidate in all_candidates
                    if candidate[0][1] == component_index
                ]
            else:
                candidates = all_candidates
        elif isinstance(curve, Rhino.Geometry.PolylineCurve):
            candidates = anchors(obj, POLYLINE_SEGMENT_MIDPOINT)
        else:
            candidates = anchors(obj, CURVE_MIDPOINT)

    elif snap_name == "center":
        if brep is not None:
            edge_candidates = anchors(obj, CIRCULAR_EDGE_CENTER)
            if component_type == "brepedge":
                edge_candidates = [
                    candidate
                    for candidate in edge_candidates
                    if candidate[0][1] == component_index
                ]
            match = _matching(edge_candidates, picked_point, tolerance)
            if match is not None:
                return ANCHOR_TYPE, match[0], match[1]

            face_candidates = anchors(obj, BREP_FACE_CENTER)
            if component_type == "brepface":
                face_candidates = [
                    candidate
                    for candidate in face_candidates
                    if candidate[0][1] == component_index
                ]
            candidates = face_candidates
        else:
            candidates = anchors(obj, CURVE_CENTER)

    match = _matching(candidates, picked_point, tolerance)
    if match is None:
        return None
    return ANCHOR_TYPE, match[0], match[1]


def bounding_box_center_anchor(obj):
    candidates = anchors(obj, BBOX_CENTER)
    if not candidates:
        return None
    key, point = candidates[0]
    return ANCHOR_TYPE, key, point
