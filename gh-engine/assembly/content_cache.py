"""Content Cache helpers for AssemblyGH generated definitions."""

import os

import System

from assembly.component_io import emit_guid, safe_set_persistent_data, wire

MODEL_OBJECT_COMPONENT_GUID = "d7071c97-bc7f-4966-beba-b7110064eebf"
CONTENT_CACHE_COMPONENT_GUID = "1fae4c7a-d84a-4f04-8400-179e13193381"


def _add_iocomponents_reference():
    import clr

    try:
        clr.AddReference("IOComponents")
        return
    except Exception:
        pass

    gha_path = "/Applications/Rhino 8.app/Contents/Frameworks/RhCore.framework/Versions/A/Resources/ManagedPlugIns/GrasshopperPlugin.rhp/Components/IOComponents.gha"
    if os.path.exists(gha_path):
        clr.AddReferenceToFileAndPath(gha_path)
        return

    # Let the original AddReference error surface with context if the path also
    # does not exist.
    clr.AddReference("IOComponents")


def make_content_cache_action(action_name="Push"):
    _add_iocomponents_reference()
    from IOComponents.Rhinoceros.Cache import ModelAction

    action_type = System.Enum.Parse(ModelAction.Type, action_name)
    flags = (
        System.Reflection.BindingFlags.Instance
        | System.Reflection.BindingFlags.Public
        | System.Reflection.BindingFlags.NonPublic
    )
    action = ModelAction()
    attrs_field = action.GetType().GetField("_Attributes", flags)
    attrs = attrs_field.GetValue(action)
    attrs.GetType().GetField("Type", flags).SetValue(attrs, action_type)
    attrs_field.SetValue(action, attrs)
    return action


def add_content_cache_push_input(content_cache):
    from Grasshopper.Kernel import GH_ParameterSide

    for index in range(content_cache.Params.Input.Count):
        if content_cache.Params.Input[index].Name == "Action":
            action_param = content_cache.Params.Input[index]
            break
    else:
        action_param = content_cache.CreateParameter(GH_ParameterSide.Input, 1)
        content_cache.Params.RegisterInputParam(action_param, 1)
        content_cache.VariableParameterMaintenance()
        content_cache.Params.OnParametersChanged()

    safe_set_persistent_data(
        action_param,
        make_content_cache_action("Push"),
        "Content Cache Push action",
    )
    return action_param


def add_model_object_writeback(api, ghdoc, object_source, geometry_source, x, y, group_title):
    """Add Model Object + Content Cache Push and wire one moving object.

    ``object_source`` should output a Rhino Model Object reference.
    ``geometry_source`` should output the solved replacement geometry.
    """
    model_object = emit_guid(
        api,
        ghdoc,
        MODEL_OBJECT_COMPONENT_GUID,
        x,
        y,
        group_title + ": Model Object",
    )
    content_cache = emit_guid(
        api,
        ghdoc,
        CONTENT_CACHE_COMPONENT_GUID,
        x + 280,
        y,
        group_title + ": Content Cache Push",
    )
    add_content_cache_push_input(content_cache)

    wire(object_source, 0, model_object, 0)
    wire(geometry_source, 0, model_object, 1)
    wire(model_object, 0, content_cache, 0)
    return model_object, content_cache
