import Rhino


SUPPLIED = "supplied"
DERIVED = "derived"


def _osnap_name(osnap_type):
    return str(osnap_type).split(".")[-1].lower()


def _geometry_component_index(obj_ref):
    component_index = getattr(obj_ref, "GeometryComponentIndex", None)
    if component_index is not None:
        return component_index

    component_index_method = getattr(obj_ref, "ComponentIndex", None)
    if component_index_method is not None:
        return component_index_method()
    return None


def _object_brep(obj_ref):
    object_method = getattr(obj_ref, "Object", None)
    if object_method is None:
        return None
    rhino_object = object_method()
    if rhino_object is None:
        return None

    geometry = rhino_object.Geometry
    if isinstance(geometry, Rhino.Geometry.Brep):
        return geometry
    if isinstance(geometry, Rhino.Geometry.Extrusion):
        return geometry.ToBrep()
    return None


def _object_curve(obj_ref):
    curve_method = getattr(obj_ref, "Curve", None)
    if curve_method is not None:
        curve = curve_method()
        if curve is not None:
            return curve

    object_method = getattr(obj_ref, "Object", None)
    if object_method is None:
        return None
    rhino_object = object_method()
    if rhino_object is None:
        return None
    geometry = rhino_object.Geometry
    if isinstance(geometry, Rhino.Geometry.Curve):
        return geometry
    return None


def _nearest_brep_vertex(brep, picked_point):
    if brep is None or brep.Vertices.Count == 0:
        return None, None
    index = min(
        range(brep.Vertices.Count),
        key=lambda candidate: brep.Vertices[candidate].Location.DistanceTo(
            picked_point
        ),
    )
    return index, brep.Vertices[index].Location


def _nearest_brep_edge(brep, picked_point):
    if brep is None:
        return None, None

    closest = None
    for index in range(brep.Edges.Count):
        success, parameter = brep.Edges[index].ClosestPoint(picked_point)
        if not success:
            continue
        distance = brep.Edges[index].PointAt(parameter).DistanceTo(picked_point)
        if closest is None or distance < closest[0]:
            closest = distance, index
    if closest is None:
        return None, None
    return closest[1], closest[0]


def _nearest_brep_face(brep, picked_point):
    if brep is None:
        return None, None

    closest = None
    for index in range(brep.Faces.Count):
        try:
            success, u, v = brep.Faces[index].ClosestPoint(picked_point)
        except Exception:
            continue
        if not success:
            continue
        distance = brep.Faces[index].PointAt(u, v).DistanceTo(picked_point)
        if closest is None or distance < closest[0]:
            closest = distance, index
    if closest is None:
        return None, None
    return closest[1], closest[0]


def _polyline_point_index(curve, picked_point):
    if not isinstance(curve, Rhino.Geometry.PolylineCurve):
        return None
    if curve.PointCount == 0:
        return None
    return min(
        range(curve.PointCount),
        key=lambda index: curve.Point(index).DistanceTo(picked_point),
    )


def _polyline_segment_index(curve, picked_point):
    if not isinstance(curve, Rhino.Geometry.PolylineCurve):
        return None
    if curve.PointCount < 2:
        return None

    closest = None
    for index in range(curve.PointCount - 1):
        line = Rhino.Geometry.Line(curve.Point(index), curve.Point(index + 1))
        parameter = max(0.0, min(1.0, line.ClosestParameter(picked_point)))
        distance = line.PointAt(parameter).DistanceTo(picked_point)
        if closest is None or distance < closest[0]:
            closest = distance, index
    return None if closest is None else closest[1]


def _end_vertex(obj_ref, picked_point):
    vertex_method = getattr(obj_ref, "Vertex", None)
    if vertex_method is not None:
        brep_vertex = vertex_method()
        if brep_vertex is not None:
            return brep_vertex.Location, SUPPLIED

    brep = _object_brep(obj_ref)
    if brep is not None:
        _, vertex = _nearest_brep_vertex(brep, picked_point)
        return vertex, DERIVED

    curve = _object_curve(obj_ref)
    if curve is None:
        return None, None
    return (
        min(
            (curve.PointAtStart, curve.PointAtEnd),
            key=lambda endpoint: endpoint.DistanceTo(picked_point),
        ),
        DERIVED,
    )


def _end_vertex_index(obj_ref, picked_point):
    component_index = _geometry_component_index(obj_ref)
    if component_index is not None:
        component_type = _osnap_name(component_index.ComponentIndexType)
        if component_type in ("brepvertex", "meshvertex", "subdvertex"):
            return component_index.Index, SUPPLIED

    vertex_method = getattr(obj_ref, "Vertex", None)
    if vertex_method is not None:
        brep_vertex = vertex_method()
        if brep_vertex is not None:
            vertex_index = getattr(brep_vertex, "VertexIndex", None)
            if vertex_index is not None:
                return vertex_index, SUPPLIED

    edge_method = getattr(obj_ref, "Edge", None)
    if edge_method is not None:
        edge = edge_method()
        if edge is not None:
            edge_vertex = min(
                (edge.StartVertex, edge.EndVertex),
                key=lambda vertex: vertex.Location.DistanceTo(picked_point),
            )
            return edge_vertex.VertexIndex, SUPPLIED

    brep = _object_brep(obj_ref)
    index, _ = _nearest_brep_vertex(brep, picked_point)
    if index is not None:
        return index, DERIVED

    index = _polyline_point_index(_object_curve(obj_ref), picked_point)
    if index is not None:
        return index, DERIVED
    return None, None


def _circle_from_curve(curve):
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


def _center_component(obj_ref, picked_point, osnap_name):
    if osnap_name != "center":
        return None, None, None, None

    component_index = _geometry_component_index(obj_ref)
    if component_index is not None:
        component_type = _osnap_name(component_index.ComponentIndexType)
        if component_type == "brepface":
            return "face center", "brepface", component_index.Index, SUPPLIED
        if component_type in ("brepedge", "extrusionwalledge"):
            brep = _object_brep(obj_ref)
            if brep is not None and 0 <= component_index.Index < brep.Edges.Count:
                circle = _circle_from_curve(
                    brep.Edges[component_index.Index].DuplicateCurve()
                )
                if circle is not None:
                    return (
                        "circular edge",
                        component_type,
                        component_index.Index,
                        SUPPLIED,
                    )

    circle = _circle_from_curve(_object_curve(obj_ref))
    if circle is not None:
        return "circular curve", None, None, SUPPLIED

    edge_type, edge_index, edge_source = _edge_component(
        obj_ref,
        picked_point,
        osnap_name,
    )
    if edge_index is not None:
        brep = _object_brep(obj_ref)
        if brep is not None:
            circle = _circle_from_curve(brep.Edges[edge_index].DuplicateCurve())
            if circle is not None:
                return "circular edge", edge_type, edge_index, edge_source

    face_type, face_index, face_source = _face_component(
        obj_ref,
        picked_point,
        osnap_name,
    )
    if face_index is not None:
        return "face center", face_type, face_index, face_source
    return None, None, None, None


def _face_component(obj_ref, picked_point, osnap_name):
    component_index = _geometry_component_index(obj_ref)
    if component_index is not None:
        component_type = _osnap_name(component_index.ComponentIndexType)
        if component_type == "brepface":
            return component_type, component_index.Index, SUPPLIED

    if osnap_name not in ("center", "face"):
        return None, None, None

    face_index, _ = _nearest_brep_face(
        _object_brep(obj_ref),
        picked_point,
    )
    if face_index is None:
        return None, None, None
    return "brepface-derived", face_index, DERIVED


def _edge_component(obj_ref, picked_point, osnap_name):
    component_index = _geometry_component_index(obj_ref)
    if component_index is not None:
        component_type = _osnap_name(component_index.ComponentIndexType)
        if component_type in (
            "brepedge",
            "extrusionwalledge",
            "meshtopologyedge",
            "polycurvesegment",
            "subdedge",
        ):
            return component_type, component_index.Index, SUPPLIED

    brep = _object_brep(obj_ref)
    edge_index, _ = _nearest_brep_edge(brep, picked_point)
    if edge_index is not None:
        return "brepedge-derived", edge_index, DERIVED

    if osnap_name in ("mid", "midpoint"):
        polyline_segment = _polyline_segment_index(
            _object_curve(obj_ref),
            picked_point,
        )
        if polyline_segment is not None:
            return "polyline-segment-derived", polyline_segment, DERIVED
    return None, None, None


def derive_snap_data(obj_ref, picked_point, osnap_type):
    """Derive component details missing from a GetPoint ObjRef callback."""
    result = {
        "end_vertex": None,
        "end_vertex_source": None,
        "end_vertex_index": None,
        "end_vertex_index_source": None,
        "edge_component_type": None,
        "edge_index": None,
        "edge_index_source": None,
        "midpoint": None,
        "midpoint_source": None,
        "face_component_type": None,
        "face_index": None,
        "face_index_source": None,
        "center_kind": None,
        "center_component_type": None,
        "center_index": None,
        "center_source": None,
    }
    if obj_ref is None:
        return result

    snap_name = _osnap_name(osnap_type)
    (
        result["edge_component_type"],
        result["edge_index"],
        result["edge_index_source"],
    ) = _edge_component(obj_ref, picked_point, snap_name)
    (
        result["face_component_type"],
        result["face_index"],
        result["face_index_source"],
    ) = _face_component(obj_ref, picked_point, snap_name)
    (
        result["center_kind"],
        result["center_component_type"],
        result["center_index"],
        result["center_source"],
    ) = _center_component(obj_ref, picked_point, snap_name)
    if result["center_kind"] != "face center":
        result["face_component_type"] = None
        result["face_index"] = None
        result["face_index_source"] = None
    if snap_name in ("end", "vertex"):
        (
            result["end_vertex"],
            result["end_vertex_source"],
        ) = _end_vertex(obj_ref, picked_point)
        (
            result["end_vertex_index"],
            result["end_vertex_index_source"],
        ) = _end_vertex_index(obj_ref, picked_point)
    elif snap_name in ("mid", "midpoint"):
        result["midpoint"] = picked_point
        result["midpoint_source"] = SUPPLIED
    return result


def brep_vertex_at(obj_ref, index):
    brep = _object_brep(obj_ref)
    if brep is None or index < 0 or index >= brep.Vertices.Count:
        return None
    return brep.Vertices[index]


def object_bbox_center(obj_ref):
    object_method = getattr(obj_ref, "Object", None)
    if object_method is None:
        return None
    rhino_object = object_method()
    if rhino_object is None:
        return None
    geometry = getattr(rhino_object, "Geometry", None)
    if geometry is None:
        return None
    bounding_box = geometry.GetBoundingBox(True)
    if not bounding_box.IsValid:
        return None
    return bounding_box.Center


def polyline_vertex_at(obj_ref, index):
    curve = _object_curve(obj_ref)
    if not isinstance(curve, Rhino.Geometry.PolylineCurve):
        return None
    if index < 0 or index >= curve.PointCount:
        return None
    return curve.Point(index)


def brep_edge_at(obj_ref, index):
    brep = _object_brep(obj_ref)
    if brep is None or index < 0 or index >= brep.Edges.Count:
        return None
    return brep.Edges[index]


def brep_face_at(obj_ref, index):
    brep = _object_brep(obj_ref)
    if brep is None or index < 0 or index >= brep.Faces.Count:
        return None
    return brep.Faces[index]
