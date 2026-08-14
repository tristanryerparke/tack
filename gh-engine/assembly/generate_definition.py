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
    doc = Rhino.RhinoDoc.ActiveDoc
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
    if "eccentric_pin_edge" in refs:
        origin = _edge_center(refs["eccentric_pin_edge"])
    else:
        origin = _point3d(refs["eccentric_pin_start"]["point"])
    return origin, normal


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


def _add_static_geometry_param(api, ghdoc, nick, object_id, x, y, group_title=None):
    """Snapshot object geometry so Content Cache writeback cannot accumulate.

    Reading geometry from the live Model Object after Content Cache writes causes
    feedback: each solve transforms the already-transformed object again. This
    param stores the base geometry once in the generated GH definition.
    """
    doc = Rhino.RhinoDoc.ActiveDoc
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

    shaft_axis = refs["shaft_axis"]
    piston_axis = refs["piston_axis"]
    plane_origin, plane_normal = _mechanism_plane_from_record(refs)
    edge_based = "rotator_shaft_edge" in refs
    eccentric_pin_values = _point_tuple(_edge_center(refs["eccentric_pin_edge"])) if edge_based else refs["eccentric_pin_start"]["point"]
    piston_pin_values = _point_tuple(_edge_center(refs["piston_pin_edge"])) if edge_based else refs["piston_pin_start"]["point"]
    eccentric_pin_point = _project_point_to_plane(
        _point3d(eccentric_pin_values),
        plane_origin,
        plane_normal,
    )
    piston_axis_start_point, piston_axis_end_point = _project_line_to_plane(
        piston_axis["start"],
        piston_axis["end"],
        plane_origin,
        plane_normal,
    )
    piston_axis_start_point, piston_axis_end_point = _extended_axis_points(
        piston_axis_start_point,
        piston_axis_end_point,
        params["rod_length"],
    )
    piston_pin_point = _project_point_to_plane(
        _point3d(piston_pin_values),
        plane_origin,
        plane_normal,
    )
    eccentric_pin = _point_tuple(eccentric_pin_point)
    piston_pin = _point_tuple(piston_pin_point)
    actual_piston_pin = _point_tuple(_point3d(piston_pin_values))
    piston_object_id = refs["piston_object"]["object_id"]
    eccentric_object = refs.get("eccentric_object")
    rod_object = refs.get("rod_object")

    sx = origin_x
    sy = origin_y

    # Geometry source references must use the actual selected edge centers, not
    # the projected solver points. This lets transforms snap initially
    # non-coincident parts into the solved planar mate locations.
    rod_big = eccentric_pin
    rod_small = piston_pin
    if edge_based:
        rod_big = _point_tuple(_edge_center(refs["rod_big_edge"]))
        rod_small = _point_tuple(_edge_center(refs["rod_small_edge"]))
        params["rod_length"] = _point3d(rod_big).DistanceTo(_point3d(rod_small))

    # Base references.
    shaft_start = _add_point_param(api, ghdoc, "shaft axis start", shaft_axis["start"], sx, sy + 20)
    shaft_end = _add_point_param(api, ghdoc, "shaft axis end", shaft_axis["end"], sx, sy + 95)
    eccentric_start = _add_point_param(api, ghdoc, "eccentric pin center", eccentric_pin, sx, sy + 190)
    rod_big_start = _add_point_param(api, ghdoc, "rod eccentric-end center", rod_big, sx, sy + 270)
    rod_small_start = _add_point_param(api, ghdoc, "rod piston-end center", rod_small, sx, sy + 350)
    piston_axis_start = _add_point_param(api, ghdoc, "piston axis start projected/extended", _point_tuple(piston_axis_start_point), sx, sy + 455)
    piston_axis_end = _add_point_param(api, ghdoc, "piston axis end projected/extended", _point_tuple(piston_axis_end_point), sx, sy + 530)
    piston_pin_start = _add_point_param(api, ghdoc, "piston wrist-pin center projected", piston_pin, sx, sy + 640)
    piston_pin_actual = _add_point_param(api, ghdoc, "piston wrist-pin actual edge center", actual_piston_pin, sx, sy + 710)
    piston_obj = _add_model_object_param(api, ghdoc, "piston object", piston_object_id, sx, sy + 790)
    base_piston_geometry = _add_static_geometry_param(api, ghdoc, "base piston geometry", piston_object_id, sx, sy + 880)

    eccentric_obj = None
    base_eccentric_geometry = None
    if eccentric_object is not None:
        eccentric_obj = _add_model_object_param(api, ghdoc, "eccentric object", eccentric_object["object_id"], sx, sy + 950)
        base_eccentric_geometry = _add_static_geometry_param(api, ghdoc, "base eccentric geometry", eccentric_object["object_id"], sx, sy + 1040)

    rod_obj = None
    base_rod_geometry = None
    if rod_object is not None:
        rod_obj = _add_model_object_param(api, ghdoc, "rod object", rod_object["object_id"], sx, sy + 1135)
        base_rod_geometry = _add_static_geometry_param(api, ghdoc, "base rod geometry", rod_object["object_id"], sx, sy + 1225)

    angle_slider = _add_number_slider(
        api,
        ghdoc,
        "shaft angle radians",
        params.get("angle_driver", {}).get("initial_degrees", 0.0),
        sx + 240,
        sy + 20,
        minimum=-6.283185307179586,
        maximum=6.283185307179586,
    )
    reset_button = _add_button(api, ghdoc, "Reset", sx + 480, sy + 20)

    # Driven geometry and Kangaroo goals.
    shaft_line = emit_named(api, ghdoc, "Line", sx + 240, sy + 95)
    shaft_line.NickName = "shaft axis line"
    shaft_vector = emit_named(api, ghdoc, "Vector 2Pt", sx + 240, sy + 170)
    shaft_vector.NickName = "shaft axis vector / plane normal"
    piston_axis_line = emit_named(api, ghdoc, "Line", sx + 240, sy + 365)
    piston_axis_line.NickName = "piston slider line"
    rotate_ecc = emit_named(api, ghdoc, "Rotate Axis", sx + 480, sy + 120)
    rotate_ecc.NickName = "rotate eccentric pin"
    rod_line = emit_named(api, ghdoc, "Line", sx + 480, sy + 285)
    rod_line.NickName = "rod constraint line"
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
    wire(eccentric_start, 0, rotate_ecc, 0)
    wire(angle_slider, 0, rotate_ecc, 1)
    wire(shaft_line, 0, rotate_ecc, 2)
    wire(eccentric_start, 0, rod_line, 0)
    wire(piston_pin_start, 0, rod_line, 1)
    wire(rod_line, 0, length_goal, 0)
    wire(eccentric_start, 0, eccentric_anchor, 0)
    wire(rotate_ecc, 0, eccentric_anchor, 1)
    wire(piston_pin_start, 0, piston_on_curve, 0)
    wire(piston_axis_line, 0, piston_on_curve, 1)
    wire(length_goal, 0, solver, 0)
    wire(eccentric_anchor, 0, solver, 0)
    wire(piston_on_curve, 0, solver, 0)
    wire(reset_button, 0, solver, 1)

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

    eccentric_components = []
    if eccentric_obj is not None:
        rotated_eccentric = emit_named(api, ghdoc, "Rotate Axis", sx + 1220, sy + 20)
        rotated_eccentric.NickName = "rotated eccentric geometry"
        replacement_eccentric = emit_guid(api, ghdoc, "d7071c97-bc7f-4966-beba-b7110064eebf", sx + 1460, sy + 20)
        replacement_eccentric.NickName = "replacement eccentric object"
        eccentric_cache = emit_guid(api, ghdoc, "1fae4c7a-d84a-4f04-8400-179e13193381", sx + 1740, sy + 20)
        eccentric_cache.NickName = "Content Cache Push eccentric"
        add_content_cache_push_input(eccentric_cache)
        wire(base_eccentric_geometry, 0, rotated_eccentric, 0)
        wire(angle_slider, 0, rotated_eccentric, 1)
        wire(shaft_line, 0, rotated_eccentric, 2)
        wire(eccentric_obj, 0, replacement_eccentric, 0)
        wire(rotated_eccentric, 0, replacement_eccentric, 1)
        wire(replacement_eccentric, 0, eccentric_cache, 0)
        eccentric_components = [
            eccentric_obj,
            base_eccentric_geometry,
            rotated_eccentric,
            replacement_eccentric,
            eccentric_cache,
        ]

    # Piston writeback: static base geometry + solved pin translation.
    piston_translation = emit_named(api, ghdoc, "Vector 2Pt", sx + 1460, sy + 540)
    piston_translation.NickName = "piston translation"
    moved_piston = emit_named(api, ghdoc, "Move", sx + 1700, sy + 650)
    moved_piston.NickName = "moved piston geometry"
    replacement_piston = emit_guid(api, ghdoc, "d7071c97-bc7f-4966-beba-b7110064eebf", sx + 1940, sy + 650)
    replacement_piston.NickName = "replacement piston object"
    piston_cache = emit_guid(api, ghdoc, "1fae4c7a-d84a-4f04-8400-179e13193381", sx + 2220, sy + 650)
    piston_cache.NickName = "Content Cache Push piston"
    add_content_cache_push_input(piston_cache)

    wire(piston_pin_actual, 0, piston_translation, 0)
    wire(solved_piston, 0, piston_translation, 1)
    wire(base_piston_geometry, 0, moved_piston, 0)
    wire(piston_translation, 0, moved_piston, 1)
    wire(piston_obj, 0, replacement_piston, 0)
    wire(moved_piston, 0, replacement_piston, 1)
    wire(replacement_piston, 0, piston_cache, 0)

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
        rod_cache = emit_guid(api, ghdoc, "1fae4c7a-d84a-4f04-8400-179e13193381", sx + 2460, sy + 815)
        rod_cache.NickName = "Content Cache Push rod"
        add_content_cache_push_input(rod_cache)

        wire(rod_big_start, 0, initial_rod_dir, 0)
        wire(rod_small_start, 0, initial_rod_dir, 1)
        wire(solved_ecc, 0, solved_rod_dir, 0)
        wire(solved_piston, 0, solved_rod_dir, 1)
        wire(rod_big_start, 0, initial_rod_plane, 0)
        wire(initial_rod_dir, 0, initial_rod_plane, 1)
        wire(shaft_vector, 0, initial_rod_plane, 2)
        wire(solved_ecc, 0, solved_rod_plane, 0)
        wire(solved_rod_dir, 0, solved_rod_plane, 1)
        wire(shaft_vector, 0, solved_rod_plane, 2)
        wire(base_rod_geometry, 0, oriented_rod, 0)
        wire(initial_rod_plane, 0, oriented_rod, 1)
        wire(solved_rod_plane, 0, oriented_rod, 2)
        wire(rod_obj, 0, replacement_rod, 0)
        wire(oriented_rod, 0, replacement_rod, 1)
        wire(replacement_rod, 0, rod_cache, 0)
        rod_components = [
            rod_obj,
            base_rod_geometry,
            initial_rod_dir,
            solved_rod_dir,
            initial_rod_plane,
            solved_rod_plane,
            oriented_rod,
            replacement_rod,
            rod_cache,
        ]

    note = add_panel(
        api,
        ghdoc,
        "Eccentric joint / crank-slider.\n\nKangaroo solves projected mate centers in the mechanism plane. Content Cache transforms use the actual selected edge centers, so initially non-coincident Breps should snap into the solved mate locations. The piston slide axis is automatically extended to approximate an infinite linear mate.\n\nChange 'shaft angle radians', click Reset, and Content Cache pushes the eccentric object, piston, and rod if selected.\n\nKangaroo particles:\n0 = solved eccentric pin\n1 = solved piston pin\n\nIf the piston jumps to the wrong branch, move the starting piston pin closer to the desired solution and reset.",
        sx,
        sy + 900,
    )

    add_group(api, ghdoc, "Mate record", [note])
    add_group(api, ghdoc, "References", [shaft_start, shaft_end, shaft_vector, eccentric_start, rod_big_start, rod_small_start, piston_axis_start, piston_axis_end, piston_pin_start, piston_pin_actual])
    add_group(api, ghdoc, "Driver", [angle_slider, reset_button, rotate_ecc])
    add_group(api, ghdoc, "Kangaroo goals", [rod_line, length_goal, eccentric_anchor, piston_on_curve, solver])
    add_group(api, ghdoc, "Solved linkage preview", [solved_ecc, solved_piston, solved_line])
    if eccentric_components:
        add_group(api, ghdoc, "Eccentric Content Cache writeback", eccentric_components)
    add_group(api, ghdoc, "Piston Content Cache writeback", [piston_obj, base_piston_geometry, piston_pin_actual, piston_translation, moved_piston, replacement_piston, piston_cache])
    if rod_components:
        add_group(api, ghdoc, "Rod Content Cache writeback", rod_components)


def rebuild_session_definition(session, *, save=True):
    ghdoc = session.get("ghdoc")
    if ghdoc is None:
        raise AssemblyGenerationError("Session has no GH document.")

    api = _load_generation_api()
    clear_ghdoc(ghdoc)

    header = add_panel(
        api,
        ghdoc,
        "AssemblyGH generated definition\n\nSession: {}\nMates: {}\nControlled objects: {}\n\nThis document is generated from mate records. Do not edit it by hand.".format(
            session.get("id", "")[:8],
            len(session.get("mates", [])),
            len(session.get("controlled_objects", {})),
        ),
        20,
        20,
    )
    add_group(api, ghdoc, "AssemblyGH session", [header])

    y = 180
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
