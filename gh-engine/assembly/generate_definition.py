"""Generate an AssemblyGH Grasshopper definition from mate records.

This file is the rebuild boundary: individual mate commands update records, then
call ``rebuild_session_definition``. The GH document is an output artifact, not
the source of truth.
"""

import json

import Rhino
import System

from assembly.component_io import (
    add_group,
    add_panel,
    clear_ghdoc,
    emit_guid,
    emit_named,
    safe_set_persistent_data,
    set_pivot,
    wire,
)
from assembly.content_cache import add_content_cache_push_input
from assembly.mate_records import eccentric_joint_record
from assembly.session import save_session_definition


class AssemblyGenerationError(Exception):
    pass


def _load_generation_api():
    import clr

    clr.AddReference("Grasshopper")
    from Grasshopper import Instances
    from Grasshopper.Kernel.Parameters import Param_Geometry, Param_Point
    from Grasshopper.Kernel.Special import GH_ButtonObject, GH_Group, GH_NumberSlider, GH_Panel
    from Grasshopper.Kernel.Types import GH_Boolean, GH_Brep, GH_Curve, GH_Integer, GH_Mesh, GH_Number, GH_Point
    from Grasshopper.Rhinoceros.Model import ModelObject
    from Grasshopper.Rhinoceros.Model.Params import Param_ModelObject

    return {
        "Instances": Instances,
        "GH_Group": GH_Group,
        "GH_Panel": GH_Panel,
        "GH_ButtonObject": GH_ButtonObject,
        "GH_NumberSlider": GH_NumberSlider,
        "Param_Point": Param_Point,
        "Param_Geometry": Param_Geometry,
        "Param_ModelObject": Param_ModelObject,
        "GH_Point": GH_Point,
        "GH_Brep": GH_Brep,
        "GH_Curve": GH_Curve,
        "GH_Mesh": GH_Mesh,
        "GH_Number": GH_Number,
        "GH_Integer": GH_Integer,
        "GH_Boolean": GH_Boolean,
        "ModelObject": ModelObject,
    }


def _point3d(values):
    return Rhino.Geometry.Point3d(float(values[0]), float(values[1]), float(values[2]))


def _point_tuple(point):
    return (float(point.X), float(point.Y), float(point.Z))


def _project_point_to_plane(point, plane_origin, plane_normal):
    vector = point - plane_origin
    distance = vector * plane_normal
    return point - plane_normal * distance


def _project_line_to_plane(start_values, end_values, plane_origin, plane_normal):
    return (
        _project_point_to_plane(_point3d(start_values), plane_origin, plane_normal),
        _project_point_to_plane(_point3d(end_values), plane_origin, plane_normal),
    )


def _extended_axis_points(start_point, end_point, reference_length):
    """Return a very long finite line to approximate an infinite slider axis."""
    direction = end_point - start_point
    if not direction.Unitize():
        raise AssemblyGenerationError("Piston slider axis is degenerate.")
    midpoint = Rhino.Geometry.Point3d(
        (start_point.X + end_point.X) * 0.5,
        (start_point.Y + end_point.Y) * 0.5,
        (start_point.Z + end_point.Z) * 0.5,
    )
    half_length = max(float(reference_length) * 100.0, start_point.DistanceTo(end_point) * 100.0, 1000.0)
    return midpoint - direction * half_length, midpoint + direction * half_length


def _brep_from_rhino_object(rhino_object):
    if rhino_object is None:
        return None
    geometry = rhino_object.Geometry
    if isinstance(geometry, Rhino.Geometry.Brep):
        return geometry
    if isinstance(geometry, Rhino.Geometry.Extrusion):
        return geometry.ToBrep()
    if hasattr(geometry, "ToBrep"):
        return geometry.ToBrep()
    return None


def _try_edge_circle(edge):
    curve = edge.DuplicateCurve()
    if curve is None:
        return None
    tolerance = 1e-6
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is not None:
        tolerance = max(float(doc.ModelAbsoluteTolerance), tolerance)
    for getter_name in ("TryGetCircle", "TryGetArc"):
        getter = getattr(curve, getter_name, None)
        if getter is None:
            continue
        result = getter(tolerance)
        if isinstance(result, tuple) and result[0]:
            circle_like = result[1]
            return circle_like.Center, circle_like.Radius, circle_like.Plane.Normal
    return None


def _resolve_edge_circle_reference(edge_reference):
    doc = _active_rhino_doc()
    if doc is None:
        raise AssemblyGenerationError("No active Rhino document for edge resolution.")
    rhino_object = doc.Objects.Find(System.Guid(str(edge_reference["object_id"])))
    brep = _brep_from_rhino_object(rhino_object)
    if brep is None:
        raise AssemblyGenerationError("Could not resolve Brep object {}".format(edge_reference["object_id"]))

    indices = edge_reference.get("edge_indices") or [edge_reference.get("edge_index")]
    centers = []
    radii = []
    normals = []
    for index in indices:
        edge_index = int(index)
        if edge_index < 0 or edge_index >= brep.Edges.Count:
            raise AssemblyGenerationError("Brep edge index {} out of range on {}".format(edge_index, edge_reference["object_id"]))
        circle = _try_edge_circle(brep.Edges[edge_index])
        if circle is None:
            raise AssemblyGenerationError("Brep edge {} on {} no longer infers a circle.".format(edge_index, edge_reference["object_id"]))
        center, radius, normal = circle
        centers.append(center)
        radii.append(float(radius))
        normals.append(normal)

    center = Rhino.Geometry.Point3d(
        sum(point.X for point in centers) / len(centers),
        sum(point.Y for point in centers) / len(centers),
        sum(point.Z for point in centers) / len(centers),
    )
    normal = Rhino.Geometry.Vector3d(
        sum(vector.X for vector in normals) / len(normals),
        sum(vector.Y for vector in normals) / len(normals),
        sum(vector.Z for vector in normals) / len(normals),
    )
    normal.Unitize()
    return center, sum(radii) / len(radii), normal


def _edge_center(edge_reference):
    return _resolve_edge_circle_reference(edge_reference)[0]


def _mechanism_plane_from_record(refs):
    shaft_start = _point3d(refs["shaft_axis"]["start"])
    shaft_end = _point3d(refs["shaft_axis"]["end"])
    normal = shaft_end - shaft_start
    if not normal.Unitize():
        raise AssemblyGenerationError("Shaft axis is degenerate.")
    # The mechanism plane is defined only by the fixed shaft axis. Circular edge
    # centers are resolved live in GH from metadata and should not be baked into
    # the definition as point inputs.
    return shaft_start, normal


def _add_point_param(api, ghdoc, nick, values, x, y, group_title=None):
    param = api["Param_Point"]()
    param.NickName = nick
    param.Description = nick
    set_pivot(param, x, y)
    safe_set_persistent_data(param, api["GH_Point"](_point3d(values)), nick)
    ghdoc.AddObject(param, False)
    if group_title:
        add_group(api, ghdoc, group_title, [param])
    return param


def _add_model_object_param(api, ghdoc, nick, object_id, x, y, group_title=None):
    param = api["Param_ModelObject"]()
    param.NickName = nick
    param.Description = "Referenced Rhino object {}".format(object_id)
    set_pivot(param, x, y)
    safe_set_persistent_data(param, api["ModelObject"](System.Guid(str(object_id))), nick)
    ghdoc.AddObject(param, False)
    if group_title:
        add_group(api, ghdoc, group_title, [param])
    return param


def _geometry_goo(api, geometry):
    if geometry is None:
        return None
    if isinstance(geometry, Rhino.Geometry.Extrusion):
        geometry = geometry.ToBrep()
    elif isinstance(geometry, Rhino.Geometry.Brep):
        geometry = geometry.DuplicateBrep()
    elif isinstance(geometry, Rhino.Geometry.Curve):
        geometry = geometry.DuplicateCurve()
    elif isinstance(geometry, Rhino.Geometry.Mesh):
        geometry = geometry.DuplicateMesh()
    elif hasattr(geometry, "Duplicate"):
        geometry = geometry.Duplicate()

    if isinstance(geometry, Rhino.Geometry.Brep):
        return api["GH_Brep"](geometry)
    if isinstance(geometry, Rhino.Geometry.Curve):
        return api["GH_Curve"](geometry)
    if isinstance(geometry, Rhino.Geometry.Mesh):
        return api["GH_Mesh"](geometry)
    return None


def _active_rhino_doc():
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is not None:
        return doc
    try:
        import scriptcontext as sc

        return sc.doc
    except Exception:
        return None


def _add_static_geometry_param(api, ghdoc, nick, object_id, x, y, group_title=None):
    """Snapshot object geometry so Content Cache writeback cannot accumulate.

    Reading geometry from the live Model Object after Content Cache writes causes
    feedback: each solve transforms the already-transformed object again. This
    param stores the base geometry once in the generated GH definition.
    """
    doc = _active_rhino_doc()
    rhino_object = doc.Objects.Find(System.Guid(str(object_id))) if doc is not None else None
    goo = _geometry_goo(api, rhino_object.Geometry if rhino_object is not None else None)
    if goo is None:
        raise AssemblyGenerationError("Could not snapshot geometry for object {}".format(object_id))

    param = api["Param_Geometry"]()
    param.NickName = nick
    param.Description = "Static base geometry snapshot for {}".format(object_id)
    set_pivot(param, x, y)
    safe_set_persistent_data(param, goo, nick)
    ghdoc.AddObject(param, False)
    if group_title:
        add_group(api, ghdoc, group_title, [param])
    return param


def _add_number_slider(api, ghdoc, nick, value, x, y, *, minimum=0.0, maximum=6.283185307179586):
    # Instantiate through the component server. Direct GH_NumberSlider()
    # construction can leave internal slider state unset on Rhino 8 Mac.
    slider = emit_guid(api, ghdoc, "57da07bd-ecab-415d-9d86-af36d7073abc", x, y)
    slider.NickName = nick
    try:
        slider.Slider.Minimum = System.Decimal(float(minimum))
        slider.Slider.Maximum = System.Decimal(float(maximum))
        slider.Slider.DecimalPlaces = 3
        slider.SetSliderValue(System.Decimal(float(value)))
    except Exception:
        # Fallback leaves a default slider, but keeps the graph buildable.
        pass
    return slider


def _add_button(api, ghdoc, nick, x, y):
    button = api["GH_ButtonObject"]()
    button.NickName = nick
    set_pivot(button, x, y)
    ghdoc.AddObject(button, False)
    return button


def _set_input_number(api, component, input_index, value):
    safe_set_persistent_data(
        component.Params.Input[input_index],
        api["GH_Number"](float(value)),
        "{} input {}".format(component.NickName, input_index),
    )


def _set_input_integer(api, component, input_index, value):
    safe_set_persistent_data(
        component.Params.Input[input_index],
        api["GH_Integer"](int(value)),
        "{} input {}".format(component.NickName, input_index),
    )


def _set_input_boolean(api, component, input_index, value):
    safe_set_persistent_data(
        component.Params.Input[input_index],
        api["GH_Boolean"](bool(value)),
        "{} input {}".format(component.NickName, input_index),
    )


def _make_list_item(api, ghdoc, source, source_index, item_index, x, y, nick):
    item = emit_named(api, ghdoc, "List Item", x, y)
    item.NickName = nick
    _set_input_integer(api, item, 1, item_index)
    wire(source, source_index, item, 0)
    return item


def _add_value_panel(api, ghdoc, title, source, source_index, x, y):
    panel = add_panel(api, ghdoc, title, x, y)
    try:
        wire(source, source_index, panel, 0)
    except Exception:
        pass
    return panel


def _edge_index(edge_reference):
    indices = edge_reference.get("edge_indices") or [edge_reference.get("edge_index")]
    return int(indices[0])


def _emit_model_object_reader(api, ghdoc, model_object_param, x, y, nick):
    reader = emit_guid(api, ghdoc, "d7071c97-bc7f-4966-beba-b7110064eebf", x, y)
    reader.NickName = nick
    wire(model_object_param, 0, reader, 0)
    return reader


def _emit_live_edge_center(api, ghdoc, geometry_source, edge_reference, x, y, nick):
    """Emit native GH components to resolve a circular Brep edge center live.

    object geometry -> Deconstruct Brep -> List Item(edge index) -> Divide Curve
    -> Circle Fit -> Area centroid.
    """
    debrep = emit_named(api, ghdoc, "Deconstruct Brep", x, y)
    debrep.NickName = nick + " deBrep"
    item = emit_named(api, ghdoc, "List Item", x + 220, y)
    item.NickName = nick + " edge"
    divide = emit_named(api, ghdoc, "Divide Curve", x + 440, y)
    divide.NickName = nick + " divide"
    circle_fit = emit_named(api, ghdoc, "Circle Fit", x + 660, y)
    circle_fit.NickName = nick + " circle fit"
    area = emit_named(api, ghdoc, "Area", x + 880, y)
    area.NickName = nick + " center"

    _set_input_integer(api, item, 1, _edge_index(edge_reference))
    _set_input_integer(api, divide, 1, 8)
    _set_input_boolean(api, divide, 2, False)

    wire(geometry_source, 1, debrep, 0)
    wire(debrep, 1, item, 0)
    wire(item, 0, divide, 0)
    wire(divide, 0, circle_fit, 0)
    wire(circle_fit, 0, area, 0)
    return area, [debrep, item, divide, circle_fit, area]


def mate_to_kangaroo_plan(record):
    mate_type = record["type"]
    if mate_type == "eccentric_joint":
        return [
            "driver: angle slider rotates eccentric object/pin about shaft axis",
            "plane: mechanism points are projected to the plane normal to the shaft axis",
            "constraint: piston pin stays on selected slider axis",
            "constraint: Length(Line) keeps rod length fixed",
            "solver: Kangaroo main Solver outputs solved piston pin",
            "writeback: Content Cache replaces eccentric object and piston",
            "optional writeback: orient connecting rod between solved endpoints in the same plane",
        ]
    if mate_type == "hinge":
        return [
            "constraint: selected axis remains coincident/concentric",
            "free DOF: rotation about hinge axis",
            "writeback: Content Cache replaces rotating component",
        ]
    if mate_type == "slider":
        return [
            "constraint: selected point/body stays on slider axis",
            "free DOF: translation along axis",
            "writeback: Content Cache replaces sliding component",
        ]
    return [
        "standard mate placeholder: map selected references to Kangaroo goals",
        "writeback only if this mate controls a moving object",
    ]


def _feature_from_joint_ref(joint, ref_key):
    reference = joint.get("references", {}).get(ref_key)
    if reference is None:
        return None
    return joint.get("references", {}).get("features", {}).get(reference.get("feature_id"))


def _edge_reference_from_feature(feature, role=None):
    fingerprint = feature.get("fingerprint", {})
    reference = {
        "role": role or feature.get("role"),
        "object_id": str(feature["object_id"]),
        "edge_indices": [int(index) for index in feature.get("edge_indices", [])],
    }
    if reference["edge_indices"]:
        reference["edge_index"] = reference["edge_indices"][0]
    for key in ("center", "radius", "normal", "circle_kind", "adjacent_face_indices"):
        if key in fingerprint:
            reference[key] = fingerprint[key]
    return reference


def _feature_object_id(feature):
    return str(feature.get("object_id")) if feature else None


def _feature_pair_for_body_joint(joint):
    feature_a = _feature_from_joint_ref(joint, "a")
    feature_b = _feature_from_joint_ref(joint, "b")
    if feature_a is None or feature_b is None:
        return None
    return feature_a, feature_b


def _joint_mode(joint):
    return joint.get("parameters", {}).get("mode")


def _synthesize_crank_slider_mate_from_joints(joints):
    """Detect the current 4-joint crank-slider and reuse the proven emitter.

    The saved source of truth stays Fusion-style joints. This function is only a
    generation adapter while the fully generic 6DOF joint solver is being built.
    """
    fixed_revolutes = [
        joint for joint in joints
        if joint.get("type") == "revolute" and _joint_mode(joint) == "body_to_world_axis"
    ]
    sliders = [
        joint for joint in joints
        if joint.get("type") == "slider" and _joint_mode(joint) == "body_to_world_axis"
    ]
    body_revolutes = [
        joint for joint in joints
        if joint.get("type") == "revolute" and _joint_mode(joint) == "body_to_body"
    ]
    if len(fixed_revolutes) != 1 or len(sliders) != 1 or len(body_revolutes) != 2:
        return None

    shaft_joint = fixed_revolutes[0]
    slider_joint = sliders[0]
    shaft_feature = _feature_from_joint_ref(shaft_joint, "body")
    piston_slider_feature = _feature_from_joint_ref(slider_joint, "body")
    shaft_axis = shaft_joint.get("references", {}).get("axis")
    piston_axis = slider_joint.get("references", {}).get("axis")
    if shaft_feature is None or piston_slider_feature is None or shaft_axis is None or piston_axis is None:
        return None

    eccentric_object_id = _feature_object_id(shaft_feature)
    piston_object_id = _feature_object_id(piston_slider_feature)

    eccentric_pin_feature = None
    rod_big_feature = None
    rod_small_feature = None
    piston_pin_feature = None
    rod_object_id = None

    for joint in body_revolutes:
        pair = _feature_pair_for_body_joint(joint)
        if pair is None:
            return None
        feature_a, feature_b = pair
        object_a = _feature_object_id(feature_a)
        object_b = _feature_object_id(feature_b)
        if object_a == eccentric_object_id and object_b != piston_object_id:
            eccentric_pin_feature = feature_a
            rod_big_feature = feature_b
            rod_object_id = object_b
        elif object_b == eccentric_object_id and object_a != piston_object_id:
            eccentric_pin_feature = feature_b
            rod_big_feature = feature_a
            rod_object_id = object_a

    if rod_object_id is None:
        return None

    for joint in body_revolutes:
        pair = _feature_pair_for_body_joint(joint)
        if pair is None:
            return None
        feature_a, feature_b = pair
        object_a = _feature_object_id(feature_a)
        object_b = _feature_object_id(feature_b)
        if object_a == rod_object_id and object_b == piston_object_id:
            rod_small_feature = feature_a
            piston_pin_feature = feature_b
        elif object_b == rod_object_id and object_a == piston_object_id:
            rod_small_feature = feature_b
            piston_pin_feature = feature_a

    if not all((eccentric_pin_feature, rod_big_feature, rod_small_feature, piston_pin_feature)):
        return None

    rod_big_edge = _edge_reference_from_feature(rod_big_feature, role="rod_big_edge")
    rod_small_edge = _edge_reference_from_feature(rod_small_feature, role="rod_small_edge")
    try:
        rod_length = _edge_center(rod_big_edge).DistanceTo(_edge_center(rod_small_edge))
    except Exception:
        big_center = rod_big_feature.get("fingerprint", {}).get("center")
        small_center = rod_small_feature.get("fingerprint", {}).get("center")
        if big_center is None or small_center is None:
            raise
        rod_length = _point3d(big_center).DistanceTo(_point3d(small_center))

    record = eccentric_joint_record(
        shaft_axis=shaft_axis,
        piston_axis=piston_axis,
        rod_length=rod_length,
        driver_mode="live_driver",
        rotator_shaft_edge=_edge_reference_from_feature(shaft_feature, role="rotator_shaft_edge"),
        eccentric_pin_edge=_edge_reference_from_feature(eccentric_pin_feature, role="eccentric_pin_edge"),
        rod_big_edge=rod_big_edge,
        rod_small_edge=rod_small_edge,
        piston_pin_edge=_edge_reference_from_feature(piston_pin_feature, role="piston_pin_edge"),
        name="Crank-slider from Fusion-style joints",
    )
    record["source_joint_ids"] = [joint.get("id") for joint in [shaft_joint] + body_revolutes + [slider_joint]]
    return record


def _joint_summary_text(joint):
    return "Joint: {}\nType: {}\nID: {}\n\nRecord:\n{}".format(
        joint.get("name"),
        joint.get("type"),
        joint.get("id"),
        json.dumps(joint, indent=2, sort_keys=True),
    )


def _mate_summary_text(record):
    plan = mate_to_kangaroo_plan(record)
    return "\n".join(
        [
            "Mate: {}".format(record["name"]),
            "Type: {}".format(record["type"]),
            "ID: {}".format(record["id"]),
            "",
            "Kangaroo/GH plan:",
        ]
        + ["- {}".format(item) for item in plan]
        + [
            "",
            "Record:",
            json.dumps(record, indent=2, sort_keys=True),
        ]
    )


def _emit_eccentric_joint(api, ghdoc, record, origin_x, origin_y):
    refs = record["references"]
    params = record["parameters"]
    strengths = params.get("strengths", {})
    driver_mode = params.get("driver_mode", "live_driver")

    shaft_axis = refs["shaft_axis"]
    piston_axis = refs["piston_axis"]
    plane_origin, plane_normal = _mechanism_plane_from_record(refs)
    edge_based = "rotator_shaft_edge" in refs
    # Live metadata mode: the GH definition resolves mate points from
    # object_id + edge_index metadata at solve time. Edge-based mates do not get
    # point params for circular-edge centers.
    transactional = False
    eccentric_pin_values = None if edge_based else refs["eccentric_pin_start"]["point"]
    piston_pin_values = None if edge_based else refs["piston_pin_start"]["point"]
    eccentric_pin_point = None if edge_based else _project_point_to_plane(
        _point3d(eccentric_pin_values),
        plane_origin,
        plane_normal,
    )
    # Use the exact user-picked slider axis. Earlier POC code projected this
    # axis into the mechanism plane, which made the visible slider line drift
    # away from the axis the user actually specified.
    piston_axis_start_point, piston_axis_end_point = _extended_axis_points(
        _point3d(piston_axis["start"]),
        _point3d(piston_axis["end"]),
        params["rod_length"],
    )
    piston_pin_point = None if edge_based else _project_point_to_plane(
        _point3d(piston_pin_values),
        plane_origin,
        plane_normal,
    )
    eccentric_pin = None if edge_based else _point_tuple(eccentric_pin_point)
    piston_pin = None if edge_based else _point_tuple(piston_pin_point)
    actual_piston_pin = None if edge_based else _point_tuple(_point3d(piston_pin_values))
    piston_object_id = refs["piston_object"]["object_id"]
    eccentric_object = refs.get("eccentric_object")
    rod_object = refs.get("rod_object")

    sx = origin_x
    sy = origin_y

    rod_big = None if edge_based else eccentric_pin
    rod_small = None if edge_based else piston_pin

    # Fixed-axis references. In edge-based mode these are the only point params
    # allowed into the solver setup.
    shaft_start = _add_point_param(api, ghdoc, "shaft axis start", shaft_axis["start"], sx, sy + 20)
    shaft_end = _add_point_param(api, ghdoc, "shaft axis end", shaft_axis["end"], sx, sy + 95)
    eccentric_start = None if edge_based else _add_point_param(api, ghdoc, "eccentric pin center", eccentric_pin, sx, sy + 190)
    rod_big_start = None if edge_based else _add_point_param(api, ghdoc, "rod eccentric-end center", rod_big, sx, sy + 270)
    rod_small_start = None if edge_based else _add_point_param(api, ghdoc, "rod piston-end center", rod_small, sx, sy + 350)
    piston_axis_start = _add_point_param(api, ghdoc, "piston axis start exact/extended", _point_tuple(piston_axis_start_point), sx, sy + 455)
    piston_axis_end = _add_point_param(api, ghdoc, "piston axis end exact/extended", _point_tuple(piston_axis_end_point), sx, sy + 530)
    piston_pin_start = None if edge_based else _add_point_param(api, ghdoc, "piston wrist-pin center projected", piston_pin, sx, sy + 640)
    piston_pin_actual = None if edge_based else _add_point_param(api, ghdoc, "piston wrist-pin actual edge center", actual_piston_pin, sx, sy + 710)
    piston_obj = _add_model_object_param(api, ghdoc, "piston object", piston_object_id, sx, sy + 790)
    base_piston_geometry = None
    if transactional:
        piston_reader = None
        base_piston_geometry = _add_static_geometry_param(api, ghdoc, "sampled piston geometry", piston_object_id, sx + 240, sy + 790)
    else:
        piston_reader = _emit_model_object_reader(api, ghdoc, piston_obj, sx + 240, sy + 790, "live piston geometry")
    live_piston_center = None
    live_piston_center_components = []
    if edge_based and not transactional:
        live_piston_center, live_piston_center_components = _emit_live_edge_center(
            api,
            ghdoc,
            piston_reader,
            refs["piston_pin_edge"],
            sx + 480,
            sy + 720,
            "live piston pin",
        )

    eccentric_obj = None
    eccentric_reader = None
    live_eccentric_center = None
    live_eccentric_center_components = []
    if eccentric_object is not None:
        eccentric_obj = _add_model_object_param(api, ghdoc, "eccentric object", eccentric_object["object_id"], sx, sy + 950)
        if transactional:
            eccentric_reader = None
        else:
            eccentric_reader = _emit_model_object_reader(api, ghdoc, eccentric_obj, sx + 240, sy + 950, "live eccentric geometry")
        if edge_based and not transactional:
            live_eccentric_center, live_eccentric_center_components = _emit_live_edge_center(
                api,
                ghdoc,
                eccentric_reader,
                refs["eccentric_pin_edge"],
                sx + 480,
                sy + 950,
                "live eccentric pin",
            )

    rod_obj = None
    rod_reader = None
    base_rod_geometry = None
    live_rod_big_center = None
    live_rod_small_center = None
    live_rod_center_components = []
    if rod_object is not None:
        rod_obj = _add_model_object_param(api, ghdoc, "rod object", rod_object["object_id"], sx, sy + 1135)
        if transactional:
            rod_reader = None
            base_rod_geometry = _add_static_geometry_param(api, ghdoc, "sampled rod geometry", rod_object["object_id"], sx + 240, sy + 1135)
        else:
            rod_reader = _emit_model_object_reader(api, ghdoc, rod_obj, sx + 240, sy + 1135, "live rod geometry")
        if edge_based and not transactional:
            live_rod_big_center, big_components = _emit_live_edge_center(
                api,
                ghdoc,
                rod_reader,
                refs["rod_big_edge"],
                sx + 480,
                sy + 1115,
                "live rod eccentric end",
            )
            live_rod_small_center, small_components = _emit_live_edge_center(
                api,
                ghdoc,
                rod_reader,
                refs["rod_small_edge"],
                sx + 480,
                sy + 1255,
                "live rod piston end",
            )
            live_rod_center_components = big_components + small_components

    if edge_based and (
        live_eccentric_center is None
        or live_piston_center is None
        or live_rod_big_center is None
        or live_rod_small_center is None
    ):
        raise AssemblyGenerationError(
            "Edge-based eccentric joints require live Brep edge-center extraction for eccentric, piston, and rod features."
        )

    driver_components = []
    angle_slider = None
    angle_radians = None
    if driver_mode == "slider":
        angle_slider = _add_number_slider(
            api,
            ghdoc,
            "shaft angle degrees",
            params.get("angle_driver", {}).get("initial_degrees", 0.0),
            sx + 240,
            sy + 20,
            minimum=0.0,
            maximum=720.0,
        )
        angle_radians = emit_named(api, ghdoc, "Radians", sx + 480, sy + 20)
        angle_radians.NickName = "degrees to radians"
        wire(angle_slider, 0, angle_radians, 0)
        driver_components.extend([angle_slider, angle_radians])
    reset_button = _add_button(api, ghdoc, "Reset", sx + 700, sy + 20)

    # Driven geometry and Kangaroo goals.
    shaft_line = emit_named(api, ghdoc, "Line", sx + 240, sy + 95)
    shaft_line.NickName = "shaft axis line"
    shaft_vector = emit_named(api, ghdoc, "Vector 2Pt", sx + 240, sy + 170)
    shaft_vector.NickName = "shaft axis vector / plane normal"
    piston_axis_line = emit_named(api, ghdoc, "Line", sx + 240, sy + 365)
    piston_axis_line.NickName = "piston slider line"
    rotate_ecc = None
    if driver_mode == "slider":
        rotate_ecc = emit_named(api, ghdoc, "Rotate Axis", sx + 480, sy + 120)
        rotate_ecc.NickName = "rotate eccentric pin"
        driver_components.append(rotate_ecc)
    rod_line = emit_named(api, ghdoc, "Line", sx + 480, sy + 285)
    rod_line.NickName = "rod constraint line"
    live_rod_length = None
    if live_rod_big_center is not None and live_rod_small_center is not None:
        live_rod_length = emit_named(api, ghdoc, "Vector 2Pt", sx + 480, sy + 215)
        live_rod_length.NickName = "live rod length from edge centers"
        wire(live_rod_big_center, 1, live_rod_length, 0)
        wire(live_rod_small_center, 1, live_rod_length, 1)
    length_goal = emit_named(api, ghdoc, "Length(Line)", sx + 720, sy + 285)
    length_goal.NickName = "fixed rod length"
    eccentric_anchor = emit_named(api, ghdoc, "Anchor", sx + 720, sy + 120)
    eccentric_anchor.NickName = "eccentric pin follows rotation"
    piston_on_curve = emit_named(api, ghdoc, "OnCurve", sx + 720, sy + 430)
    piston_on_curve.NickName = "piston pin stays on axis"
    solver = emit_guid(api, ghdoc, "8f9f19c0-207a-419d-90f6-2fcadaa845f9", sx + 980, sy + 285)
    solver.NickName = "Kangaroo solver"

    wire(shaft_start, 0, shaft_line, 0)
    wire(shaft_end, 0, shaft_line, 1)
    wire(shaft_start, 0, shaft_vector, 0)
    wire(shaft_end, 0, shaft_vector, 1)
    wire(piston_axis_start, 0, piston_axis_line, 0)
    wire(piston_axis_end, 0, piston_axis_line, 1)

    # Use transaction-sampled metadata points by default. Pure GH-live solver
    # inputs are possible, but they feed back when Content Cache writes the same
    # objects in the same solution.
    if live_eccentric_center is not None:
        eccentric_particle_source = live_eccentric_center
        eccentric_particle_output = 1
    else:
        eccentric_particle_source = eccentric_start
        eccentric_particle_output = 0

    wire(eccentric_particle_source, eccentric_particle_output, rod_line, 0)
    wire(eccentric_particle_source, eccentric_particle_output, eccentric_anchor, 0)
    if driver_mode == "slider" and rotate_ecc is not None:
        wire(eccentric_particle_source, eccentric_particle_output, rotate_ecc, 0)
        wire(angle_radians, 0, rotate_ecc, 1)
        wire(shaft_line, 0, rotate_ecc, 2)
        wire(rotate_ecc, 0, eccentric_anchor, 1)
    else:
        # Live-driver mode: the eccentric object leads the solve. Its current
        # edge center is the hard anchor target, and AssemblyGH does not write
        # the eccentric object back.
        wire(eccentric_particle_source, eccentric_particle_output, eccentric_anchor, 1)

    if live_piston_center is not None:
        wire(live_piston_center, 1, rod_line, 1)
        wire(live_piston_center, 1, piston_on_curve, 0)
    else:
        wire(piston_pin_start, 0, rod_line, 1)
        wire(piston_pin_start, 0, piston_on_curve, 0)
    wire(rod_line, 0, length_goal, 0)
    wire(piston_axis_line, 0, piston_on_curve, 1)
    wire(length_goal, 0, solver, 0)
    wire(eccentric_anchor, 0, solver, 0)
    wire(piston_on_curve, 0, solver, 0)
    wire(reset_button, 0, solver, 1)

    if live_rod_length is not None:
        wire(live_rod_length, 1, length_goal, 1)
    else:
        _set_input_number(api, length_goal, 1, params["rod_length"])
    _set_input_number(api, length_goal, 2, strengths.get("rod_length", 1000.0))
    _set_input_number(api, eccentric_anchor, 2, strengths.get("shaft_anchor", 10000.0))
    _set_input_number(api, piston_on_curve, 2, strengths.get("slider_axis", 10000.0))
    _set_input_number(api, solver, 2, 1e-6)
    _set_input_number(api, solver, 3, 0.001)
    _set_input_boolean(api, solver, 4, True)

    solved_ecc = _make_list_item(api, ghdoc, solver, 1, 0, sx + 1220, sy + 160, "solved eccentric pin")
    solved_piston = _make_list_item(api, ghdoc, solver, 1, 1, sx + 1220, sy + 420, "solved piston pin")
    solved_line = emit_named(api, ghdoc, "Line", sx + 1460, sy + 285)
    solved_line.NickName = "solved rod preview"
    wire(solved_ecc, 0, solved_line, 0)
    wire(solved_piston, 0, solved_line, 1)

    debug_panels = []
    if live_eccentric_center is not None:
        debug_panels.append(_add_value_panel(api, ghdoc, "DEBUG live eccentric pin center", live_eccentric_center, 1, sx + 1220, sy + 520))
    if live_piston_center is not None:
        debug_panels.append(_add_value_panel(api, ghdoc, "DEBUG live piston pin center", live_piston_center, 1, sx + 1220, sy + 620))
    if live_rod_big_center is not None:
        debug_panels.append(_add_value_panel(api, ghdoc, "DEBUG live rod eccentric-end center", live_rod_big_center, 1, sx + 1220, sy + 720))
    if live_rod_small_center is not None:
        debug_panels.append(_add_value_panel(api, ghdoc, "DEBUG live rod piston-end center", live_rod_small_center, 1, sx + 1220, sy + 820))
    debug_panels.append(_add_value_panel(api, ghdoc, "DEBUG solved eccentric pin", solved_ecc, 0, sx + 1460, sy + 520))
    debug_panels.append(_add_value_panel(api, ghdoc, "DEBUG solved piston pin", solved_piston, 0, sx + 1460, sy + 620))

    writeback_sources = []

    eccentric_components = []
    if eccentric_obj is not None and driver_mode == "slider":
        current_ecc_dir = emit_named(api, ghdoc, "Vector 2Pt", sx + 1220, sy + 20)
        current_ecc_dir.NickName = "current eccentric radius direction"
        target_ecc_dir = emit_named(api, ghdoc, "Vector 2Pt", sx + 1220, sy + 110)
        target_ecc_dir.NickName = "target eccentric radius direction"
        current_ecc_plane = emit_named(api, ghdoc, "Construct Plane", sx + 1460, sy + 20)
        current_ecc_plane.NickName = "current eccentric plane"
        target_ecc_plane = emit_named(api, ghdoc, "Construct Plane", sx + 1460, sy + 110)
        target_ecc_plane.NickName = "target eccentric plane"
        oriented_eccentric = emit_named(api, ghdoc, "Orient", sx + 1700, sy + 65)
        oriented_eccentric.NickName = "oriented eccentric geometry"
        replacement_eccentric = emit_guid(api, ghdoc, "d7071c97-bc7f-4966-beba-b7110064eebf", sx + 1940, sy + 65)
        replacement_eccentric.NickName = "replacement eccentric object"

        if live_eccentric_center is not None:
            wire(shaft_start, 0, current_ecc_dir, 0)
            wire(live_eccentric_center, 1, current_ecc_dir, 1)
            wire(shaft_start, 0, current_ecc_plane, 0)
            wire(current_ecc_dir, 0, current_ecc_plane, 1)
            wire(shaft_vector, 0, current_ecc_plane, 2)
            wire(shaft_start, 0, target_ecc_dir, 0)
            wire(solved_ecc, 0, target_ecc_dir, 1)
            wire(shaft_start, 0, target_ecc_plane, 0)
            wire(target_ecc_dir, 0, target_ecc_plane, 1)
            wire(shaft_vector, 0, target_ecc_plane, 2)
            wire(eccentric_reader, 1, oriented_eccentric, 0)
            wire(current_ecc_plane, 0, oriented_eccentric, 1)
            wire(target_ecc_plane, 0, oriented_eccentric, 2)
            wire(eccentric_obj, 0, replacement_eccentric, 0)
            wire(oriented_eccentric, 0, replacement_eccentric, 1)
            writeback_sources.append(replacement_eccentric)
        eccentric_components = [
            eccentric_obj,
            eccentric_reader,
            live_eccentric_center,
            current_ecc_dir,
            target_ecc_dir,
            current_ecc_plane,
            target_ecc_plane,
            oriented_eccentric,
            replacement_eccentric,
        ] + live_eccentric_center_components

    # Piston writeback: live geometry + live edge-center correction.
    piston_translation = emit_named(api, ghdoc, "Vector 2Pt", sx + 1460, sy + 540)
    piston_translation.NickName = "piston translation"
    moved_piston = emit_named(api, ghdoc, "Move", sx + 1700, sy + 650)
    moved_piston.NickName = "moved piston geometry"
    replacement_piston = emit_guid(api, ghdoc, "d7071c97-bc7f-4966-beba-b7110064eebf", sx + 1940, sy + 650)
    replacement_piston.NickName = "replacement piston object"

    if live_piston_center is not None:
        wire(live_piston_center, 1, piston_translation, 0)
    else:
        wire(piston_pin_actual, 0, piston_translation, 0)
    wire(solved_piston, 0, piston_translation, 1)
    if piston_reader is not None:
        wire(piston_reader, 1, moved_piston, 0)
    else:
        wire(base_piston_geometry, 0, moved_piston, 0)
    wire(piston_translation, 0, moved_piston, 1)
    wire(piston_obj, 0, replacement_piston, 0)
    wire(moved_piston, 0, replacement_piston, 1)
    writeback_sources.append(replacement_piston)

    rod_components = []
    if rod_obj is not None:
        initial_rod_dir = emit_named(api, ghdoc, "Vector 2Pt", sx + 1460, sy + 800)
        initial_rod_dir.NickName = "initial rod direction"
        solved_rod_dir = emit_named(api, ghdoc, "Vector 2Pt", sx + 1460, sy + 890)
        solved_rod_dir.NickName = "solved rod direction"
        initial_rod_plane = emit_named(api, ghdoc, "Construct Plane", sx + 1700, sy + 785)
        initial_rod_plane.NickName = "initial rod plane"
        solved_rod_plane = emit_named(api, ghdoc, "Construct Plane", sx + 1700, sy + 905)
        solved_rod_plane.NickName = "solved rod plane"
        oriented_rod = emit_named(api, ghdoc, "Orient", sx + 1940, sy + 815)
        oriented_rod.NickName = "oriented rod geometry in mechanism plane"
        replacement_rod = emit_guid(api, ghdoc, "d7071c97-bc7f-4966-beba-b7110064eebf", sx + 2180, sy + 815)
        replacement_rod.NickName = "replacement rod object"

        if live_rod_big_center is not None:
            wire(live_rod_big_center, 1, initial_rod_dir, 0)
        else:
            wire(rod_big_start, 0, initial_rod_dir, 0)
        if live_rod_small_center is not None:
            wire(live_rod_small_center, 1, initial_rod_dir, 1)
        else:
            wire(rod_small_start, 0, initial_rod_dir, 1)
        wire(solved_ecc, 0, solved_rod_dir, 0)
        wire(solved_piston, 0, solved_rod_dir, 1)
        if live_rod_big_center is not None:
            wire(live_rod_big_center, 1, initial_rod_plane, 0)
        else:
            wire(rod_big_start, 0, initial_rod_plane, 0)
        wire(initial_rod_dir, 0, initial_rod_plane, 1)
        wire(shaft_vector, 0, initial_rod_plane, 2)
        wire(solved_ecc, 0, solved_rod_plane, 0)
        wire(solved_rod_dir, 0, solved_rod_plane, 1)
        wire(shaft_vector, 0, solved_rod_plane, 2)
        if rod_reader is not None:
            wire(rod_reader, 1, oriented_rod, 0)
        else:
            wire(base_rod_geometry, 0, oriented_rod, 0)
        wire(initial_rod_plane, 0, oriented_rod, 1)
        wire(solved_rod_plane, 0, oriented_rod, 2)
        wire(rod_obj, 0, replacement_rod, 0)
        wire(oriented_rod, 0, replacement_rod, 1)
        writeback_sources.append(replacement_rod)
        rod_components = [
            rod_obj,
            rod_reader,
            live_rod_big_center,
            live_rod_small_center,
            initial_rod_dir,
            solved_rod_dir,
            initial_rod_plane,
            solved_rod_plane,
            oriented_rod,
            replacement_rod,
        ] + live_rod_center_components

    final_cache_components = []
    if writeback_sources:
        final_cache = emit_guid(api, ghdoc, "1fae4c7a-d84a-4f04-8400-179e13193381", sx + 2760, sy + 650)
        final_cache.NickName = "Content Cache Push assembly writeback"
        add_content_cache_push_input(final_cache)
        for source in writeback_sources:
            wire(source, 0, final_cache, 0)
        final_cache_components = [final_cache]

    note = add_panel(
        api,
        ghdoc,
        "Eccentric joint / crank-slider.\n\nEdge-based mode: Kangaroo goals are driven only by live circular edge centers extracted from Model Object geometry using object_id + edge_index metadata. The only point params are the fixed shaft axis and fixed piston slide axis.\n\nDefault mode is live-driver: the eccentric object leads the solve and is not written by Content Cache. Rotate/edit it in Rhino, then solve/reset to update the piston and rod.\n\nUse the DEBUG panels to compare live edge centers against solved centers. The piston and rod Content Cache transforms are based on these live centers.\n\nKangaroo particles:\n0 = solved eccentric pin\n1 = solved piston pin.",
        sx,
        sy + 900,
    )

    add_group(api, ghdoc, "Mate record", [note])
    add_group(api, ghdoc, "Fixed axes", [shaft_start, shaft_end, shaft_vector, piston_axis_start, piston_axis_end])
    add_group(api, ghdoc, "Driver", driver_components + [reset_button])
    add_group(api, ghdoc, "Kangaroo goals", [rod_line, live_rod_length, length_goal, eccentric_anchor, piston_on_curve, solver])
    add_group(api, ghdoc, "Solved linkage preview", [solved_ecc, solved_piston, solved_line])
    if debug_panels:
        add_group(api, ghdoc, "Live metadata debug output", debug_panels)
    if eccentric_components:
        add_group(api, ghdoc, "Eccentric Content Cache writeback", eccentric_components)
    elif eccentric_obj is not None:
        add_group(api, ghdoc, "Eccentric live driver metadata", [eccentric_obj, eccentric_reader, live_eccentric_center] + live_eccentric_center_components)
    add_group(api, ghdoc, "Piston writeback object", [piston_obj, piston_reader, live_piston_center, piston_pin_actual, piston_translation, moved_piston, replacement_piston] + live_piston_center_components)
    if rod_components:
        add_group(api, ghdoc, "Rod writeback object", rod_components)
    if final_cache_components:
        add_group(api, ghdoc, "Single final Content Cache writeback", final_cache_components)


def rebuild_session_definition(session, *, save=True):
    ghdoc = session.get("ghdoc")
    if ghdoc is None:
        raise AssemblyGenerationError("Session has no GH document.")

    api = _load_generation_api()
    clear_ghdoc(ghdoc)

    header = add_panel(
        api,
        ghdoc,
        "AssemblyGH generated definition\n\nSession: {}\nMates: {}\nJoints: {}\nBodies: {}\nControlled objects: {}\n\nThis document is generated from body + joint/mate metadata. Do not edit it by hand.".format(
            session.get("id", "")[:8],
            len(session.get("mates", [])),
            len(session.get("joints", [])),
            len(session.get("bodies", {})),
            len(session.get("controlled_objects", {})),
        ),
        20,
        20,
    )
    add_group(api, ghdoc, "AssemblyGH session", [header])

    y = 180
    joints = session.get("joints", [])
    synthesized_record = _synthesize_crank_slider_mate_from_joints(joints) if joints else None
    if synthesized_record is not None:
        source_panel = add_panel(
            api,
            ghdoc,
            "Fusion-style joint graph detected: crank-slider\n\nGenerated Kangaroo graph from {} joint records.\n\nSource joint IDs:\n{}".format(
                len(synthesized_record.get("source_joint_ids", [])),
                "\n".join("- {}".format(value) for value in synthesized_record.get("source_joint_ids", [])),
            ),
            20,
            y,
        )
        add_group(api, ghdoc, "Fusion joint graph adapter", [source_panel])
        y += 220
        _emit_eccentric_joint(api, ghdoc, synthesized_record, 20, y)
        y += 1100
    else:
        for index, joint in enumerate(joints):
            panel = add_panel(api, ghdoc, _joint_summary_text(joint), 20, y)
            add_group(api, ghdoc, "Joint {}: {}".format(index + 1, joint["name"]), [panel])
            y += 320

    for index, record in enumerate(session.get("mates", [])):
        if record["type"] == "eccentric_joint":
            _emit_eccentric_joint(api, ghdoc, record, 20, y)
            y += 1100
        else:
            panel = add_panel(api, ghdoc, _mate_summary_text(record), 20, y)
            add_group(api, ghdoc, "Mate {}: {}".format(index + 1, record["name"]), [panel])
            y += 260

    ghdoc.ExpireSolution()
    session["dirty"] = True
    if save:
        save_session_definition()
    return ghdoc
