"""Interactive pickers that drive the TackAdd command flow."""

import Rhino

from tack.anchors import analytic_plane, definitions
from tack.core import plugin_data
from tack.dynamic.placement_preview import TransformPreviewConduit
from tack.prompting import analytic_plane_picker
from tack.prompting.osnap_anchor_picker import select_object


def _bool_setting(name, default):
    value = plugin_data.setting(name, default)
    return value if isinstance(value, bool) else default


def _parent_options():
    return (
        _bool_setting(plugin_data.ADD_TACK_TRANSLATION, True),
        _bool_setting(plugin_data.ADD_TACK_ROTATION, True),
        _bool_setting(plugin_data.ADD_TACK_ATTACH, False),
    )


def _save_parent_options(translation, rotation, attach):
    values = plugin_data.settings()
    values.update(
        {
            plugin_data.ADD_TACK_TRANSLATION: bool(translation),
            plugin_data.ADD_TACK_ROTATION: bool(rotation),
            plugin_data.ADD_TACK_ATTACH: bool(attach),
        }
    )
    plugin_data.set_settings(values)


def _invert_option():
    return _bool_setting(plugin_data.ADD_TACK_INVERT, False)


def _save_invert_option(inverted):
    plugin_data.set_setting(plugin_data.ADD_TACK_INVERT, bool(inverted))


def pick_plane(doc, obj, role, rotation):
    view = doc.Views.ActiveView
    if view is None:
        return None
    picked = (
        analytic_plane_picker.pick_plane(
            doc,
            obj,
            view.ActiveViewport.ConstructionPlane(),
        )
        if rotation
        else analytic_plane_picker.pick_origin(
            doc,
            obj,
            view.ActiveViewport.ConstructionPlane(),
        )
    )
    if picked is None:
        return None
    definition = picked["definition"]
    plane = analytic_plane.resolve_definition(doc, definition)
    if plane is None:
        Rhino.RhinoApp.WriteLine(f"The {role} Tack plane could not be resolved.")
        return None
    return definition, plane


def select_child(doc, parent_id):
    while True:
        child = select_object(
            doc,
            "Select child object",
            allow_preselection=False,
        )
        if child is None:
            return None
        if str(child.Id).lower() != str(parent_id).lower():
            return child
        Rhino.RhinoApp.WriteLine("Select a child different from the parent.")


def select_parent_and_degrees_of_freedom(doc):
    """Select the parent while configuring Tack's native command options."""
    translation_enabled, rotation_enabled, attach_enabled = _parent_options()
    translation = Rhino.Input.Custom.OptionToggle(translation_enabled, "Off", "On")
    rotation = Rhino.Input.Custom.OptionToggle(rotation_enabled, "Off", "On")
    attach = Rhino.Input.Custom.OptionToggle(attach_enabled, "Off", "On")

    while True:
        getter = Rhino.Input.Custom.GetObject()
        getter.SetCommandPrompt("Select parent object")
        getter.GeometryFilter = Rhino.DocObjects.ObjectType.AnyObject
        getter.EnablePreSelect(True, True)
        getter.AddOptionToggle("Translation", translation)
        getter.AddOptionToggle("Rotation", rotation)
        getter.AddOptionToggle("Attach", attach)
        result = getter.Get()
        if result == Rhino.Input.GetResult.Option:
            _save_parent_options(
                bool(translation.CurrentValue),
                bool(rotation.CurrentValue),
                bool(attach.CurrentValue),
            )
            continue
        if result != Rhino.Input.GetResult.Object:
            return None
        obj_ref = getter.Object(0)
        parent = obj_ref.Object() if obj_ref is not None else None
        if parent is not None and definitions.bounding_box_center(parent) is not None:
            return parent, {
                "translation": bool(translation.CurrentValue),
                "rotation": bool(rotation.CurrentValue),
                "attach": bool(attach.CurrentValue),
            }
        Rhino.RhinoApp.WriteLine("Select an object with a valid bounding box.")


def preview_placement(
    doc,
    child,
    parent_plane,
    child_plane,
    translation,
    rotation,
):
    conduit = TransformPreviewConduit(
        child,
        parent_plane,
        child_plane,
        translation=translation,
        rotation=rotation,
    )
    inverted = Rhino.Input.Custom.OptionToggle(_invert_option(), "No", "Yes")
    getter = Rhino.Input.Custom.GetOption()
    getter.SetCommandPrompt("Preview the child placement")
    getter.AcceptNothing(True)
    if rotation:
        getter.AddOptionToggle("Invert", inverted)

    def redraw():
        conduit.inverted = bool(inverted.CurrentValue)
        doc.Views.Redraw()

    conduit.Enabled = True
    doc.Views.Redraw()
    try:
        while True:
            result = getter.Get()
            if result == Rhino.Input.GetResult.Nothing:
                redraw()
                return conduit.transform, conduit.inverted
            if result != Rhino.Input.GetResult.Option:
                return None
            _save_invert_option(bool(inverted.CurrentValue))
            redraw()
    finally:
        conduit.Enabled = False
        doc.Views.Redraw()
