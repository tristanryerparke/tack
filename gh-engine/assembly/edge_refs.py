"""Brep edge selection and circular-edge metadata for AssemblyGH mates."""

import Rhino

BREP_EDGE_COMPONENT_TYPE = Rhino.Geometry.ComponentIndexType.BrepEdge
BREP_TRIM_COMPONENT_TYPE = Rhino.Geometry.ComponentIndexType.BrepTrim


class EdgeReferenceError(Exception):
    pass


class EdgePromptCancelled(Exception):
    pass


def _brep_from_rhino_object(rhino_object):
    if rhino_object is None:
        return None
    geometry = rhino_object.Geometry
    if isinstance(geometry, Rhino.Geometry.Brep):
        return geometry
    if hasattr(geometry, "ToBrep"):
        return geometry.ToBrep()
    return None


def _brep_edge_only_filter(rhino_object, geometry, component_index):
    component_type = component_index.ComponentIndexType
    if component_type == BREP_EDGE_COMPONENT_TYPE:
        return True
    if isinstance(geometry, Rhino.Geometry.BrepEdge):
        return True
    if component_type != BREP_TRIM_COMPONENT_TYPE:
        return False

    brep = _brep_from_rhino_object(rhino_object)
    trim_index = component_index.Index
    if brep is None or trim_index < 0 or trim_index >= brep.Trims.Count:
        return False

    trim = brep.Trims[trim_index]
    edge = trim.Edge
    if edge is None:
        return False

    trim_indices = list(edge.TrimIndices())
    return bool(trim_indices) and trim.TrimIndex == trim_indices[0]


def _edge_parameter(edge, pick_point):
    closest = edge.ClosestPoint(pick_point)
    if isinstance(closest, tuple):
        ok, parameter = closest
        return parameter if ok else None
    return closest if closest else None


def _try_get_circle_or_arc(edge, tolerance=None):
    curve = edge.DuplicateCurve()
    if curve is None:
        return None

    circle_result = curve.TryGetCircle() if tolerance is None else curve.TryGetCircle(tolerance)
    if isinstance(circle_result, tuple):
        if circle_result[0]:
            circle = circle_result[1]
            return {
                "kind": "circle",
                "center": circle.Center,
                "radius": circle.Radius,
                "normal": circle.Plane.Normal,
                "x_axis": circle.Plane.XAxis,
                "y_axis": circle.Plane.YAxis,
            }
    elif circle_result:
        # Python.NET normally returns a tuple for out parameters. Keep this for
        # forward compatibility, but do not pretend we have center/radius data.
        return None

    arc_result = curve.TryGetArc() if tolerance is None else curve.TryGetArc(tolerance)
    if isinstance(arc_result, tuple):
        if arc_result[0]:
            arc = arc_result[1]
            return {
                "kind": "arc",
                "center": arc.Center,
                "radius": arc.Radius,
                "normal": arc.Plane.Normal,
                "x_axis": arc.Plane.XAxis,
                "y_axis": arc.Plane.YAxis,
            }
    return None


def _vec_tuple(vector):
    return (float(vector.X), float(vector.Y), float(vector.Z))


def _point_tuple(point):
    return (float(point.X), float(point.Y), float(point.Z))


def circular_edge_reference_from_obj_ref(obj_ref, *, role):
    edge = obj_ref.Edge()
    brep = obj_ref.Brep()
    rhino_object = obj_ref.Object()
    if edge is None or brep is None or rhino_object is None:
        raise EdgeReferenceError("Selection is not a Brep edge.")

    tolerance = None
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is not None:
        tolerance = doc.ModelAbsoluteTolerance
    circle = _try_get_circle_or_arc(edge, tolerance)
    if circle is None:
        raise EdgeReferenceError("Selected edge is not circular/arc-like.")

    pick_point = obj_ref.SelectionPoint()
    component_index = obj_ref.GeometryComponentIndex
    return {
        "role": role,
        "object_id": str(obj_ref.ObjectId),
        "edge_index": int(edge.EdgeIndex),
        "component_index_type": str(component_index.ComponentIndexType),
        "component_index_index": int(component_index.Index),
        "pick_point": _point_tuple(pick_point),
        "edge_parameter": _edge_parameter(edge, pick_point),
        "edge_length": float(edge.GetLength()),
        "adjacent_face_indices": [int(index) for index in edge.AdjacentFaces()],
        "circle_kind": circle["kind"],
        "center": _point_tuple(circle["center"]),
        "radius": float(circle["radius"]),
        "normal": _vec_tuple(circle["normal"]),
        "x_axis": _vec_tuple(circle["x_axis"]),
        "y_axis": _vec_tuple(circle["y_axis"]),
    }


def _same_inferred_circle(first, second, tolerance):
    first_center = Rhino.Geometry.Point3d(*first["center"])
    second_center = Rhino.Geometry.Point3d(*second["center"])
    if first_center.DistanceTo(second_center) > tolerance:
        return False
    if abs(first["radius"] - second["radius"]) > tolerance:
        return False

    first_normal = Rhino.Geometry.Vector3d(*first["normal"])
    second_normal = Rhino.Geometry.Vector3d(*second["normal"])
    if not first_normal.Unitize() or not second_normal.Unitize():
        return False
    return abs(first_normal * second_normal) > 0.999


def _combined_circular_edge_reference(references, *, role):
    if not references:
        raise EdgeReferenceError("Select at least one circular/arc Brep edge.")

    tolerance = 1e-6
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is not None:
        tolerance = max(float(doc.ModelAbsoluteTolerance), tolerance)

    first = references[0]
    for reference in references[1:]:
        if reference["object_id"] != first["object_id"]:
            raise EdgeReferenceError("Selected edge segments for one mate reference must belong to the same Brep.")
        if not _same_inferred_circle(first, reference, tolerance):
            raise EdgeReferenceError("Selected edge segments do not infer the same circle.")

    combined = dict(first)
    combined["role"] = role
    combined["edge_indices"] = [int(reference["edge_index"]) for reference in references]
    combined["edge_index"] = combined["edge_indices"][0]
    combined["edge_lengths"] = [float(reference["edge_length"]) for reference in references]
    combined["edge_length"] = sum(combined["edge_lengths"])
    combined["circle_kind"] = "inferred_circle_from_edges" if len(references) > 1 else first["circle_kind"]
    return combined


def prompt_for_circular_brep_edge(prompt, *, role):
    getter = Rhino.Input.Custom.GetObject()
    getter.SetCommandPrompt(prompt)
    getter.SetPressEnterWhenDonePrompt("Press Enter when done")
    getter.GeometryFilter = Rhino.DocObjects.ObjectType.EdgeFilter
    getter.SetCustomGeometryFilter(_brep_edge_only_filter)
    getter.SubObjectSelect = True
    getter.ChooseOneQuestion = False
    getter.AlreadySelectedObjectSelect = True
    getter.EnablePreSelect(True, True)
    getter.EnablePostSelect(True)

    result = getter.GetMultiple(1, 0)
    if result != Rhino.Input.GetResult.Object:
        raise EdgePromptCancelled(prompt)

    references = []
    seen = set()
    for index in range(getter.ObjectCount):
        obj_ref = getter.Object(index)
        edge = obj_ref.Edge()
        if edge is None:
            continue
        key = (str(obj_ref.ObjectId), int(edge.EdgeIndex))
        if key in seen:
            continue
        seen.add(key)
        references.append(circular_edge_reference_from_obj_ref(obj_ref, role=role))

    return _combined_circular_edge_reference(references, role=role)


def require_same_object(first, second, message):
    if first.get("object_id") != second.get("object_id"):
        raise EdgeReferenceError(message)


def require_different_object(first, second, message):
    if first.get("object_id") == second.get("object_id"):
        raise EdgeReferenceError(message)
