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
        _bool_setting(plugin_data.ADD_TACK_ALLOW_CHILD_MOVEMENT, False),
    )


def _save_parent_options(translation, rotation, attach, allow_child_movement):
    values = plugin_data.settings()
    values.update(
        {
            plugin_data.ADD_TACK_TRANSLATION: bool(translation),
            plugin_data.ADD_TACK_ROTATION: bool(rotation),
            plugin_data.ADD_TACK_ATTACH: bool(attach),
            plugin_data.ADD_TACK_ALLOW_CHILD_MOVEMENT: bool(allow_child_movement),
        }
    )
    plugin_data.set_settings(values)


def _flip_child_plane(doc, definition, plane, role, rotation):
    """Choose the Child plane's persisted orientation before creating a Tack."""
    if role != "child" or not rotation:
        return definition, plane

    flipped = Rhino.Input.Custom.OptionToggle(
        _bool_setting(plugin_data.ADD_TACK_FLIP_CHILD_PLANE, False),
        "No",
        "Yes",
    )
    getter = Rhino.Input.Custom.GetOption()
    getter.SetCommandPrompt("Confirm child plane orientation")
    getter.AcceptNothing(True)
    getter.AddOptionToggle("Flip", flipped)
    while True:
        result = getter.Get()
        if result == Rhino.Input.GetResult.Nothing:
            plugin_data.set_setting(
                plugin_data.ADD_TACK_FLIP_CHILD_PLANE,
                bool(flipped.CurrentValue),
            )
            if not flipped.CurrentValue:
                return definition, plane
            definition = analytic_plane.flipped_definition(definition)
            flipped_plane = analytic_plane.resolve_definition(doc, definition)
            return (definition, flipped_plane) if flipped_plane is not None else None
        if result != Rhino.Input.GetResult.Option:
            return None


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
    return _flip_child_plane(doc, definition, plane, role, rotation)


def select_child(doc, parent_id):
    from tack.core.objects import object_key, same_id
    from tack.links import repository

    existing_child_ids = {object_key(link.child_id) for link in repository.all_links(doc)}
    while True:
        child = select_object(
            doc,
            "Select child object",
            allow_preselection=False,
            object_filter=lambda obj: (
                obj is not None and not same_id(obj.Id, parent_id)
            ),
        )
        if child is None:
            return None
        if object_key(child.Id) not in existing_child_ids:
            return child
        child.Select(False)
        doc.Views.Redraw()
        Rhino.UI.Dialogs.ShowMessage(
            "This object already has a parent Tack and cannot be selected as "
            "a child.",
            "Tack child already has a parent",
            Rhino.UI.ShowMessageButton.OK,
            Rhino.UI.ShowMessageIcon.Warning,
        )


def select_parent_and_degrees_of_freedom(doc):
    """Select the parent while configuring Tack's native command options."""
    (
        translation_enabled,
        rotation_enabled,
        attach_enabled,
        allow_child_movement_enabled,
    ) = _parent_options()
    translation = Rhino.Input.Custom.OptionToggle(translation_enabled, "Off", "On")
    rotation = Rhino.Input.Custom.OptionToggle(rotation_enabled, "Off", "On")
    attach = Rhino.Input.Custom.OptionToggle(attach_enabled, "Off", "On")
    allow_child_movement = Rhino.Input.Custom.OptionToggle(
        allow_child_movement_enabled,
        "Off",
        "On",
    )

    while True:
        getter = Rhino.Input.Custom.GetObject()
        getter.SetCommandPrompt("Select parent object")
        getter.GeometryFilter = Rhino.DocObjects.ObjectType.AnyObject
        getter.EnablePreSelect(True, True)
        getter.AddOptionToggle("Translation", translation)
        getter.AddOptionToggle("Rotation", rotation)
        getter.AddOptionToggle("Attach", attach)
        getter.AddOptionToggle("AllowChildMovement", allow_child_movement)
        result = getter.Get()
        if result == Rhino.Input.GetResult.Option:
            _save_parent_options(
                bool(translation.CurrentValue),
                bool(rotation.CurrentValue),
                bool(attach.CurrentValue),
                bool(allow_child_movement.CurrentValue),
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
                "allow_child_movement": bool(allow_child_movement.CurrentValue),
            }
        Rhino.RhinoApp.WriteLine("Select an object with a valid bounding box.")


def preview_placement(doc, child, parent_plane, child_plane):
    """Preview the one-time full plane alignment performed by Attach."""
    conduit = TransformPreviewConduit(child, parent_plane, child_plane)
    getter = Rhino.Input.Custom.GetOption()
    getter.SetCommandPrompt("Preview the child placement")
    getter.AcceptNothing(True)
    conduit.Enabled = True
    doc.Views.Redraw()
    try:
        return conduit.transform if getter.Get() == Rhino.Input.GetResult.Nothing else None
    finally:
        conduit.Enabled = False
        doc.Views.Redraw()
