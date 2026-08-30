"""Derive and resolve analytic geometry anchors.

Anchor dictionaries use the model documented in
``better-plane-selector-osnap-picker.md``: a ``type`` discriminator and only
the metadata owned by that type's handler. There is no legacy universal index.
"""

import math

import Rhino


BOUNDING_BOX_CENTER = "bounding_box_center"
BREP_VERTEX = "brep_vertex"
POLYLINE_VERTEX = "polyline_vertex"
CURVE_START = "curve_start"
CURVE_END = "curve_end"
BREP_EDGE_MIDPOINT = "brep_edge_midpoint"
POLYLINE_SEGMENT_MIDPOINT = "polyline_segment_midpoint"
CURVE_MIDPOINT = "curve_midpoint"
CIRCULAR_EDGE_CENTER = "circular_edge_center"
CURVE_CENTER = "curve_center"
BREP_FACE_CENTER = "brep_face_center"
BREP_EDGE_QUADRANT = "brep_edge_quadrant"
CURVE_QUADRANT = "curve_quadrant"


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


def bounding_box_center(obj):
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
    if (
        count > 1
        and polyline.IsClosed
        and polyline.Point(0).EpsilonEquals(
            polyline.Point(count - 1),
            Rhino.RhinoMath.ZeroTolerance,
        )
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


def _try_get_conic(curve, method_name, tolerance):
    if curve is None:
        return None
    method = getattr(curve, method_name, None)
    if method is None:
        return None
    try:
        result = method()
    except TypeError:
        result = method(tolerance)
    if isinstance(result, tuple):
        success, conic = result
        return conic if success else None
    return result if result else None


def _circle(curve, tolerance):
    return _try_get_conic(curve, "TryGetCircle", tolerance)


def _arc(curve, tolerance):
    return _try_get_conic(curve, "TryGetArc", tolerance)


def _ellipse(curve, tolerance):
    return _try_get_conic(curve, "TryGetEllipse", tolerance)


def _face_center(face):
    try:
        properties = Rhino.Geometry.AreaMassProperties.Compute(face)
    except Exception:
        properties = None
    if properties is None:
        return None
    return Rhino.Geometry.Point3d(properties.Centroid)


def _curve_contains_point(curve, point, tolerance):
    try:
        success, parameter = curve.ClosestPoint(point)
    except Exception:
        return False
    return success and curve.PointAt(parameter).DistanceTo(point) <= tolerance


def _quadrant_points(curve, tolerance):
    """Return valid ``(quadrant, point)`` pairs in the conic's own plane.

    Quadrants 0..3 are +X, +Y, -X, and -Y. Testing each point against the
    original curve excludes quarter-turn positions outside a trimmed arc.
    """
    arc = _arc(curve, tolerance)
    if arc is not None:
        plane = arc.Plane
        radius_x = arc.Radius
        radius_y = arc.Radius
    else:
        ellipse = _ellipse(curve, tolerance)
        if ellipse is None:
            return []
        plane = ellipse.Plane
        radius_x = ellipse.Radius1
        radius_y = ellipse.Radius2

    result = []
    for quadrant in range(4):
        angle = quadrant * math.pi / 2.0
        point = plane.PointAt(
            radius_x * math.cos(angle),
            radius_y * math.sin(angle),
        )
        if _curve_contains_point(curve, point, tolerance):
            result.append((quadrant, Rhino.Geometry.Point3d(point)))
    return result


def _component_index(obj_ref):
    component = getattr(obj_ref, "GeometryComponentIndex", None)
    if component is None:
        component_method = getattr(obj_ref, "ComponentIndex", None)
        component = component_method() if component_method is not None else None
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


def _nonnegative_integer(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _quadrant_number(value):
    return _nonnegative_integer(value) and value < 4


class _AnchorTypeHandler:
    def __init__(self, feature_type, metadata_validators, generate):
        self.feature_type = feature_type
        self.metadata_validators = metadata_validators
        self.generate = generate

    def validates(self, definition):
        if not isinstance(definition, dict):
            return False
        expected_fields = {"type"}.union(self.metadata_validators)
        if set(definition) != expected_fields:
            return False
        if definition.get("type") != self.feature_type:
            return False
        return all(
            validator(definition[name])
            for name, validator in self.metadata_validators.items()
        )

    def candidates(self, obj, tolerance):
        return [
            (
                {"type": self.feature_type, **metadata},
                Rhino.Geometry.Point3d(point),
            )
            for metadata, point in self.generate(obj, tolerance)
        ]

    def resolve(self, obj, definition, tolerance):
        if not self.validates(definition):
            return None
        matches = [
            point
            for candidate, point in self.candidates(obj, tolerance)
            if candidate == definition
        ]
        return matches[0] if len(matches) == 1 else None


def _bounding_box_features(obj, tolerance):
    center = bounding_box_center(obj)
    return [] if center is None else [({}, center)]


def _brep_vertex_features(obj, tolerance):
    brep = _brep(obj)
    if brep is None:
        return []
    return [
        ({"vertex_index": index}, vertex.Location)
        for index, vertex in enumerate(brep.Vertices)
    ]


def _polyline_vertex_features(obj, tolerance):
    curve = _curve(obj)
    if not isinstance(curve, Rhino.Geometry.PolylineCurve):
        return []
    return [
        ({"vertex_index": index}, curve.Point(index))
        for index in range(_polyline_vertex_count(curve))
    ]


def _curve_start_features(obj, tolerance):
    curve = _curve(obj)
    if curve is None or curve.IsClosed:
        return []
    return [({}, curve.PointAtStart)]


def _curve_end_features(obj, tolerance):
    curve = _curve(obj)
    if curve is None or curve.IsClosed:
        return []
    return [({}, curve.PointAtEnd)]


def _brep_edge_midpoint_features(obj, tolerance):
    brep = _brep(obj)
    if brep is None:
        return []
    return [
        ({"edge_index": index}, midpoint)
        for index, edge in enumerate(brep.Edges)
        for midpoint in (_curve_midpoint(edge),)
        if midpoint is not None
    ]


def _polyline_segment_midpoint_features(obj, tolerance):
    curve = _curve(obj)
    if not isinstance(curve, Rhino.Geometry.PolylineCurve):
        return []
    return [
        (
            {"segment_index": index},
            Rhino.Geometry.Line(
                curve.Point(index),
                curve.Point(index + 1),
            ).PointAt(0.5),
        )
        for index in range(curve.PointCount - 1)
    ]


def _curve_midpoint_features(obj, tolerance):
    curve = _curve(obj)
    if curve is None or isinstance(curve, Rhino.Geometry.PolylineCurve):
        return []
    midpoint = _curve_midpoint(curve)
    return [] if midpoint is None else [({}, midpoint)]


def _circular_edge_center_features(obj, tolerance):
    brep = _brep(obj)
    if brep is None:
        return []
    result = []
    for index, edge in enumerate(brep.Edges):
        circle = _circle(edge.DuplicateCurve(), tolerance)
        if circle is not None:
            result.append(({"edge_index": index}, circle.Center))
    return result


def _curve_center_features(obj, tolerance):
    circle = _circle(_curve(obj), tolerance)
    return [] if circle is None else [({}, circle.Center)]


def _brep_face_center_features(obj, tolerance):
    brep = _brep(obj)
    if brep is None:
        return []
    return [
        ({"face_index": index}, center)
        for index, face in enumerate(brep.Faces)
        for center in (_face_center(face),)
        if center is not None
    ]


def _brep_edge_quadrant_features(obj, tolerance):
    brep = _brep(obj)
    if brep is None:
        return []
    return [
        (
            {"edge_index": edge_index, "quadrant": quadrant},
            point,
        )
        for edge_index, edge in enumerate(brep.Edges)
        for quadrant, point in _quadrant_points(edge, tolerance)
    ]


def _curve_quadrant_features(obj, tolerance):
    curve = _curve(obj)
    if curve is None:
        return []
    return [
        ({"quadrant": quadrant}, point)
        for quadrant, point in _quadrant_points(curve, tolerance)
    ]


_HANDLERS = {
    handler.feature_type: handler
    for handler in (
        _AnchorTypeHandler(BOUNDING_BOX_CENTER, {}, _bounding_box_features),
        _AnchorTypeHandler(
            BREP_VERTEX,
            {"vertex_index": _nonnegative_integer},
            _brep_vertex_features,
        ),
        _AnchorTypeHandler(
            POLYLINE_VERTEX,
            {"vertex_index": _nonnegative_integer},
            _polyline_vertex_features,
        ),
        _AnchorTypeHandler(CURVE_START, {}, _curve_start_features),
        _AnchorTypeHandler(CURVE_END, {}, _curve_end_features),
        _AnchorTypeHandler(
            BREP_EDGE_MIDPOINT,
            {"edge_index": _nonnegative_integer},
            _brep_edge_midpoint_features,
        ),
        _AnchorTypeHandler(
            POLYLINE_SEGMENT_MIDPOINT,
            {"segment_index": _nonnegative_integer},
            _polyline_segment_midpoint_features,
        ),
        _AnchorTypeHandler(CURVE_MIDPOINT, {}, _curve_midpoint_features),
        _AnchorTypeHandler(
            CIRCULAR_EDGE_CENTER,
            {"edge_index": _nonnegative_integer},
            _circular_edge_center_features,
        ),
        _AnchorTypeHandler(CURVE_CENTER, {}, _curve_center_features),
        _AnchorTypeHandler(
            BREP_FACE_CENTER,
            {"face_index": _nonnegative_integer},
            _brep_face_center_features,
        ),
        _AnchorTypeHandler(
            BREP_EDGE_QUADRANT,
            {
                "edge_index": _nonnegative_integer,
                "quadrant": _quadrant_number,
            },
            _brep_edge_quadrant_features,
        ),
        _AnchorTypeHandler(
            CURVE_QUADRANT,
            {"quadrant": _quadrant_number},
            _curve_quadrant_features,
        ),
    )
}


def _candidates(obj, feature_type, tolerance):
    handler = _HANDLERS.get(feature_type)
    return [] if handler is None else handler.candidates(obj, tolerance)


def _unique_match(candidates, picked_point, tolerance):
    matches = [
        candidate
        for candidate in candidates
        if candidate[1].DistanceTo(picked_point) <= tolerance
    ]
    return matches[0] if len(matches) == 1 else None


def _narrow_component(candidates, locator_name, component_index):
    if component_index is None:
        return candidates
    narrowed = [
        candidate
        for candidate in candidates
        if candidate[0].get(locator_name) == component_index
    ]
    return narrowed if narrowed else candidates


def _end_candidates(obj, component_type, component_index, tolerance):
    brep = _brep(obj)
    curve = _curve(obj)
    if brep is not None:
        candidates = _candidates(obj, BREP_VERTEX, tolerance)
        if component_type == "brepvertex":
            return _narrow_component(
                candidates,
                "vertex_index",
                component_index,
            )
        return candidates
    if isinstance(curve, Rhino.Geometry.PolylineCurve):
        return _candidates(obj, POLYLINE_VERTEX, tolerance)
    return (
        _candidates(obj, CURVE_START, tolerance)
        + _candidates(obj, CURVE_END, tolerance)
    )


def _midpoint_candidates(obj, component_type, component_index, tolerance):
    brep = _brep(obj)
    curve = _curve(obj)
    if brep is not None:
        candidates = _candidates(obj, BREP_EDGE_MIDPOINT, tolerance)
        if component_type in ("brepedge", "extrusionwalledge"):
            return _narrow_component(candidates, "edge_index", component_index)
        return candidates
    if isinstance(curve, Rhino.Geometry.PolylineCurve):
        return _candidates(obj, POLYLINE_SEGMENT_MIDPOINT, tolerance)
    return _candidates(obj, CURVE_MIDPOINT, tolerance)


def _quadrant_candidates(obj, component_type, component_index, tolerance):
    if _brep(obj) is not None:
        candidates = _candidates(obj, BREP_EDGE_QUADRANT, tolerance)
        if component_type in ("brepedge", "extrusionwalledge"):
            return _narrow_component(candidates, "edge_index", component_index)
        return candidates
    return _candidates(obj, CURVE_QUADRANT, tolerance)


def derive(obj_ref, picked_point, osnap_type, tolerance):
    """Return ``(definition, point)`` for one unambiguous object snap."""
    if obj_ref is None:
        return None
    obj = obj_ref.Object()
    if obj is None:
        return None

    snap_name = str(osnap_type).split(".")[-1].lower()
    component_type, component_index = _component_index(obj_ref)

    if snap_name in ("end", "vertex"):
        candidates = _end_candidates(
            obj,
            component_type,
            component_index,
            tolerance,
        )
        return _unique_match(candidates, picked_point, tolerance)

    if snap_name in ("mid", "midpoint"):
        candidates = _midpoint_candidates(
            obj,
            component_type,
            component_index,
            tolerance,
        )
        return _unique_match(candidates, picked_point, tolerance)

    if snap_name == "center":
        if _brep(obj) is not None:
            edge_candidates = _candidates(obj, CIRCULAR_EDGE_CENTER, tolerance)
            if component_type in ("brepedge", "extrusionwalledge"):
                edge_candidates = _narrow_component(
                    edge_candidates,
                    "edge_index",
                    component_index,
                )
            match = _unique_match(edge_candidates, picked_point, tolerance)
            if match is not None:
                return match

            face_candidates = _candidates(obj, BREP_FACE_CENTER, tolerance)
            if component_type == "brepface":
                face_candidates = _narrow_component(
                    face_candidates,
                    "face_index",
                    component_index,
                )
            return _unique_match(face_candidates, picked_point, tolerance)

        return _unique_match(
            _candidates(obj, CURVE_CENTER, tolerance),
            picked_point,
            tolerance,
        )

    if snap_name in ("quadrant", "quad"):
        # Some Rhino fallback paths report a coincident lower-priority snap.
        # Preserve the documented identity order: End/Vertex, Midpoint, Quad.
        for candidates in (
            _end_candidates(obj, component_type, component_index, tolerance),
            _midpoint_candidates(obj, component_type, component_index, tolerance),
            _quadrant_candidates(obj, component_type, component_index, tolerance),
        ):
            match = _unique_match(candidates, picked_point, tolerance)
            if match is not None:
                return match

    return None


def validate(definition):
    """Return whether a dictionary exactly matches one new-model anchor type."""
    if not isinstance(definition, dict):
        return False
    handler = _HANDLERS.get(definition.get("type"))
    return handler is not None and handler.validates(definition)


def circular_edge(obj, definition, tolerance):
    """Resolve a circular-edge anchor to its current Brep edge and circle."""
    if (
        not validate(definition)
        or definition.get("type") != CIRCULAR_EDGE_CENTER
    ):
        return None
    brep = _brep(obj)
    edge_index = definition["edge_index"]
    if brep is None or edge_index >= brep.Edges.Count:
        return None
    edge = brep.Edges[edge_index]
    circle = _circle(edge.DuplicateCurve(), tolerance)
    return None if circle is None else (edge, circle)


def circular_curve(obj, definition, tolerance):
    """Resolve a circular-curve anchor to its current curve and circle."""
    if not validate(definition) or definition.get("type") != CURVE_CENTER:
        return None
    curve = _curve(obj)
    circle = _circle(curve, tolerance)
    return None if circle is None else (curve, circle)


def resolve(obj, definition, tolerance):
    """Regenerate one anchor point using its type-specific handler."""
    if not isinstance(definition, dict):
        return None
    handler = _HANDLERS.get(definition.get("type"))
    return None if handler is None else handler.resolve(obj, definition, tolerance)
