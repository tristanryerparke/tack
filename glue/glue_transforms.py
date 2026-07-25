import Rhino
import System

from glue_constants import (
    ALLOW_ROTATION,
    ALLOW_SCALE,
    ALLOW_TRANSLATION,
    EPS,
)
from glue_debug import log

# Keep the last command's choices as the next command's defaults.
_allow_translation = ALLOW_TRANSLATION
_allow_rotation = ALLOW_ROTATION
_allow_scale = ALLOW_SCALE


def transform_flags(xform):
    """Classify a Rhino transform using RhinoCommon's native rigid test."""
    linear = (
        (xform.M00, xform.M01, xform.M02),
        (xform.M10, xform.M11, xform.M12),
        (xform.M20, xform.M21, xform.M22),
    )
    identity = all(
        abs(linear[row][column] - (1.0 if row == column else 0.0)) <= EPS
        for row in range(3)
        for column in range(3)
    )
    has_translation = any(
        abs(value) > EPS
        for value in (xform.M03, xform.M13, xform.M23)
    )
    rigid = bool(xform.IsRigid)
    return has_translation, rigid and not identity, not rigid


def transform_allowed(xform, relationship):
    has_translation, has_rotation, has_scale = transform_flags(xform)
    return (
        (not has_translation or relationship["translation"])
        and (not has_rotation or relationship["rotation"])
        and (not has_scale or relationship["scale"])
    )


def choose_transform_types(parent_id):
    global _allow_translation, _allow_rotation, _allow_scale

    options = Rhino.Input.Custom.GetOption()
    options.SetCommandPrompt("Choose glue transform types, then press Enter")
    options.AcceptNothing(True)

    translation = Rhino.Input.Custom.OptionToggle(
        _allow_translation, "Off", "On"
    )
    rotation = Rhino.Input.Custom.OptionToggle(
        _allow_rotation, "Off", "On"
    )
    scale = Rhino.Input.Custom.OptionToggle(
        _allow_scale, "Off", "On"
    )
    options.AddOptionToggle("Translation", translation)
    options.AddOptionToggle("Rotation", rotation)
    options.AddOptionToggle("Scale", scale)
    reference_option = options.AddOption("ParentVertex")

    reference = "centroid"
    vertex_index = -1
    vertex_type = ""

    while True:
        result = options.Get()
        if result == Rhino.Input.GetResult.Option:
            if options.OptionIndex() != reference_option:
                continue
            selected_vertex = choose_parent_vertex(parent_id)
            if selected_vertex is None:
                return None
            vertex_type, vertex_index = selected_vertex
            reference = "vertex"
            continue
        if result != Rhino.Input.GetResult.Nothing:
            return None
        _allow_translation = translation.CurrentValue
        _allow_rotation = rotation.CurrentValue
        _allow_scale = scale.CurrentValue
        return (
            _allow_translation,
            _allow_rotation,
            _allow_scale,
            reference,
            vertex_index,
            vertex_type,
        )


def choose_parent_vertex(parent_id):
    getter = Rhino.Input.Custom.GetObject()
    getter.SetCommandPrompt("Select a vertex on the Parent")
    getter.SubObjectSelect = True
    getter.GeometryFilter = (
        Rhino.DocObjects.ObjectType.BrepVertex
        | Rhino.DocObjects.ObjectType.MeshVertex
    )
    getter.EnablePreSelect(False, True)
    log("vertex picker started for Parent {}".format(parent_id))

    vertex_types = (
        Rhino.Geometry.ComponentIndexType.BrepVertex,
        Rhino.Geometry.ComponentIndexType.MeshVertex,
    )

    result = getter.Get()
    log("vertex picker result: {}".format(result))
    if result != Rhino.Input.GetResult.Object:
        log("vertex picker did not return an object")
        return None

    obj_ref = getter.Object(0)
    component_index = obj_ref.GeometryComponentIndex
    component_type = component_index.ComponentIndexType
    log(
        "picked object={}, parent={}, component_type={}, index={}".format(
            obj_ref.ObjectId,
            parent_id,
            component_type,
            component_index.Index,
        )
    )
    if obj_ref.ObjectId != parent_id:
        log("picked object is not the selected Parent")
        print("Select a vertex on the Parent.")
        return None

    if component_type not in vertex_types:
        log("picked component is not a supported vertex")
        print("Select a vertex on the Parent.")
        return None

    component_name = System.Enum.GetName(
        Rhino.Geometry.ComponentIndexType,
        component_type,
    )
    selected = component_name or str(component_type), int(component_index.Index)
    log("stored vertex reference: type={}, index={}".format(*selected))
    return selected
